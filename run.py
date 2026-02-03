from gevent import monkey
monkey.patch_all()

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import shutil
import time
import datetime
import subprocess
import configparser
import socket
import gevent
from app import app, socketio, submission_worker, restore_state_on_startup

# --- 1. НАСТРОЙКА ЛОГИРОВАНИЯ ---
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(module)s: %(message)s',
    handlers=[
        RotatingFileHandler("logs/judge.log", maxBytes=2_000_000, backupCount=5, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# --- 2. ФОНОВЫЕ БЭКАПЫ БД ---
def backup_scheduler():
    """Каждые 10 минут копирует базу данных в папку backups"""
    if not os.path.exists('backups'):
        os.makedirs('backups')
    
    log.info("Запущен планировщик бэкапов.")
    
    while True:
        gevent.sleep(600)  # 10 минут ожидания
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            src_db = 'testirovschik.db'
            
            if os.path.exists(src_db):
                dst_db = f'backups/testirovschik_{timestamp}.db'
                shutil.copy2(src_db, dst_db)
                log.info(f"Бэкап БД создан: {dst_db}")
                
                # Удаляем старые бэкапы (оставляем последние 5)
                backups = sorted([os.path.join('backups', f) for f in os.listdir('backups') if f.endswith('.db')])
                while len(backups) > 5:
                    os.remove(backups.pop(0))
            else:
                log.warning("Файл БД не найден, бэкап пропущен.")
                
        except Exception as e:
            log.error(f"Ошибка при создании бэкапа: {e}", exc_info=True)

# --- 3. ОЧИСТКА ЗОМБИ-КОНТЕЙНЕРОВ ---
def cleanup_zombies():
    """Убивает старые контейнеры при старте, чтобы освободить память"""
    log.info("Очистка старых Docker-контейнеров...")
    try:
        images = ["testirovschik-python", "testirovschik-cpp", "testirovschik-csharp"]
        for img in images:
            # Fixed: Use list args instead of shell=True to prevent injection
            try:
                # Получаем ID контейнеров
                output = subprocess.check_output(
                    ['docker', 'ps', '-a', '-q', '--filter', f'ancestor={img}']
                ).decode().strip()
                if output:
                    container_ids = output.split()
                    subprocess.run(['docker', 'rm', '-f'] + container_ids, check=False)
                    log.info(f"Удалены зомби-контейнеры для {img}: {len(container_ids)} шт.")
            except Exception:
                pass
    except Exception as e:
        log.warning(f"Не удалось выполнить очистку Docker (возможно, он не запущен): {e}")

# --- 4. АВТО-ЗАПУСК ОЛИМПИАД ---
def auto_starter():
    """Проверяет запланированные олимпиады."""
    from app import olympiad_lock, olympiads, db 
    print("INFO: Планировщик олимпиад запущен.")
    
    while True:
        gevent.sleep(10) # Проверка каждые 10 секунд
        current_ts = time.time()
        
        try:
            with olympiad_lock:
                to_start = []
                # Ищем олимпиады, которым пора стартовать
                for oid, data in olympiads.items():
                    if data.get('status') == 'scheduled':
                        start_time = data.get('start_time', 0)
                        if start_time and current_ts >= start_time:
                            to_start.append(oid)
                
                for oid in to_start:
                    print(f"AUTO-START: Запуск запланированной олимпиады {oid}")
                    
                    # Обновляем память
                    olympiads[oid]['status'] = 'running'
                    olympiads[oid]['start_time'] = current_ts # Обновляем стартовое время
                    # Сохраняем старт в БД!
                    try:
                        db.set_olympiad_start_time(oid, current_ts)
                        db.remove_scheduled_olympiad(oid) # Удаляем из расписания, т.к. она уже идет
                    except Exception as e:
                        print(f"DB Error saving auto-start: {e}")
                        
                    socketio.emit('olympiad_started', {'status': 'ok'}, to=oid)
        except Exception as e:
             log.error(f"Ошибка в auto_starter: {e}")

def get_local_ip():
    """Определяет IP-адрес компьютера в локальной сети."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Пытаемся подключиться к публичному DNS (трафик не идет), чтобы узнать свой IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    # Читаем конфиг
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    HOST = config.get('server', 'HOST', fallback='0.0.0.0')
    PORT = config.getint('server', 'PORT', fallback=5000)
    
    # Предварительная очистка и восстановление
    cleanup_zombies()
    restore_state_on_startup()
    
    # Запуск фоновых задач
    #gevent.spawn(backup_scheduler)
    gevent.spawn(submission_worker)
    gevent.spawn(auto_starter)
    
    local_ip = get_local_ip()
    
    print("\n" + "="*60)
    print(f" СЕРВЕР ЗАПУЩЕН (HTTP РЕЖИМ)")
    print(f" Локальный доступ:   http://127.0.0.1:{PORT}")
    print(f" Доступ для других:  http://{local_ip}:{PORT}")
    print(f" Админка:            http://{local_ip}:{PORT}/login")
    print("="*60 + "\n")
    
    log.info(f"ЗАПУСК СЕРВЕРА (HTTP): http://{HOST}:{PORT}")
    
    try:
        # Запускаем БЕЗ ssl_context, чтобы гарантировать HTTP
        socketio.run(app, host=HOST, port=PORT)
    except Exception as e:
        log.critical(f"Ошибка запуска сервера: {e}", exc_info=True)
        print("Нажмите Enter, чтобы выйти...")
        input()
