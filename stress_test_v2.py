import requests
import threading
import time
import random

# НАСТРОЙКИ
# Если запускаете тест с того же ноутбука, где сервер - используйте 127.0.0.1
# Если с другого - укажите реальный IP сервера
URL_SUBMIT = "http://127.0.0.1:5000/run_code" 
CONCURRENT_USERS = 100  # Имитируем полную посадку
TOTAL_SUBMISSIONS = 500 # Общее количество решений за тест

# Простейший код (Python), чтобы Docker быстро отработал
CODE_PYTHON = "print(sum(int(x) for x in input().split()))"

# ID задачи, которая реально существует в вашей БД (например, A+B)
TASK_ID = 1 

success_count = 0
error_count = 0
start_time = 0

def student_behavior(user_id):
    global success_count, error_count
    
    # Имитация: студент думает перед отправкой (разброс 0-10 секунд)
    time.sleep(random.random() * 10)
    
    try:
        # print(f"Student {user_id}: Отправляет решение...")
        resp = requests.post(URL_SUBMIT, json={
            "task_id": TASK_ID,
            "language": "Python",
            "code": CODE_PYTHON
        }, timeout=120) # Большой таймаут, так как очередь может быть длинной

        if resp.status_code == 200:
            data = resp.json()
            # Проверяем, что сервер вернул хоть какой-то вердикт
            if 'passed_count' in data or 'verdict' in data:
                success_count += 1
            else:
                print(f"Student {user_id}: ⚠️ Странный ответ: {data}")
                error_count += 1
        else:
            print(f"Student {user_id}: ❌ HTTP {resp.status_code}")
            error_count += 1

    except Exception as e:
        print(f"Student {user_id}: 💥 Ошибка сети: {e}")
        error_count += 1

def run_stress_test():
    global start_time
    print(f"--- НАЧАЛО СТРЕСС-ТЕСТА (100 потоков) ---")
    print(f"Цель: Проверить, не упадет ли база и Docker.")
    
    start_time = time.time()
    threads = []
    
    # Запускаем "волну" студентов
    for i in range(TOTAL_SUBMISSIONS):
        t = threading.Thread(target=student_behavior, args=(i,))
        threads.append(t)
        t.start()
        
        # Держим не более 100 активных "студентов" одновременно
        while threading.active_count() > CONCURRENT_USERS:
            time.sleep(0.1)

    # Ждем завершения всех
    for t in threads:
        t.join()

    duration = time.time() - start_time
    print("\n" + "="*40)
    print(f"ИТОГИ ТЕСТА:")
    print(f"Всего попыток: {TOTAL_SUBMISSIONS}")
    print(f"Успешно обработано: {success_count}")
    print(f"Ошибок/Таймаутов: {error_count}")
    print(f"Общее время: {duration:.2f} сек")
    print(f"Скорость сервера: {success_count / duration:.2f} решений/сек")
    print("="*40)

    if error_count == 0:
        print("✅ ВЕРДИКТ: Система готова к нагрузке!")
    else:
        print("⚠️ ВЕРДИКТ: Есть ошибки. Проверьте логи и уменьшите MAX_CHECKS.")

if __name__ == "__main__":
    run_stress_test()