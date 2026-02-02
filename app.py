from anyio import current_time
from gevent import monkey
monkey.patch_all()
import io
from gevent.pool import Pool
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file, abort
from flask_socketio import SocketIO, join_room, leave_room
from db_manager import DBManager, run_python, run_cpp, run_csharp
import os
import time
from flask import session
import uuid 
from functools import wraps 
import configparser
import pandas as pd
import zipfile
import re
import json
from threading import Lock, Semaphore 
from gevent.queue import Queue
from werkzeug.security import check_password_hash
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
import gevent 
from datetime import datetime
submission_queue = Queue()

socketio = SocketIO(app, async_mode='gevent')

@app.after_request
def add_header(response):
    """
    Умное кэширование:
    - Статику (CSS/JS/Fonts) кэшируем на 1 час, чтобы не "положить" сеть при 100 участниках.
    - Динамический контент (страницы, JSON) не кэшируем.
    """
    # Если запрос идет к папке static, разрешаем кэш
    if request.path.startswith('/static'):
        response.headers['Cache-Control'] = 'public, max-age=3600'
    else:
        # Для остальных запросов (HTML, API) запрещаем кэш
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    
    return response

# Определяем точный путь к папке с проектом
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.ini')

config = configparser.ConfigParser()

# Проверяем наличие файла по полному пути
if not os.path.exists(CONFIG_PATH):
    default_config = """
[security]
SECRET_KEY = "your_very_secret_key_12345_for_sessions_98765"
ADMIN_PASSWORD = "commandblock2025"

[server]
MAX_CHECKS = 20
"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write(default_config)
    print(f"WARNING: config.ini не найден по пути {CONFIG_PATH}. Создан файл по умолчанию.")

# Читаем конфиг по полному пути
config.read(CONFIG_PATH, encoding='utf-8') 

try:
    app.secret_key = config.get('security', 'SECRET_KEY').strip() 
    ADMIN_PASSWORD = config.get('security', 'ADMIN_PASSWORD').strip() 
    MAX_CONCURRENT_CHECKS = config.getint('server', 'MAX_CHECKS', fallback=20)
    print(f"INFO: Конфигурация загружена успешно. Лимит проверок: {MAX_CONCURRENT_CHECKS}")
    
except (configparser.NoSectionError, configparser.NoOptionError) as e:
    print(f"CRITICAL ERROR: Ошибка чтения config.ini ({e}). Используем defaults.")
    app.secret_key = 'fallback_secret_key'
    ADMIN_PASSWORD = 'admin'
    MAX_CONCURRENT_CHECKS = 10
check_pool = Pool(MAX_CONCURRENT_CHECKS)
if ADMIN_PASSWORD == "commandblock2025" or ADMIN_PASSWORD == "admin":
     print("WARNING: Вы используете пароль администратора по умолчанию. Обязательно смените его в config.ini")

db = DBManager()
olympiads = {}
olympiad_lock = Lock() 
docker_check_semaphore = Semaphore(MAX_CONCURRENT_CHECKS)



def _get_olympiad_state(olympiad_id):
    """
    ОПТИМИЗИРОВАННАЯ ВЕРСИЯ: Использует кэш.
    Пересчитывает scoreboard только если is_dirty=True.
    [FIX] Добавлена нормализация ключей scores (str), чтобы избежать ошибки JSON sort.
    """
    with olympiad_lock:
        if olympiad_id not in olympiads:
            return None 
        
        oly = olympiads[olympiad_id]
        if 'first_solves' not in oly:
            oly['first_solves'] = db.get_first_solvers(olympiad_id)

        remaining_seconds = 0
        if oly['status'] == 'running' and oly.get('start_time'):
            elapsed = time.time() - oly['start_time']
            duration_sec = oly['config']['duration_minutes'] * 60
            remaining_seconds = max(0, duration_sec - elapsed)
            if remaining_seconds <= 0:
                oly['status'] = 'finished'


        if not oly.get('is_dirty', True) and oly.get('cached_state'):
            response = oly['cached_state'].copy()
            response['remaining_seconds'] = remaining_seconds
            response['status'] = oly['status'] 
            response['first_solves'] = oly['first_solves']
            return response

        oly_data_copy = {
            'status': oly['status'],
            'config': oly['config'], 
            'participants': oly['participants'], 
        }

        scoreboard = []
        scoring_mode = oly_data_copy['config'].get('scoring', 'all_or_nothing')

        for p_id, p_data in oly_data_copy['participants'].items(): 
            total_score = 0
            total_penalty = 0
            
            # [FIX] Нормализация ключей: превращаем все ID задач в строки
            # Это предотвращает ошибку TypeError при jsonify (смесь int и str)
            normalized_scores = {}
            for k, v in p_data['scores'].items():
                str_key = str(k)
                # [FIX] Гарантируем, что все ключи в v тоже нормализованы
                if isinstance(v, dict):
                    normalized_scores[str_key] = v
                else:
                    normalized_scores[str_key] = {'score': 0, 'attempts': 0, 'passed': False, 'penalty': 0}

            if scoring_mode == 'icpc':
                total_score = sum(s.get('score', 0) for s in normalized_scores.values())
                total_penalty = sum(s.get('penalty', 0) for s in normalized_scores.values() if s.get('passed'))
            else:
                total_score = sum(s.get('score', 0) for s in normalized_scores.values())
            
            scoreboard.append({
                'participant_id': p_id, 
                'nickname': p_data['nickname'],
                'organization': p_data.get('organization', None),
                'scores': normalized_scores,
                'total_score': total_score,
                'total_penalty': total_penalty 
            })

        # [FIX] ИСПРАВЛЕНА СОРТИРОВКА ДЛЯ ICPC (по решенным задачам, потом по штрафу)
        if scoring_mode == 'icpc':
            scoreboard.sort(key=lambda p: (-p['total_score'], p['total_penalty']))
        else:
            scoreboard.sort(key=lambda p: -p['total_score'])

        state_to_cache = {
            'status': oly_data_copy['status'],
            'duration_minutes': oly_data_copy['config']['duration_minutes'],
            'config': {
                **oly_data_copy['config'],        
                'task_ids': oly['task_ids']       
            },
            'participants': [p['nickname'] for p in oly_data_copy['participants'].values()],
            'scoreboard': scoreboard,
            'first_solves': oly['first_solves']
        }
        oly['cached_state'] = state_to_cache
        oly['is_dirty'] = False
        
        response = state_to_cache.copy()
        response['remaining_seconds'] = remaining_seconds
        return response

@app.socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    role = data.get('role')
    participant_id = session.get('participant_id')
    nickname = session.get('nickname')
    session_olympiad_id = session.get('olympiad_id')
    
    print(f"DEBUG: Попытка входа. Ник: {nickname}, Комната: {room}, SessionOlyID: {session_olympiad_id}")

    if not room:
        print("ERROR: Не указана комната (room) при подключении.")
        return

    join_room(room)
    
    if role == 'spectator':
        
        current_state = _get_olympiad_state(room)
        if current_state:
            socketio.emit('full_status_update', current_state, to=request.sid)
        return

    if session.get(f'is_organizer_for_{room}'):
        print(f"INFO: Организатор присоединился к комнате: {room}")
        current_state = _get_olympiad_state(room)
        if current_state:
            socketio.emit('full_status_update', current_state, to=request.sid)
        return
    with olympiad_lock:
        if room not in olympiads:
            print(f"WARNING: Участник {nickname} пытается зайти в олимпиаду {room}, которой нет в памяти (возможно, сервер был перезагружен).")
            
        else:
            oly = olympiads[room]
            
            
            if participant_id:
                if participant_id not in oly['participants']:
                    try:
                        print(f"INFO: Восстановление данных для {nickname}...")

                        saved_data = None
                        try:
                            saved_data = db.get_participant_progress(room, participant_id)
                        except Exception as db_err:
                            print(f"DB ERROR: Ошибка при чтении из базы: {db_err}")
                        
                        if saved_data:
                            print(f"SUCCESS: Данные из БД найдены для {nickname}.")
                            submissions_restored = saved_data.get('last_submissions', {})
                            
                            for tid in oly['task_ids']:
                                str_tid = str(tid)
                                if str_tid not in submissions_restored and tid not in submissions_restored:
                                    submissions_restored[str_tid] = ""
                            
                            oly['participants'][participant_id] = {
                                'nickname': nickname,
                                'organization': saved_data.get('organization') or session.get('organization'),
                                'scores': saved_data['scores'],
                                'last_submissions': submissions_restored,
                                'finished_early': False,
                                'disqualified': saved_data.get('disqualified', False),
                                'pending_submissions': 0
                            }
                            
                        else:
                            print(f"INFO: Данных в БД нет. Создаем нового участника {nickname}.")
                            scores_data = {
                                tid: {'score': 0, 'attempts': 0, 'passed': False, 'penalty': 0} 
                                for tid in oly['task_ids']
                            }
                            oly['participants'][participant_id] = {
                                'nickname': nickname,
                                'organization': session.get('organization', None),
                                'scores': scores_data, 
                                'last_submissions': {tid: "" for tid in oly['task_ids']},
                                'finished_early': False,
                                'disqualified': False,
                                'pending_submissions': 0
                            }
                        oly['is_dirty'] = True
                    except Exception as e:
                        print(f"CRITICAL ERROR: Ошибка при добавлении участника {nickname}: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"INFO: Участник {nickname} уже есть в памяти.")
            else:
                print(f"WARNING: У {nickname} нет participant_id или не совпадает сессия. (SessID: {session_olympiad_id} != Room: {room})")

    current_state = _get_olympiad_state(room)
    if current_state:
        socketio.emit('full_status_update', current_state, to=room)


def process_single_submission(item):
    """
    Функция обработки ОДНОГО решения.
    Запускается в отдельном грин-треде (greenlet) внутри пула.
    """
    olympiad_id = item['olympiad_id']
    participant_id = item['participant_id']
    task_id = item['task_id']
    
    try:
        language = item['language']
        code = item['code']
        scoring_mode = item['scoring_mode']
        
        print(f"WORKER [Thread]: Начало проверки для {participant_id}, задача {task_id}, язык {language}")

        # 1. Получаем тесты из БД
        tests = db.get_tests_for_task(task_id)
        
        # 2. Получаем чекер
        task_info = db.get_task_details(task_id)
        checker_code = None
        if task_info:
            try: checker_code = task_info['checker_code']
            except: pass

        test_data_list = []

        if not tests:
            print(f"WORKER: Нет тестов для задачи {task_id}. Отмена проверки.")
            _handle_worker_error(olympiad_id, participant_id, task_id, "ОШИБКА: Для этой задачи не загружены тесты.")
            return 
        else:
            test_data_list = [
                {
                    'input': t['test_input'].replace('\r\n', '\n') if t['test_input'] else '',
                    'output': t['expected_output'].replace('\r\n', '\n') if t['expected_output'] else '',
                    'limit': t['time_limit']
                } for t in tests
            ]

        # === ВЫБОР ЯЗЫКА (Best Practice) ===
        RUNNERS = {
            'Python': run_python,
            'C++': run_cpp,
            'C#': run_csharp
        }
        
        runner = RUNNERS.get(language)
        
        if not runner:
            print(f"WORKER ERROR: Неподдерживаемый язык {language}")
            _handle_worker_error(olympiad_id, participant_id, task_id, f"Language '{language}' is not supported yet.")
            return

        # --- ЗАПУСК ---
        verdicts, global_err = runner(code, test_data_list, checker_code=checker_code)
        
        results_details = []
        passed_count = 0
        is_correct = False 
        
        if global_err:
            verdict = "Compilation Error" if "Compilation Error" in global_err else "Runtime Error"
            results_details.append({'test_num': 1, 'verdict': verdict, 'error': global_err})
        else:
            for i, v in enumerate(verdicts):
                verdict = v.get('verdict', 'Internal Error')
                results_details.append({'test_num': i + 1, 'verdict': verdict})
                if verdict == "Accepted":
                    passed_count += 1
        
        if len(test_data_list) > 0:
            is_correct = (passed_count == len(test_data_list)) and (not global_err)
        else:
            is_correct = False

        # === БЛОК ОБНОВЛЕНИЯ БАЗЫ ===
        new_score_info = {}
        response_data = {}

        with olympiad_lock:
            if olympiad_id in olympiads:
                oly = olympiads[olympiad_id]
                if participant_id in oly['participants']:
                    p_data = oly['participants'][participant_id]
                    
                    # Снимаем статус PENDING
                    p_data['pending_submissions'] = max(0, p_data.get('pending_submissions', 1) - 1)
                    
                    # Инициализация, если задача новая
                    if task_id not in p_data['scores']:
                        p_data['scores'][task_id] = {'score': 0, 'attempts': 0, 'passed': False, 'penalty': 0}
                    if task_id not in p_data.get('last_submissions', {}):
                        p_data['last_submissions'][task_id] = ""

                    # Проверка на дисквалификацию - РАННИЙ ВЫХОД
                    if p_data.get('disqualified', False):
                        print(f"INFO: Решение отклонено - участник {participant_id} дисквалифицирован")
                        return 

                    task_submissions = p_data['scores'][task_id]
                    
                    # Если решение верное, обновляем First Solves
                    if is_correct:
                        if 'first_solves' not in oly: oly['first_solves'] = {}
                        if task_id not in oly['first_solves']: oly['first_solves'][task_id] = participant_id
                    
                    # --- ЛОГИКА ПОДСЧЕТА БАЛЛОВ (ИСПРАВЛЕННАЯ) ---
                    if scoring_mode == 'icpc':
                        if not task_submissions['passed']:
                            if is_correct:
                                task_submissions['passed'] = True
                                task_submissions['score'] = 1
                                # [FIX] Защита от сбоя времени старта + правильный расчет штрафа
                                start_time = oly.get('start_time')
                                if start_time and start_time > 0:
                                    elapsed = max(0, time.time() - start_time)
                                    penalty_min = max(0, int(elapsed / 60))
                                    # Штраф = время + 20*неверные попытки
                                    task_submissions['penalty'] = penalty_min + (task_submissions.get('attempts', 0) * 20)
                                else:
                                    # Если нет времени старта, штраф = только неверные попытки
                                    task_submissions['penalty'] = task_submissions.get('attempts', 0) * 20
                            elif not global_err:
                                task_submissions['attempts'] = task_submissions.get('attempts', 0) + 1
                                
                    elif scoring_mode == 'all_or_nothing':
                        if is_correct:
                            task_submissions['score'] = 100
                            task_submissions['passed'] = True
                        elif not global_err:
                            task_submissions['attempts'] = task_submissions.get('attempts', 0) + 1
                            
                    else: # 'points'
                        total_tests = len(test_data_list)
                        calculated_score = 0
                        if total_tests > 0:
                            calculated_score = int(round((passed_count / total_tests) * 100))
                        
                        current_score = task_submissions.get('score', 0)
                        if calculated_score > current_score:
                            task_submissions['score'] = calculated_score
                        
                        if is_correct: 
                            task_submissions['passed'] = True
                        elif not global_err:
                            task_submissions['attempts'] = task_submissions.get('attempts', 0) + 1
                    # --- END LOGIKA ---
                    
                    new_score_info = task_submissions.copy()
                    oly['is_dirty'] = True
                    
                    response_data = {
                        'task_id': task_id,
                        'passed_count': passed_count,
                        'total_tests': len(test_data_list),
                        'new_score': new_score_info.get('score', 0),
                        'passed': new_score_info.get('passed', False),
                        'details': results_details,
                        'verdict': "OK" if is_correct else ("CE" if global_err else "WA/RE")
                    }
                    try:
                        db.save_olympiad_data(olympiad_id, oly)
                    except Exception as e:
                        print(f"DB SAVE ERROR: {e}")

        # === СОХРАНЕНИЕ ИСТОРИИ ===
        history_verdict = "Accepted" if is_correct else "Wrong Answer"
        if global_err: 
            history_verdict = "Compilation Error" if "Compilation" in global_err else "Runtime Error"
        elif not is_correct and results_details:
            for d in results_details:
                if d['verdict'] != 'Accepted':
                    history_verdict = d['verdict']
                    break
        
        try:
            db.add_to_history(olympiad_id, participant_id, task_id, language, history_verdict, passed_count, len(test_data_list))
        except Exception as e:
            print(f"HISTORY ERROR: {e}")

        # === ОТПРАВКА РЕЗУЛЬТАТА ===
        socketio.emit('personal_result', {
            'participant_id': participant_id,
            'data': response_data
        }, to=olympiad_id)

        current_state = _get_olympiad_state(olympiad_id)
        if current_state:
            socketio.emit('full_status_update', current_state, to=olympiad_id)

    except Exception as e:
        print(f"CRITICAL WORKER ERROR in Thread: {e}")
        import traceback
        traceback.print_exc()
        _handle_worker_error(olympiad_id, participant_id, task_id, f"Server Error: {str(e)}")

def submission_worker():
    """
    Главный процесс-диспетчер. 
    Берет задачи из очереди и отдает их в Пул потоков.
    Не блокирует очередь ожиданием выполнения проверки.
    """
    print(f"INFO: Воркер проверки запущен. Параллельных потоков: {check_pool.size}")
    
    while True:
        item = submission_queue.get() # Блокируется, если очередь пуста
        
        # Передаем задачу в пул. spawn не блокирует выполнение,
        # если есть свободные слоты в пуле. Если нет - ждет освобождения.
        check_pool.spawn(process_single_submission, item)

def _handle_worker_error(olympiad_id, participant_id, task_id, error_msg):
    """Вспомогательная функция, чтобы убрать статус 'В очереди' при ошибках"""
    with olympiad_lock:
        if olympiad_id in olympiads:
            p_data = olympiads[olympiad_id]['participants'].get(participant_id)
            if p_data:
                # Уменьшаем счетчик, чтобы разблокировать интерфейс
                p_data['pending_submissions'] = max(0, p_data.get('pending_submissions', 1) - 1)
    
    # Отправляем сообщение об ошибке клиенту
    socketio.emit('personal_result', {
        'participant_id': participant_id,
        'data': {
            'task_id': task_id,
            'passed': False,
            'verdict': "System Error",
            'details': [{'test_num': 0, 'verdict': 'System Error', 'error': error_msg}]
        }
    }, to=olympiad_id)
            
@app.route('/')
def index():
    if not session.get('is_admin'):
        return redirect(url_for('olympiad_index'))
    tasks = db.get_tasks()
    return render_template('index.html', tasks=tasks)

@app.route('/spectate/<olympiad_id>')
def spectate_olympiad(olympiad_id):
    """
    Публичный доступ к таблице результатов.
    Закрывается, если олимпиада завершена.
    """
    with olympiad_lock:
        if olympiad_id not in olympiads:
             return render_template('error.html', message="Олимпиада не найдена"), 404
        
        oly = olympiads[olympiad_id]
        
        if oly['status'] == 'finished':
            return render_template('error.html', message="Олимпиада завершена. Live-трансляция окончена."), 403


        tasks_count = len(oly['task_ids'])
        
    return render_template('spectator_board.html', 
                           olympiad_id=olympiad_id, 
                           tasks_count=tasks_count)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Доступ запрещен. Пожалуйста, войдите как администратор.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function



@admin_required
@app.route('/run_code', methods=['POST'])
def run_code_submission():
    data = request.json
    try:
        task_id = int(data['task_id'])
    except (ValueError, TypeError):
        return jsonify({'error': 'Некорректный ID задачи'}), 400

    language = data.get('language')
    code = data.get('code')
    
    if not code:
        return jsonify({'error': 'Код пустой'}), 400

    # 1. Получаем тесты
    tests = db.get_tests_for_task(task_id)
    
    # 2. Получаем чекер
    task_info = db.get_task_details(task_id)
    checker_code = None
    if task_info:
        try: checker_code = task_info['checker_code']
        except: pass

    test_data_list = []

    if not tests:
        if checker_code and checker_code.strip():
            # Запуск для проверки работоспособности (без тестов)
            test_data_list.append({'input': '', 'output': '', 'limit': 2.0})
        else:
            return jsonify({'error': 'Нет тестов для этой задачи и нет чекера'}), 400
    else:
        test_data_list = [
            {
                'input': t['test_input'].replace('\r\n', '\n') if t['test_input'] else '',
                'output': t['expected_output'].replace('\r\n', '\n') if t['expected_output'] else '',
                'limit': t['time_limit']
            } for t in tests
        ]
    
    # === ВЫБОР ЯЗЫКА ===
    RUNNERS = {
        'Python': run_python,
        'C++': run_cpp,
        'C#': run_csharp
    }
    
    runner = RUNNERS.get(language)
    if not runner:
        return jsonify({'error': f'Язык {language} не поддерживается сервером'}), 400
    
    # === ЗАЩИТА: ИСПОЛЬЗУЕМ СЕМАФОР ===
    verdicts = []
    global_err = None
    
    with docker_check_semaphore:
        verdicts, global_err = runner(code, test_data_list, checker_code=checker_code)
    # ==================================
    
    results = []
    passed_count = 0

    if global_err:
        verdict = "Compilation Error" if "Compilation Error" in global_err else "Runtime Error"
        results.append({
            'test_num': 1,
            'verdict': verdict,
            'input': '(system)',
            'expected': '-',
            'output': '',
            'error': global_err,
            'passed': False
        })
    else:
        for i, v in enumerate(verdicts):
            verdict = v.get('verdict', 'Internal Error')
            passed = (verdict == "Accepted")
            if passed: passed_count += 1
            
            inp = tests[i]['test_input'] if i < len(tests) else ""
            exp = tests[i]['expected_output'] if i < len(tests) else "(checker)"
                
            results.append({
                'test_num': i + 1,
                'verdict': verdict,
                'input': inp,
                'expected': exp,
                'output': v.get('output', ''),
                'error': v.get('error', ''),
                'passed': passed
            })

    overall_result = {
        'passed_count': passed_count,
        'total_tests': len(test_data_list),
        'details': results
    }
    
    return jsonify(overall_result)

@app.route('/olympiad/submit/<olympiad_id>', methods=['POST'])
def olympiad_submit(olympiad_id):
    participant_id = session.get('participant_id')
    nickname = session.get('nickname')
    data = request.json
    task_id = int(data['task_id'])
    language = data['language']
    code = data['code']
    
    with olympiad_lock: 
        if olympiad_id not in olympiads or not participant_id:
            return jsonify({'error': 'Олимпиада не активна или вы не авторизованы.'}), 403

        oly = olympiads[olympiad_id]
        if participant_id not in oly['participants']:
            return jsonify({'error': 'Участник не найден.'}), 403

        p_data = oly['participants'][participant_id]
        
        # Validate language against allowed languages
        allowed_languages = oly['config'].get('allowed_languages', ['Python', 'C++', 'C#'])
        if language not in allowed_languages:
            return jsonify({'error': f'Язык "{language}" не разрешён для этой олимпиады.'}), 400
        
        if p_data.get('disqualified'): 
            return jsonify({'error': 'Вы дисквалифицированы.'}), 400
        if p_data.get('finished_early'): 
            return jsonify({'error': 'Олимпиада завершена.'}), 400
        
        if oly.get('start_time'):
            elapsed = time.time() - oly['start_time']
            if elapsed > oly['config']['duration_minutes'] * 60:
                return jsonify({'error': 'Время вышло!'}), 400
        
        if p_data.get('pending_submissions', 0) >= 3:
            return jsonify({'error': 'Слишком много проверок в очереди. Ждите.'}), 429

        p_data['last_submissions'][task_id] = code 
        p_data['pending_submissions'] = p_data.get('pending_submissions', 0) + 1
        
        scoring_mode = oly['config'].get('scoring', 'all_or_nothing')

    db.update_submission_immediate(olympiad_id, participant_id, nickname, task_id, code)

    task_item = {
        'olympiad_id': olympiad_id,
        'participant_id': participant_id,
        'task_id': task_id,
        'language': language,
        'code': code,
        'scoring_mode': scoring_mode
    }
    
    submission_queue.put(task_item)
    
    socketio.emit('submission_pending', {
        'participant_id': participant_id,
        'task_id': task_id
    }, to=olympiad_id)
    
    return jsonify({
        'status': 'queued', 
        'message': 'Решение сохранено и принято на проверку',
        'queue_size': submission_queue.qsize()
    })


@app.route('/olympiad/create', methods=['GET', 'POST'])
@admin_required
def olympiad_create():
    if request.method == 'POST':
        task_ids = request.form.getlist('task_ids')
        duration = int(request.form.get('duration'))
        scoring = request.form.get('scoring')
        mode = request.form.get('mode')
        name = request.form.get('name', 'Olympiad')
        start_time_str = request.form.get('start_time_local')
        allowed_languages = request.form.getlist('allowed_languages')
        
        # Default to all languages if none selected
        if not allowed_languages:
            allowed_languages = ['Python', 'C++', 'C#']

        if not (1 <= len(task_ids) <= 10):
            flash('Необходимо выбрать от 1 до 10 задач.', 'danger') 
            return redirect(url_for('olympiad_create'))
        
        olympiad_id = str(uuid.uuid4())[:8]
        with olympiad_lock:
            while olympiad_id in olympiads:
                olympiad_id = str(uuid.uuid4())[:8]

            tasks_ordered = [int(tid) for tid in task_ids]
            
            status = 'waiting'
            start_timestamp = None
            
            if start_time_str:
                try:
                    dt = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
                    start_timestamp = dt.timestamp()
                    status = 'scheduled'
                except ValueError:
                    flash('Неверный формат времени.', 'warning')
            
            config_dict = {
                'duration_minutes': duration,
                'scoring': scoring,
                'mode': mode,
                'allowed_languages': allowed_languages
            }

            olympiads[olympiad_id] = {
                'status': status,
                'name': name,
                'task_ids': tasks_ordered,
                'tasks_details': [db.get_task_details(tid) for tid in tasks_ordered],
                'config': config_dict,
                'start_time': start_timestamp,
                'participants': {},
                'is_dirty': True,  
                'first_solves': {},     
                'cached_state': None    
            }

            try:
                db.save_olympiad_config(olympiad_id, tasks_ordered, name=name, duration=duration, scoring=scoring, allowed_languages=allowed_languages)
                
                if status == 'scheduled':
                    db.add_scheduled_olympiad(olympiad_id, name, start_timestamp, config_dict, tasks_ordered)
            except Exception as e:
                print(f"DB Error saving config: {e}")

        flash(f'Олимпиада создана! ID: {olympiad_id}', 'success')
        return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))

    tasks = db.get_tasks()
    return render_template('olympiad_create.html', tasks=tasks)

@app.route('/olympiad/mode/<olympiad_id>')
def get_olympiad_mode(olympiad_id):
    """API: Возвращает режим олимпиады (free/closed) для UI."""

    with olympiad_lock:
        if olympiad_id not in olympiads:
            return jsonify({'error': 'not found'}), 404
        
        mode = olympiads[olympiad_id].get('config', {}).get('mode', 'free')
    
    return jsonify({'mode': mode})

@app.route('/olympiad/join', methods=['GET', 'POST'])
def olympiad_join():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        olympiad_id = request.form.get('olympiad_id', '').strip()
        password = request.form.get('password', '').strip()
        organization = request.form.get('organization', '').strip() 

        if not nickname or not olympiad_id:
            flash('Нужно ввести и никнейм, и ID олимпиады.', 'warning')
            return redirect(url_for('olympiad_join'))
        
        oly_data_copy = None 

        with olympiad_lock:
            if olympiad_id not in olympiads:
                flash('Олимпиада с таким ID не найдена.', 'danger')
                return redirect(url_for('olympiad_join'))

            oly = olympiads[olympiad_id]
            oly_data_copy = {
                'config': oly['config'],
                'status': oly['status'],
                'participants': oly['participants'].copy() 
            }

        mode = oly_data_copy['config'].get('mode', 'free')

        participant_id_to_set = None
        participant_org = organization # [FIX] Используем введенную организацию по умолчанию

        if mode == 'free':
            existing_participant_id = None
            
            # 1. Сначала ищем в оперативной памяти (если сервер не перезагружался)
            for p_id, p_data in oly_data_copy['participants'].items():
                if p_data['nickname'] == nickname:
                    existing_participant_id = p_id
                    # [FIX] Если участник уже есть, берем его организацию из памяти, если новая не введена
                    if not participant_org and p_data.get('organization'):
                         participant_org = p_data.get('organization')
                         
                    if p_data.get('finished_early'):
                        flash('Вы уже завершили эту олимпиаду и не можете переподключиться.', 'warning')
                        return redirect(url_for('olympiad_end', olympiad_id=olympiad_id))
                    # [FIX] УДАЛЕНА БЛОКИРОВКА ДИСКВАЛИФИЦИРОВАННЫХ - они должны видеть свои результаты
                    break
            
            # 2. [FIX] Если в памяти нет, ищем в БД (чтобы восстановить баллы после перезагрузки)
            if not existing_participant_id:
                try:
                    existing_participant_id = db.get_participant_uuid_by_nickname(olympiad_id, nickname)
                    if existing_participant_id:
                        print(f"INFO: Участник {nickname} найден в базе (восстановление сессии).")
                except Exception as e:
                    print(f"DB Error looking up participant: {e}")

            if existing_participant_id:
                participant_id_to_set = existing_participant_id
            else:
                participant_id_to_set = str(uuid.uuid4())
        
        else: # Closed mode
            if not password:
                flash('Это закрытая олимпиада. Необходимо ввести пароль.', 'warning')
                return redirect(url_for('olympiad_join'))

            participant_data = db.validate_closed_participant(olympiad_id, nickname, password)
            
            if not participant_data:
                flash('Неверный никнейм или пароль для этой олимпиады.', 'danger')
                return redirect(url_for('olympiad_join'))
                
            participant_db_id = str(participant_data['id']) 
            # В закрытом режиме организация берется строго из белого списка
            participant_org = participant_data['organization'] 

            if participant_db_id in oly_data_copy['participants'] and oly_data_copy['participants'][participant_db_id].get('finished_early'):
                flash('Вы уже завершили эту олимпиаду и не можете переподключиться.', 'warning')
                return redirect(url_for('olympiad_end', olympiad_id=olympiad_id))
            
            participant_id_to_set = participant_db_id

        session['participant_id'] = participant_id_to_set
        session['nickname'] = nickname
        session['olympiad_id'] = olympiad_id
        
        # [FIX] Обязательно сохраняем организацию в сессию, 
        # чтобы handle_join_room мог её подхватить
        if participant_org:
            session['organization'] = participant_org
        
        if oly_data_copy.get('status') == 'running':
            return redirect(url_for('olympiad_run', olympiad_id=olympiad_id))
        else:
            return redirect(url_for('olympiad_lobby', olympiad_id=olympiad_id))

    return render_template('olympiad_join.html')

@app.route('/olympiad/lobby/<olympiad_id>')
def olympiad_lobby(olympiad_id):
    nickname = session.get('nickname')
    if not nickname or session.get('olympiad_id') != olympiad_id:
        return redirect(url_for('olympiad_join'))
    return render_template('olympiad_lobby.html', olympiad_id=olympiad_id, nickname=nickname)

@app.route('/olympiad/host/<olympiad_id>')
@admin_required
def olympiad_host(olympiad_id):

    session.pop('participant_id', None)
    session.pop('nickname', None)
    session.pop('olympiad_id', None)
    session.pop('organization', None)

    oly_data_copy = None
    oly_mode = 'free'
    tasks_details = []
    
    with olympiad_lock:
        if olympiad_id not in olympiads:
            return "Олимпиада не найдена", 404
        
        session[f'is_organizer_for_{olympiad_id}'] = True
        
        oly_data = olympiads[olympiad_id]
        oly_mode = oly_data['config'].get('mode', 'free')
        tasks_details = oly_data['tasks_details']
        oly_data_copy = oly_data.copy()
        if 'first_solves' not in oly_data_copy:
             oly_data_copy['first_solves'] = db.get_first_solvers(olympiad_id)
        
    whitelist = []
    
    if oly_mode == 'closed':
        whitelist = db.get_whitelist_for_olympiad(olympiad_id)
        
    return render_template('olympiad_host.html', 
                           olympiad_id=olympiad_id, 
                           tasks=tasks_details,
                           oly_mode=oly_mode,
                           whitelist=whitelist,
                           olympiad_data=oly_data_copy)

@app.route('/olympiad/start/<olympiad_id>', methods=['POST'])
@admin_required
def olympiad_start(olympiad_id):

    with olympiad_lock:
        if olympiad_id in olympiads:
            current_time = time.time()
            # 1. Обновляем в оперативной памяти (для мгновенной работы)
            olympiads[olympiad_id]['status'] = 'running'
            olympiads[olympiad_id]['start_time'] = current_time 
            
            # 2. Сохраняем в БД (на случай перезагрузки)
            db.set_olympiad_start_time(olympiad_id, current_time)
          
            socketio.emit('olympiad_started', {'status': 'ok'}, to=olympiad_id)
            
            return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404

@app.route('/olympiad/run/<olympiad_id>')
def olympiad_run(olympiad_id):
    
    oly_data_copy = None
    with olympiad_lock:
        
        if session.get('olympiad_id') != olympiad_id:
            
            flash('Вы вошли в другую олимпиаду. Войдите заново.', 'warning')
            session.pop('participant_id', None)
            session.pop('nickname', None)
            session.pop('olympiad_id', None)
            session.pop('organization', None)
            return redirect(url_for('olympiad_join'))
    
    with olympiad_lock:
        if olympiad_id not in olympiads or 'nickname' not in session:
            return redirect(url_for('olympiad_join'))
        
        oly = olympiads[olympiad_id]
        participant_id = session.get('participant_id') 
        participant_data = oly['participants'].get(participant_id, {})
        
        
        if participant_data.get('finished_early'):
            flash('Вы уже завершили эту олимпиаду.', 'info')
            return redirect(url_for('olympiad_end', olympiad_id=olympiad_id))
        if participant_data.get('disqualified'):
            flash('Вы были дисквалифицированы.', 'danger')
            return redirect(url_for('olympiad_end', olympiad_id=olympiad_id))
        if oly['status'] != 'running':
            return redirect(url_for('olympiad_lobby', olympiad_id=olympiad_id))

        if participant_id and participant_id not in oly['participants']:
            

            scores_data = {
                tid: {
                    'score': 0,      
                    'attempts': 0,   
                    'passed': False, 
                    'penalty': 0     
                } for tid in oly['task_ids']
            }
            
            oly['participants'][participant_id] = {
                'nickname': session['nickname'],
                'organization': session.get('organization', None), 
                'scores': scores_data, 
                'last_submissions': {tid: "" for tid in oly['task_ids']},
                'finished_early': False,
                'disqualified': False, 
                'pending_submissions': 0  
            }

        
        oly_data_copy = oly.copy()
        
    return render_template('olympiad_run.html', 
                           olympiad_id=olympiad_id, 
                           oly_session=oly_data_copy, 
                           participant_id=participant_id)

@app.route('/olympiad/finish_early/<olympiad_id>', methods=['POST'])
def olympiad_finish_early(olympiad_id):

    with olympiad_lock:
        if olympiad_id not in olympiads or 'participant_id' not in session:
            return redirect(url_for('olympiad_join'))
        
        participant_id = session['participant_id']
        oly = olympiads[olympiad_id]

        if participant_id in oly['participants']:
            oly['participants'][participant_id]['finished_early'] = True
            oly['is_dirty'] = True
            flash('Вы успешно завершили олимпиаду.', 'success')
    
    current_state = _get_olympiad_state(olympiad_id)
    if current_state:
        socketio.emit('full_status_update', current_state, to=olympiad_id)

    
    return redirect(url_for('olympiad_end', olympiad_id=olympiad_id))

@app.route('/olympiad/end/<olympiad_id>')
def olympiad_end(olympiad_id):
    
    results_copy = None
    
    with olympiad_lock:
        if olympiad_id in olympiads:
            results_copy = olympiads[olympiad_id].copy()

    if results_copy:
        results = results_copy
        participants_list = []
        scoring_mode = results.get('config', {}).get('scoring', 'all_or_nothing')

        for p_id, p_data in results['participants'].items():
            

            total_score = 0
            total_penalty = 0
            
            if scoring_mode == 'icpc':
                total_score = sum(s['score'] for s in p_data['scores'].values()) # Кол-во решенных
                total_penalty = sum(s['penalty'] for s in p_data['scores'].values() if s['passed'])
            else:
                total_score = sum(s['score'] for s in p_data['scores'].values()) # Сумма баллов


            normalized_scores = {str(k): v for k, v in p_data['scores'].items()}
            
            participants_list.append({
                'nickname': p_data['nickname'],
                'organization': p_data.get('organization', None), 
                'scores': normalized_scores, 
                'total_score': total_score,
                'total_penalty': total_penalty, 
                'disqualified': p_data.get('disqualified', False)
            })
        

        if scoring_mode == 'icpc':
            participants_list.sort(key=lambda p: (p['total_score'], -p['total_penalty']), reverse=True)
        else:
            participants_list.sort(key=lambda p: p['total_score'], reverse=True)
        tasks_details = results['tasks_details']
        
    else:
        db_results = db.get_olympiad_results(olympiad_id)
        if not db_results:
             return "Олимпиада не найдена", 404
        
        results = db_results['results']
        tasks_details = db_results['tasks']
        participants_list = db_results['participants_list']

    is_organizer = session.get(f'is_organizer_for_{olympiad_id}', False)
    
    return render_template(
        'olympiad_end.html', 
        results=results, 
        tasks=tasks_details,
        participants_list=participants_list,
        is_organizer=is_organizer,
        olympiad_id=olympiad_id
    )
    


@app.route('/olympiad/status/<olympiad_id>')
def olympiad_status(olympiad_id):
    print("DEBUG: /olympiad/status/ был вызван (HTTP)")
    state = _get_olympiad_state(olympiad_id)
    if state:
        return jsonify(state)
    else:
        return jsonify({'error': 'not found'}), 404

    

@app.route('/olympiad/host/<olympiad_id>/disqualify/<participant_id>', methods=['POST'])
@admin_required
def olympiad_disqualify(olympiad_id, participant_id):
    """ОРГАНИЗАТОР: Дисквалифицирует участника."""
    
    nickname = "???"
    with olympiad_lock:
        if olympiad_id not in olympiads:
            return "Олимпиада не найдена", 404
            
        oly = olympiads[olympiad_id]
        
        if participant_id in oly['participants']:
            p_data = oly['participants'][participant_id]
            p_data['disqualified'] = True 
            oly['is_dirty'] = True
            p_data['finished_early'] = True 
            nickname = p_data['nickname']
            
            for task_id in p_data['scores']:
                 p_data['scores'][task_id]['score'] = 0 
                
            flash(f"Участник {nickname} был дисквалифицирован. Все баллы обнулены.", 'warning')
        else:
            flash('Участник не найден.', 'danger')

    current_state = _get_olympiad_state(olympiad_id)
    if current_state:
        socketio.emit('full_status_update', current_state, to=olympiad_id)
    
        
    return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))

@app.route('/olympiad/finish_by_host/<olympiad_id>', methods=['POST'])
@admin_required
def olympiad_finish_by_host(olympiad_id):
    
    oly_data_to_save = None
    
    with olympiad_lock:
        if olympiad_id in olympiads:
            olympiads[olympiad_id]['status'] = 'finished' 
            oly_data_to_save = olympiads[olympiad_id].copy()
            session.pop(f'is_organizer_for_{olympiad_id}', None)

            del olympiads[olympiad_id] 

    socketio.emit('olympiad_finished', {'status': 'finished'}, to=olympiad_id)
    
    if oly_data_to_save:
        db.save_olympiad_data(olympiad_id, oly_data_to_save)
        
        # --- [FIX] Ставим метку finished в БД ---
        try:
            db.mark_olympiad_finished(olympiad_id)
        except Exception as e:
            print(f"DB Error marking finished: {e}")
        # ----------------------------------------
        
        return jsonify({'status': 'ok', 'message': 'Олимпиада завершена.'})
        
    return jsonify({'status': 'error'}), 404

@app.route('/tasks/<int:task_id>/tests')
@admin_required
def tests_list(task_id):
    task = db.get_task_details(task_id)
    tests = db.get_tests_for_task(task_id)
    return render_template('tests.html', tests=tests, task=task)

@app.route('/tasks/<int:task_id>/tests/add', methods=['GET', 'POST'])
@admin_required
def add_test(task_id):
    if request.method == 'POST':
        test_input = request.form['test_input']
        expected_output = request.form['expected_output']
        time_limit = float(request.form.get('time_limit', 1.0))
        db.add_test(task_id, test_input, expected_output, time_limit)
        flash('Тест успешно добавлен!', 'success')
        return redirect(url_for('tests_list', task_id=task_id))
    
    task = db.get_task_details(task_id)
    return render_template('test_form.html', title="Добавить тест", task=task)

@app.route('/tasks/<int:task_id>/tests/edit/<int:test_id>', methods=['GET', 'POST'])
@admin_required
def edit_test(task_id, test_id):
    test = db.get_test_details(test_id)
    if request.method == 'POST':
        test_input = request.form['test_input']
        expected_output = request.form['expected_output']
        time_limit = float(request.form.get('time_limit', 1.0))
        db.update_test(test_id, test_input, expected_output, time_limit)
        flash('Тест успешно обновлен!', 'success')
        return redirect(url_for('tests_list', task_id=task_id))
        
    task = db.get_task_details(task_id)
    return render_template('test_form.html', title="Редактировать тест", task=task, test=test)

@app.route('/tasks/<int:task_id>/tests/delete/<int:test_id>', methods=['POST'])
@admin_required
def delete_test(task_id, test_id):
    db.delete_test(test_id)
    flash('Тест удален.', 'info')
    return redirect(url_for('tests_list', task_id=task_id))

@app.route('/tasks/<int:task_id>/tests/import_excel', methods=['POST'])
@admin_required
def import_tests_from_excel(task_id):
    
    if 'tests_file' not in request.files:
        flash('Файл не найден.', 'danger')
        return redirect(url_for('tests_list', task_id=task_id))
        
    file = request.files['tests_file']
    if file.filename == '':
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('tests_list', task_id=task_id))

    default_time_limit = float(request.form.get('time_limit_excel', 1.0))

    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            df = pd.read_excel(file, header=None) 
            
            if len(df.columns) < 2:
                flash('Ошибка формата: Ожидается 2 колонки (Ввод, Вывод).', 'danger')
                return redirect(url_for('tests_list', task_id=task_id))

            added_count = 0
            for index, row in df.iterrows():
                test_input = str(row.iloc[0])
                expected_output = str(row.iloc[1])
                
                if not test_input and not expected_output:
                    continue
                    
                db.add_test(task_id, test_input, expected_output, default_time_limit)
                added_count += 1
                    
            flash(f'Импорт завершен: {added_count} тестов успешно добавлено.', 'success')

        except Exception as e:
            flash(f'Ошибка при чтении файла Excel: {e}', 'danger')
    else:
        flash('Неверный формат файла. Нужен .xlsx или .xls', 'danger')
            
    return redirect(url_for('tests_list', task_id=task_id))


@app.route('/tasks/<int:task_id>/tests/import_zip', methods=['POST'])
@admin_required
def import_tests_from_zip(task_id):
    if 'zip_file' not in request.files:
        flash('Файл не найден.', 'danger')
        return redirect(url_for('tests_list', task_id=task_id))
        
    file = request.files['zip_file']
    if file.filename == '':
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('tests_list', task_id=task_id))

    default_time_limit = float(request.form.get('time_limit_zip', 1.0))
    added_count = 0

    if file and file.filename.endswith('.zip'):
        try:
            with zipfile.ZipFile(file, 'r') as z:
                all_files = z.namelist()
                all_files_set = set(all_files) # Для быстрого поиска
                test_pairs = {}
                
                # --- НОВАЯ ЛОГИКА ПОИСКА ПАР (01 и 01.a) ---
                for filename in all_files:
                    # Игнорируем папки и служебные файлы
                    if filename.endswith('/') or '__MACOSX' in filename:
                        continue
                    
                    base_name = os.path.basename(filename)
                    dir_name = os.path.dirname(filename)

                    # 1. Проверка формата: "XX.a" (вывод) -> "XX" (ввод)
                    if base_name.endswith('.a'):
                        input_base_name = base_name[:-2] # Убираем .a
                        # Формируем полный путь к предполагаемому вводу
                        expected_input_path = os.path.join(dir_name, input_base_name).replace("\\", "/")
                        
                        if expected_input_path in all_files_set:
                            # Нашли пару! Используем имя без расширения как ключ сортировки
                            test_pairs[expected_input_path] = {
                                'in': expected_input_path,
                                'out': filename
                            }
                            continue

                    # 2. (Опционально) Старая поддержка input_X.txt / output_X.txt
                    # Если нужно сохранить совместимость со старыми архивами
                    if "input_" in base_name:
                        expected_out_name = base_name.replace("input_", "output_")
                        full_out_path = os.path.join(dir_name, expected_out_name).replace("\\", "/")
                        if full_out_path in all_files_set:
                             test_pairs[filename] = {'in': filename, 'out': full_out_path}

                # Сортируем тесты, чтобы они добавлялись в правильном порядке
                # Пытаемся сортировать как числа, если имена числовые (01, 02...)
                def sort_key(k):
                    base = os.path.basename(k)
                    # Пытаемся извлечь число из начала файла
                    nums = re.findall(r'\d+', base)
                    if nums:
                        return int(nums[0])
                    return base

                sorted_keys = sorted(test_pairs.keys(), key=sort_key)
                
                for key in sorted_keys:
                    in_path = test_pairs[key]['in']
                    out_path = test_pairs[key]['out']

                    input_data = z.read(in_path).decode('utf-8', errors='replace').replace('\r\n', '\n').strip()
                    output_data = z.read(out_path).decode('utf-8', errors='replace').replace('\r\n', '\n').strip()
                    
                    if input_data or output_data:
                        db.add_test(task_id, input_data, output_data, default_time_limit)
                        added_count += 1

            if added_count > 0:
                flash(f'Успешно импортировано {added_count} тестов из ZIP-архива.', 'success')
            else:
                flash('Не найдено парных файлов (формат: 01 и 01.a) в архиве.', 'warning')

        except zipfile.BadZipFile:
            flash('Ошибка: Файл не является корректным ZIP-архивом.', 'danger')
        except Exception as e:
            flash(f'Ошибка при обработке ZIP: {e}', 'danger')
            print(f"ZIP Error: {e}")
    else:
        flash('Неверный формат. Нужен .zip', 'danger')
            
    return redirect(url_for('tests_list', task_id=task_id))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if check_password_hash(config.get('security', 'ADMIN_PASSWORD'), password):
            session['is_admin'] = True
            flash('Вы успешно вошли в систему!', 'success')
            return redirect(url_for('tasks_list'))
        else:
            flash('Неверный пароль.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))


@app.route('/tasks')
@admin_required
def tasks_list():
    tasks = db.get_tasks()
    return render_template('tasks.html', tasks=tasks)

@app.route('/admin/tasks/add', methods=['GET', 'POST'])
@admin_required
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        difficulty = request.form['difficulty']
        topic = request.form['topic']
        description = request.form['description']
        checker_code = request.form.get('checker_code', '') # Читаем чекер

        # Обработка файла (PDF и т.д.)
        file = request.files['attachment']
        attachment_data = None
        file_format = None
        if file and file.filename != '':
            attachment_data = file.read()
            file_format = file.filename.split('.')[-1].lower()

        # Передаем checker_code в БД
        db.add_task(title, difficulty, topic, description, attachment_data, file_format, checker_code)
        
        flash('Задача успешно добавлена!', 'success')
        return redirect(url_for('tasks_list'))
    
    return render_template('task_form.html', task=None)

@app.route('/admin/tasks/edit/<int:task_id>', methods=['GET', 'POST'])
@admin_required
def edit_task(task_id):
    task = db.get_task_details(task_id)
    if not task:
        flash('Задача не найдена', 'danger')
        return redirect(url_for('tasks_list'))

    if request.method == 'POST':
        title = request.form['title']
        difficulty = request.form['difficulty']
        topic = request.form['topic']
        description = request.form['description']
        checker_code = request.form.get('checker_code', '') # Читаем чекер

        file = request.files['attachment']
        attachment_data = None
        file_format = None
        
        if file and file.filename != '':
            attachment_data = file.read()
            file_format = file.filename.split('.')[-1].lower()

        # Обновляем (логика обновления в db_manager должна поддерживать checker_code)
        db.update_task(task_id, title, difficulty, topic, description, attachment_data, file_format, checker_code)
        
        flash('Задача обновлена!', 'success')
        return redirect(url_for('tasks_list'))

    return render_template('task_form.html', task=task)

@app.route('/tasks/delete/<int:task_id>', methods=['POST'])
@admin_required
def delete_task(task_id):
    db.delete_task(task_id)
    flash('Задача и все связанные с ней тесты удалены.', 'info')
    return redirect(url_for('tasks_list'))

@app.route('/tasks/view/<int:task_id>')
def view_task(task_id):
    task = db.get_task_details(task_id)
    if not task:
        abort(404) 
    tests = db.get_tests_for_task(task_id)
    return render_template('view_task.html', task=task, tests=tests)
    
@app.route('/tasks/<int:task_id>/attachment')
def display_attachment(task_id):
    task_data = db.get_task_details(task_id)
    if task_data and task_data[5]:
        attachment_data = task_data[5]
        file_format = task_data[6] or '' 

        mimetype = 'application/octet-stream' 
        if file_format == '.pdf':
            mimetype = 'application/pdf'
        elif file_format == '.html':
            mimetype = 'text/html'
        
        return send_file(io.BytesIO(attachment_data), mimetype=mimetype)
        
    return "Файл не найден", 404

@app.route('/olympiad/host/<olympiad_id>/add_participant', methods=['POST'])
@admin_required
def olympiad_add_participant(olympiad_id):

    if olympiad_id not in olympiads: 
        return "Олимпиада не найдена", 404

    nickname = request.form.get('nickname').strip()
    organization = request.form.get('organization').strip()
    password = request.form.get('password').strip()
    
    if not nickname or not password:
        flash('Никнейм и пароль обязательны.', 'danger')
        return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))
        
    success, message = db.add_participant_to_whitelist(olympiad_id, nickname, organization, password)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
        
    return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))


@app.route('/olympiad/host/<olympiad_id>/remove_participant/<int:participant_db_id>', methods=['POST'])
@admin_required
def olympiad_remove_participant(olympiad_id, participant_db_id):

    if olympiad_id not in olympiads:
        return "Олимпиада не найдена", 404
    
    if db.remove_participant_from_whitelist(participant_db_id):
        flash('Участник удален.', 'success')
    else:
        flash('Не удалось удалить участника.', 'danger')
        
    return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))


@app.route('/olympiad/host/<olympiad_id>/upload_participants', methods=['POST'])
@admin_required
def olympiad_upload_participants(olympiad_id): 
    if olympiad_id not in olympiads:
        return "Олимпиада не найдена", 404
    if 'participant_file' not in request.files:
        flash('Файл не найден.', 'danger')
        return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))
        
    file = request.files['participant_file']
    if file.filename == '':
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))

    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            df = pd.read_excel(file, header=None)
            
            if len(df.columns) < 3:
                flash('Ошибка формата: Ожидается 3 колонки (Никнейм, Организация, Пароль).', 'danger')
                return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))

            added_count = 0
            errors_count = 0
            
            for index, row in df.iterrows():
                nickname = str(row.iloc[0]).strip()
                organization = str(row.iloc[1]).strip()
                password = str(row.iloc[2]).strip()
                
                success, message = db.add_participant_to_whitelist(olympiad_id, nickname, organization, password)
                if success:
                    added_count += 1
                else:
                    errors_count += 1
                    
            flash(f'Импорт завершен: {added_count} участников добавлено, {errors_count} ошибок (возможно, дубликаты).', 'info')

        except Exception as e:
            flash(f'Ошибка при чтении файла Excel: {e}', 'danger')
    else:
        flash('Неверный формат файла. Нужен .xlsx или .xls', 'danger')
            
    return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))

@app.route('/admin/archive')
@admin_required
def admin_archive():
    """Список всех прошедших олимпиад."""
    olympiads_list = db.get_all_olympiads_list()
    return render_template('admin_archive.html', olympiads=olympiads_list)

@app.route('/admin/archive/view/<olympiad_id>')
@admin_required
def admin_archive_view(olympiad_id):
    """Детальный просмотр результатов олимпиады с кодом."""
    data = db.get_olympiad_results(olympiad_id)
    if not data:
        flash('Олимпиада не найдена или данных нет.', 'warning')
        return redirect(url_for('admin_archive'))
    
    return render_template('admin_results_view.html', 
                           results=data['results'], 
                           tasks=data['tasks'], 
                           participants_list=data['participants_list'],
                           olympiad_id=olympiad_id)

@app.route('/admin/archive/delete/<olympiad_id>', methods=['POST'])
@admin_required
def admin_archive_delete(olympiad_id):
    """Удаление олимпиады из базы."""
    if db.delete_olympiad_history(olympiad_id):
        flash(f'Олимпиада {olympiad_id} успешно удалена.', 'success')
    else:
        flash('Ошибка при удалении.', 'danger')
    return redirect(url_for('admin_archive'))

@app.route('/admin/archive/export/<olympiad_id>')
@admin_required
def admin_archive_export(olympiad_id):
    """Экспорт в Excel."""
    data = db.get_olympiad_results(olympiad_id)
    if not data:
        return "Нет данных", 404
        
    participants = data['participants_list']
    tasks = data['tasks']
    scoring = data['results']['config']['scoring']

    export_data = []
    for p in participants:
        row = {
            'Никнейм': p['nickname'],
            'Организация': p.get('organization', ''),
            'Итого баллов': p['total_score']
        }
        if scoring == 'icpc':
             row['Штраф'] = p['total_penalty']
             row['Решено'] = p.get('solved_count', 0)

        scores = p['scores']
        for t in tasks:
            tid = t[0]
            t_score = scores.get(tid) or scores.get(str(tid)) or {}
            
            header = f"Задача {t[1]} ({t[0]})"
            
            if scoring == 'icpc':
                val = ""
                if t_score.get('passed'):
                    val = f"+{t_score.get('attempts', 0) if t_score.get('attempts', 0) > 0 else ''}"
                elif t_score.get('attempts', 0) > 0:
                    val = f"-{t_score['attempts']}"
                else:
                    val = "."
                row[header] = val
            else:
                row[header] = t_score.get('score', 0)
                
        export_data.append(row)

    df = pd.DataFrame(export_data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Results')
        
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'results_{olympiad_id}.xlsx'
    )

@app.route('/olympiad/api/history/<olympiad_id>')
def api_get_history(olympiad_id):
    participant_id = session.get('participant_id')
    if not participant_id:
        return jsonify([])
    
    raw_history = db.get_participant_history(olympiad_id, participant_id)

    tasks_order = []
    with olympiad_lock:
        if olympiad_id in olympiads:
            tasks_order = olympiads[olympiad_id]['task_ids']
    
    history_json = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    
    for row in raw_history:
        tid = row[0]
        letter = "?"
        if tid in tasks_order:
            idx = tasks_order.index(tid)
            if idx < len(letters):
                letter = letters[idx]

        t_struct = time.localtime(row[5])
        time_str = time.strftime("%H:%M:%S", t_struct)
        
        history_json.append({
            'letter': letter,
            'time': time_str,
            'language': row[1],
            'verdict': row[2],
            'tests': f"{row[3]} / {row[4]}"
        })
        
    return jsonify(history_json)

@app.route('/olympiad/api/scoreboard/<olympiad_id>')
def api_get_scoreboard(olympiad_id):
    state = _get_olympiad_state(olympiad_id)
    if not state:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(state)


def restore_state_on_startup():
    """Вызывается из run.py для восстановления олимпиад и загрузки планов."""
    print("INFO: Восстановление состояния олимпиад...")
    try:
        # 1. Восстанавливаем активные (как было раньше)
        active_data = db.get_all_active_olympiads_data()
        current_time = time.time()
        
        with olympiad_lock:
            for oid, data in active_data.items():
                if data['status'] == 'running' and data['start_time']:
                    duration_sec = data['config']['duration_minutes'] * 60
                    if (current_time - data['start_time']) > (duration_sec + 3600):
                        continue
                olympiads[oid] = data

            # 2. Загружаем запланированные
            scheduled = db.get_all_scheduled_olympiads()
            for row in scheduled:
                oid = row['olympiad_id']
                # Если олимпиада уже есть в памяти (например, она активна), пропускаем
                if oid in olympiads:
                    continue
                
                config = json.loads(row['config_json'])
                task_ids = json.loads(row['task_ids_json'])
                
                olympiads[oid] = {
                    'status': 'scheduled', # Новый статус
                    'name': row['name'], # Название для удобства
                    'task_ids': task_ids,
                    'tasks_details': [db.get_task_details(tid) for tid in task_ids],
                    'config': config,
                    'start_time': row['start_time'], # Это время запланированного старта
                    'participants': {},
                    'is_dirty': True,
                    'first_solves': {},
                    'cached_state': None
                }
                print(f"INFO: Загружена запланированная олимпиада {oid} на {row['start_time']}")

        print(f"SUCCESS: Состояние восстановлено.")
    except Exception as e:
        print(f"ERROR: Ошибка восстановления состояния: {e}")
        import traceback
        traceback.print_exc()


@app.route('/olympiad/edit_time/<olympiad_id>', methods=['POST'])
@admin_required
def olympiad_edit_time(olympiad_id):
    new_time_str = request.form.get('new_time')
    if not new_time_str:
        return redirect(url_for('olympiad_index'))
    
    with olympiad_lock:
        if olympiad_id in olympiads:
            try:
                dt = datetime.strptime(new_time_str, "%Y-%m-%dT%H:%M")
                ts = dt.timestamp()
                olympiads[olympiad_id]['start_time'] = ts

                if olympiads[olympiad_id]['status'] == 'running':
                    db.set_olympiad_start_time(olympiad_id, ts)
                else:
                    db.update_scheduled_time(olympiad_id, ts)
                
                flash('Время старта обновлено.', 'success')
            except ValueError:
                flash('Ошибка формата времени', 'danger')
    return redirect(url_for('olympiad_index'))

@app.route('/olympiad/print_cards/<olympiad_id>')
@admin_required
def olympiad_print_cards(olympiad_id):
    """Генерация страницы для печати карточек участников."""
    whitelist = db.get_whitelist_for_olympiad(olympiad_id)
    if not whitelist:
        flash('В этой олимпиаде нет зарегистрированных участников (whitelist).', 'warning')
        return redirect(url_for('olympiad_host', olympiad_id=olympiad_id))
    
    # Получаем название олимпиады
    oly_name = olympiad_id
    with olympiad_lock:
        if olympiad_id in olympiads:
            oly_name = olympiads[olympiad_id].get('name', olympiad_id)

    return render_template('print_cards.html', 
                           whitelist=whitelist, 
                           olympiad_id=olympiad_id,
                           olympiad_name=oly_name)