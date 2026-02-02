import requests
import threading
import time
import random

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # Отключаем спам предупреждениями

URL = "https://127.0.0.1/run_code" # Порт 443 дефолтный, писать не нужно. HTTPS обязательно.
CONCURRENT_USERS = 20  # Сколько "студентов" жмут кнопку одновременно
TOTAL_REQUESTS = 100    # Сколько всего запросов отправить

# Простой код, который сервер должен выполнить
CODE_PYTHON = """
n = int(input())


a = [int(i) for i in input().split()]
turn = True
aisara = 0
bauyr = 0
i = 0
j = n - 1
while i <= j:
    if turn:
        if a[i] >= a[j]:
            aisara += a[i]
            i+=1
        else:
            aisara += a[j]
            j-=1
        turn = False
    else:
        if a[i] >= a[j]:
            bauyr += a[i]
            i+=1
        else:
            bauyr += a[j]
            j-=1
        turn = True
print("Aisara" if aisara > bauyr else "Bauyr")
"""

# Нужно указать ID существующей задачи! 
# Посмотрите в базе или на сайте (например, ID=1)
TASK_ID = 34 

success_count = 0
error_count = 0
start_time = 0

def send_request(user_id):
    global success_count, error_count
    try:
        # Небольшая задержка, чтобы имитировать разную скорость нажатия
        time.sleep(random.random() * 2)
        
        print(f"User {user_id}: Отправка решения...")
        resp = requests.post(URL, json={
            "task_id": TASK_ID,
            "language": "Python",
            "code": CODE_PYTHON
        }, timeout=60) # Таймаут ожидания ответа (очередь может быть долгой)

        if resp.status_code == 200:
            data = resp.json()
            if 'passed_count' in data:
                print(f"User {user_id}: ✅ УСПЕХ (Тестов: {data['total_tests']})")
                success_count += 1
            else:
                print(f"User {user_id}: ⚠️ ОШИБКА ЛОГИКИ: {data}")
                error_count += 1
        else:
            print(f"User {user_id}: ❌ ОШИБКА HTTP {resp.status_code}: {resp.text}")
            error_count += 1

    except Exception as e:
        print(f"User {user_id}: 💥 ИСКЛЮЧЕНИЕ: {e}")
        error_count += 1

def run_stress_test():
    global start_time
    print(f"--- ЗАПУСК СТРЕСС-ТЕСТА ---")
    print(f"Потоков: {CONCURRENT_USERS}, Всего запросов: {TOTAL_REQUESTS}")
    print(f"Цель: {URL}")
    print("---------------------------")
    
    start_time = time.time()
    threads = []
    
    # Запускаем пачки потоков
    for i in range(TOTAL_REQUESTS):
        t = threading.Thread(target=send_request, args=(i,))
        threads.append(t)
        t.start()
        
        # Ограничиваем количество одновременных потоков, чтобы скрипт не упал сам
        while threading.active_count() > CONCURRENT_USERS:
            time.sleep(0.1)

    # Ждем завершения всех
    for t in threads:
        t.join()

    duration = time.time() - start_time
    print("\n--- РЕЗУЛЬТАТЫ ---")
    print(f"Всего запросов: {TOTAL_REQUESTS}")
    print(f"Успешно: {success_count}")
    print(f"Ошибок: {error_count}")
    print(f"Время выполнения: {duration:.2f} сек")
    print(f"Среднее время на запрос: {duration/TOTAL_REQUESTS:.2f} сек")

if __name__ == "__main__":
    run_stress_test()
