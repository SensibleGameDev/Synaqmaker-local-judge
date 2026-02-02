import sys
import os
import sqlite3
import subprocess
import tempfile
import json
import platform
import shutil 
import time
from threading import RLock

# НАСТРОЙКИ DOCKER
DOCKER_IMAGE_PYTHON = "testirovschik-python"
DOCKER_IMAGE_CPP = "testirovschik-cpp"
DOCKER_IMAGE_CSHARP = "testirovschik-csharp"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, 'judge_scripts')

DOCKER_COMMON_ARGS = [
    "docker", "run",
    "--rm",             
    "--network=none",   
    "--memory=256m",
    "--memory-swap=256m",
    "--cpus=1.0",
    "--cap-drop=ALL",
    "--pids-limit=64",
    "--ulimit", "fsize=10000000",
    "--user=appuser",   
    "-w", "/home/appuser/run" 
]

def load_judge_script(filename):
    path = os.path.join(SCRIPTS_DIR, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""

def _get_docker_path(abs_path):
    if platform.system() == "Windows":
         abs_path = abs_path.replace("\\", "/")
         if len(abs_path) > 1 and abs_path[1] == ":":
            abs_path = "/" + abs_path[0].lower() + abs_path[2:]
    return abs_path

class DBManager:
    def __init__(self, db_name="testirovschik.db"):
        self.db_name = db_name
        # Блокировка ТОЛЬКО для записи. Чтение работает параллельно.
        self.write_lock = RLock()
        
        # Инициализация режима WAL (Write-Ahead Logging) для параллелизма
        try:
            with self._get_conn() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
        except Exception as e:
            print(f"DB Init Error: {e}")
        
        self.create_tables()
        self._create_olympiad_tables()

    def _get_conn(self):
        """
        Создает изолированное соединение для каждого запроса.
        Позволяет избежать DB Lock Bottleneck при чтении.
        """
        # Timeout 60s важен для очереди на запись при 100 участниках
        conn = sqlite3.connect(self.db_name, timeout=60.0, check_same_thread=False)
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-64000;") # ~64MB кэша
        conn.row_factory = sqlite3.Row
        return conn

    # === ИСТОРИЯ (Запись - нужен лок) ===
    def add_to_history(self, olympiad_id, participant_id, task_id, language, verdict, tests_passed, total_tests):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO olympiad_history 
                    (olympiad_id, participant_id, task_id, language, verdict, tests_passed, total_tests, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (olympiad_id, participant_id, task_id, language, verdict, tests_passed, total_tests, time.time()))
                conn.commit()

    # === ИСТОРИЯ (Чтение - без лока) ===
    def get_participant_history(self, olympiad_id, participant_id):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT task_id, language, verdict, tests_passed, total_tests, timestamp
                FROM olympiad_history
                WHERE olympiad_id = ? AND participant_id = ?
                ORDER BY id DESC
            """, (olympiad_id, participant_id))
            return c.fetchall()

    def _create_olympiad_tables(self):
        with self.write_lock:
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute('''CREATE TABLE IF NOT EXISTS olympiad_results (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                olympiad_id TEXT NOT NULL,
                                participant_uuid TEXT NOT NULL,
                                nickname TEXT NOT NULL,
                                total_score INTEGER,
                                task_scores TEXT, 
                                organization TEXT,
                                disqualified BOOLEAN DEFAULT 0,
                                UNIQUE(olympiad_id, participant_uuid)
                            )''')
                
                c.execute('''CREATE TABLE IF NOT EXISTS olympiad_configs (
                                olympiad_id TEXT PRIMARY KEY,
                                task_ids_json TEXT,
                                name TEXT,
                                status TEXT DEFAULT 'waiting',
                                duration_minutes INTEGER DEFAULT 300,
                                scoring_type TEXT DEFAULT 'icpc',
                                start_time REAL
                            )''')
                
                # Миграции
                c.execute("PRAGMA table_info(olympiad_configs)")
                cols = [col[1] for col in c.fetchall()]
                if "name" not in cols: c.execute("ALTER TABLE olympiad_configs ADD COLUMN name TEXT")
                if "status" not in cols: c.execute("ALTER TABLE olympiad_configs ADD COLUMN status TEXT DEFAULT 'waiting'")
                if "duration_minutes" not in cols: c.execute("ALTER TABLE olympiad_configs ADD COLUMN duration_minutes INTEGER DEFAULT 300")
                if "scoring_type" not in cols: c.execute("ALTER TABLE olympiad_configs ADD COLUMN scoring_type TEXT DEFAULT 'icpc'")
                if "start_time" not in cols: c.execute("ALTER TABLE olympiad_configs ADD COLUMN start_time REAL")
                if "allowed_languages" not in cols: c.execute("ALTER TABLE olympiad_configs ADD COLUMN allowed_languages TEXT")

                c.execute('''CREATE TABLE IF NOT EXISTS olympiad_submissions (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                olympiad_id TEXT NOT NULL,
                                participant_uuid TEXT NOT NULL,
                                nickname TEXT NOT NULL,
                                task_submissions TEXT, 
                                UNIQUE(olympiad_id, participant_uuid)
                            )''')
                
                c.execute('''CREATE TABLE IF NOT EXISTS olympiad_whitelist (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                olympiad_id TEXT NOT NULL,
                                nickname TEXT NOT NULL,
                                organization TEXT,
                                password TEXT NOT NULL,
                                UNIQUE(olympiad_id, nickname) 
                            )''')

                c.execute('''CREATE TABLE IF NOT EXISTS olympiad_history (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                olympiad_id TEXT NOT NULL,
                                participant_id TEXT NOT NULL,
                                task_id INTEGER NOT NULL,
                                language TEXT,
                                verdict TEXT,
                                tests_passed INTEGER,
                                total_tests INTEGER,
                                timestamp REAL
                            )''')
                c.execute('''CREATE TABLE IF NOT EXISTS scheduled_olympiads (
                                olympiad_id TEXT PRIMARY KEY,
                                name TEXT,
                                start_time REAL,
                                config_json TEXT,
                                task_ids_json TEXT
                            )''')
                conn.commit()

    def save_olympiad_config(self, olympiad_id, task_ids_list, name=None, duration=None, scoring=None, allowed_languages=None):
        ids_json = json.dumps(task_ids_list)
        languages_json = json.dumps(allowed_languages) if allowed_languages else None
        with self.write_lock:
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("SELECT olympiad_id FROM olympiad_configs WHERE olympiad_id=?", (olympiad_id,))
                exists = c.fetchone()
                
                if exists:
                    query = "UPDATE olympiad_configs SET task_ids_json=?"
                    params = [ids_json]
                    if name: 
                        query += ", name=?"
                        params.append(name)
                    if duration:
                        query += ", duration_minutes=?"
                        params.append(duration)
                    if scoring:
                        query += ", scoring_type=?"
                        params.append(scoring)
                    if languages_json:
                        query += ", allowed_languages=?"
                        params.append(languages_json)
                    query += " WHERE olympiad_id=?"
                    params.append(olympiad_id)
                    c.execute(query, tuple(params))
                else:
                    c.execute("""
                        INSERT INTO olympiad_configs (olympiad_id, task_ids_json, name, duration_minutes, scoring_type, allowed_languages)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (olympiad_id, ids_json, name, duration or 300, scoring or 'icpc', languages_json))
                conn.commit()
    
    def set_olympiad_start_time(self, olympiad_id, start_time):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("UPDATE olympiad_configs SET start_time = ?, status = 'running' WHERE olympiad_id = ?", 
                          (start_time, olympiad_id))
                conn.commit()

    def save_olympiad_data(self, olympiad_id, olympiad_data):
        with self.write_lock:
            with self._get_conn() as conn:
                c = conn.cursor()
                participants = olympiad_data.get('participants', {})
                for p_uuid, p_data in participants.items():
                    nickname = p_data.get('nickname')
                    organization = p_data.get('organization', None) 
                    disqualified = p_data.get('disqualified', False)
                    scores = p_data.get('scores', {})
                    
                    total_score = sum(s.get('score', 0) for s in scores.values())
                    task_scores_json = json.dumps(scores) 
                    
                    c.execute("""
                        INSERT INTO olympiad_results (olympiad_id, participant_uuid, nickname, organization, total_score, task_scores, disqualified)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(olympiad_id, participant_uuid) DO UPDATE SET
                        organization=excluded.organization, total_score=excluded.total_score, task_scores=excluded.task_scores,
                        disqualified=excluded.disqualified
                    """, (olympiad_id, p_uuid, nickname, organization, total_score, task_scores_json, disqualified))
                    
                    submissions = p_data.get('last_submissions', {})
                    submissions_json = json.dumps(submissions)
                    c.execute("""
                        INSERT INTO olympiad_submissions (olympiad_id, participant_uuid, nickname, task_submissions)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(olympiad_id, participant_uuid) DO UPDATE SET
                        task_submissions=excluded.task_submissions
                    """, (olympiad_id, p_uuid, nickname, submissions_json))
                conn.commit()

    def get_first_solvers(self, olympiad_id):
        with self._get_conn() as conn:
            c = conn.cursor()
            query = """
                SELECT task_id, participant_id
                FROM olympiad_history
                WHERE olympiad_id = ? AND (verdict = 'OK' OR verdict = 'Accepted')
                GROUP BY task_id
                HAVING timestamp = MIN(timestamp)
            """
            c.execute(query, (olympiad_id,))
            return {int(r[0]): r[1] for r in c.fetchall()}
    
    def get_olympiad_results(self, olympiad_id):
        # Оптимизированная версия для Скорборда с авто-исправлением типа скоринга
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM olympiad_results WHERE olympiad_id = ?", (olympiad_id,))
            participants_raw = c.fetchall()
            if not participants_raw: return None 

            c.execute("SELECT participant_uuid, task_submissions FROM olympiad_submissions WHERE olympiad_id = ?", (olympiad_id,))
            submissions_raw = c.fetchall()
            submissions_map = {s['participant_uuid']: json.loads(s['task_submissions']) for s in submissions_raw if s['task_submissions']}

            c.execute("SELECT * FROM olympiad_configs WHERE olympiad_id = ?", (olympiad_id,))
            config_row = c.fetchone()
            
            # Читаем тип из БД, но если там ошибка - исправим ниже
            scoring_type = config_row['scoring_type'] if config_row and config_row['scoring_type'] else 'icpc'

            participants_list = []
            task_ids_set = set()
            
            # [FIX] Флаг для автоопределения IOI (если были баллы > 1)
            looks_like_ioi = False
            
            for p in participants_raw:
                scores_full = json.loads(p['task_scores']) 

                # [FIX START] Исправление дублирования ключей (str vs int)
                scores_fixed = {}
                for k, v in scores_full.items():
                    try:
                        int_k = int(k)
                    except (ValueError, TypeError):
                        int_k = k
                    
                    # [FIX] Гарантируем правильную структуру данных
                    if isinstance(v, dict):
                        scores_fixed[int_k] = v
                    else:
                        # Если это просто число (старый формат), преобразуем
                        scores_fixed[int_k] = {'score': int(v) if isinstance(v, (int, float)) else 0, 'attempts': 0, 'passed': False, 'penalty': 0}
                scores_full = scores_fixed
                # [FIX END]

                task_ids_set.update(scores_full.keys())
                uuid = p['participant_uuid']
                user_code = submissions_map.get(uuid, {})
                
                total_score_calc = 0
                total_penalty_calc = 0
                solved_count = 0
                
                for tid, info in scores_full.items():
                    if isinstance(info, int):
                        info = {'score': info, 'attempts': 0, 'passed': False, 'penalty': 0}
                        scores_full[tid] = info
                    
                    s_val = info.get('score', 0)
                    total_score_calc += s_val
                    
                    # Если видим баллы > 1, значит это точно не ICPC (там обычно 1 или 0)
                    if s_val > 1:
                        looks_like_ioi = True

                    if info.get('passed'):
                        total_penalty_calc += info.get('penalty', 0)
                        solved_count += 1

                participants_list.append({
                    'participant_uuid': uuid,
                    'nickname': p['nickname'],
                    'organization': p['organization'],
                    'scores': scores_full,
                    'submissions': user_code,
                    'total_score': total_score_calc,
                    'total_penalty': total_penalty_calc,
                    'solved_count': solved_count,  # [FIX] Добавлено для ICPC
                    'disqualified': p['disqualified'] 
                })

                # [FIX] Для ICPC: total_score должен быть кол-во решенных задач, а не баллов
                if scoring_type == 'icpc' and looks_like_ioi:
                    for p_item in participants_list:
                        p_item['total_score'] = p_item['solved_count']

            # [FIX] Применяем авто-исправление типа скоринга
            if scoring_type == 'icpc' and looks_like_ioi:
                scoring_type = 'points'
                
            task_ids_list = []
            status = 'finished'
            if config_row:
                status = config_row['status']
                try:
                    saved_ids = json.loads(config_row['task_ids_json'])
                    for tid in saved_ids:
                        try:
                            task_ids_list.append(int(tid))
                        except (ValueError, TypeError):
                            task_ids_list.append(tid)
                except:
                    task_ids_list = sorted([int(x) if isinstance(x, int) else int(x) for x in task_ids_set])
            else:
                task_ids_list = sorted([int(x) if isinstance(x, int) else int(x) for x in task_ids_set])

            tasks_details = []
            for tid in task_ids_list:
                task_row = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
                if task_row:
                    tasks_details.append(task_row)
            
            # Сортировка зависит от итогового scoring_type
            if scoring_type == 'icpc':
                participants_list.sort(key=lambda p: (-p['solved_count'], p['total_penalty']))
            else:
                participants_list.sort(key=lambda p: -p['total_score'])
            
            return {
                'results': {
                    'status': status, 
                    'config': {'olympiad_id': olympiad_id, 'scoring': scoring_type},
                    'first_solves': self.get_first_solvers(olympiad_id)
                }, 
                'tasks': tasks_details,
                'participants_list': participants_list
            }
    
    def create_tables(self):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 title TEXT, difficulty TEXT, topic TEXT, description TEXT,
                                 attachment BLOB, file_format TEXT, checker_code TEXT
                               )''')
                conn.execute('''CREATE TABLE IF NOT EXISTS tests (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER,
                                 test_input TEXT, expected_output TEXT, time_limit REAL,
                                 FOREIGN KEY(task_id) REFERENCES tasks(id)
                               )''')
                conn.execute('''CREATE TABLE IF NOT EXISTS submissions (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER,
                                 language TEXT, code TEXT, result TEXT,
                                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 FOREIGN KEY(task_id) REFERENCES tasks(id)
                               )''')
                conn.commit()
    
    def add_submission(self, task_id, language, code, result):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("INSERT INTO submissions (task_id, language, code, result) VALUES (?,?,?,?)",
                          (task_id, language, code, result))
                conn.commit()

    def get_all_olympiads_list(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT r.olympiad_id, COUNT(r.id) as participants_count, c.name, c.status
                FROM olympiad_results r
                LEFT JOIN olympiad_configs c ON r.olympiad_id = c.olympiad_id
                GROUP BY r.olympiad_id 
                ORDER BY r.id DESC
            """)
            return c.fetchall()
    
    def delete_olympiad_history(self, olympiad_id):
        with self.write_lock:
            try:
                with self._get_conn() as conn:
                    conn.execute("DELETE FROM olympiad_results WHERE olympiad_id = ?", (olympiad_id,))
                    conn.execute("DELETE FROM olympiad_submissions WHERE olympiad_id = ?", (olympiad_id,))
                    conn.execute("DELETE FROM olympiad_configs WHERE olympiad_id = ?", (olympiad_id,))
                    conn.execute("DELETE FROM olympiad_history WHERE olympiad_id = ?", (olympiad_id,))
                    conn.commit()
                return True
            except: return False
        
    def get_whitelist_for_olympiad(self, olympiad_id):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, nickname, organization, password FROM olympiad_whitelist WHERE olympiad_id = ? ORDER BY nickname", (olympiad_id,))
            return c.fetchall()

    def add_participant_to_whitelist(self, olympiad_id, nickname, organization, password):
        with self.write_lock:
            try:
                with self._get_conn() as conn:
                    conn.execute("INSERT INTO olympiad_whitelist (olympiad_id, nickname, organization, password) VALUES (?, ?, ?, ?)", 
                              (olympiad_id, nickname, organization, password))
                    conn.commit()
                return (True, f"Участник {nickname} добавлен.")
            except sqlite3.IntegrityError:
                return (False, f"Ошибка: Участник {nickname} уже есть.")
            except Exception as e:
                return (False, str(e))

    def remove_participant_from_whitelist(self, participant_db_id):
        with self.write_lock:
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM olympiad_whitelist WHERE id = ?", (participant_db_id,))
                conn.commit()
                return c.rowcount > 0 

    def validate_closed_participant(self, olympiad_id, nickname, password):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM olympiad_whitelist WHERE olympiad_id = ? AND nickname = ? AND password = ?", (olympiad_id, nickname, password))
            return c.fetchone()
        
    def add_task(self, title, difficulty, topic, description, attachment, file_format, checker_code=None):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("INSERT INTO tasks (title, difficulty, topic, description, attachment, file_format, checker_code) VALUES (?,?,?,?,?,?,?)",
                          (title, difficulty, topic, description, attachment, file_format, checker_code))
                conn.commit()

    def get_tasks(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, title, difficulty, topic FROM tasks ORDER BY id DESC")
            return c.fetchall()

    def get_task_details(self, task_id):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
            return c.fetchone()

    def update_task(self, task_id, title, difficulty, topic, description, attachment, file_format, checker_code=None):
        with self.write_lock:
            with self._get_conn() as conn:
                if attachment and file_format:
                     conn.execute("UPDATE tasks SET title=?, difficulty=?, topic=?, description=?, attachment=?, file_format=?, checker_code=? WHERE id=?",
                               (title, difficulty, topic, description, attachment, file_format, checker_code, task_id))
                else:
                    conn.execute("UPDATE tasks SET title=?, difficulty=?, topic=?, description=?, checker_code=? WHERE id=?",
                               (title, difficulty, topic, description, checker_code, task_id))
                conn.commit()

    def mark_olympiad_finished(self, olympiad_id):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("UPDATE olympiad_configs SET status = 'finished' WHERE olympiad_id = ?", (olympiad_id,))
                conn.commit()

    def delete_task(self, task_id):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM tests WHERE task_id=?", (task_id,))
                conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
                conn.commit()

    def add_test(self, task_id, test_input, expected_output, time_limit):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("INSERT INTO tests (task_id, test_input, expected_output, time_limit) VALUES (?,?,?,?)",
                          (task_id, test_input, expected_output, time_limit))
                conn.commit()

    def get_tests_for_task(self, task_id):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, test_input, expected_output, time_limit FROM tests WHERE task_id=?", (task_id,))
            return c.fetchall()

    def get_test_details(self, test_id):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM tests WHERE id=?", (test_id,))
            return c.fetchone()

    def update_test(self, test_id, test_input, expected_output, time_limit):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("UPDATE tests SET test_input=?, expected_output=?, time_limit=? WHERE id=?", (test_input, expected_output, time_limit, test_id))
                conn.commit()

    def delete_test(self, test_id):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM tests WHERE id=?", (test_id,))
                conn.commit()
    
    def get_participant_progress(self, olympiad_id, participant_uuid):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT task_scores, disqualified, organization FROM olympiad_results WHERE olympiad_id = ? AND participant_uuid = ?", (olympiad_id, participant_uuid))
            row_res = c.fetchone()
            if not row_res: return None
            
            c.execute("SELECT task_submissions FROM olympiad_submissions WHERE olympiad_id = ? AND participant_uuid = ?", (olympiad_id, participant_uuid))
            row_sub = c.fetchone()
            last_submissions = json.loads(row_sub['task_submissions']) if row_sub and row_sub['task_submissions'] else {}
            raw_scores = json.loads(row_res['task_scores'])
            # [FIX START] Принудительная конвертация ключей в int
            scores_fixed = {}
            for k, v in raw_scores.items():
                try:
                    scores_fixed[int(k)] = v
                except ValueError:
                    scores_fixed[k] = v
            # [FIX END]
            return {
                'scores': scores_fixed,
                'disqualified': row_res['disqualified'],
                'organization': row_res['organization'],
                'last_submissions': last_submissions
            }

    # === ВОССТАНОВЛЕНИЕ (Чтение) ===
    def get_all_active_olympiads_data(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM olympiad_configs WHERE status IS NOT 'finished'")
            configs = c.fetchall()
        
        # Здесь мы уже вышли из контекста conn, поэтому можно вызывать get_olympiad_results
        restored = {}
        for row in configs:
            oid = row['olympiad_id']
            res = self.get_olympiad_results(oid) 
            if not res: continue

            start_time = row['start_time']
            status = row['status']

            if not start_time:
                # Временное соединение для проверки истории
                with self._get_conn() as conn_hist:
                    c_h = conn_hist.cursor()
                    c_h.execute("SELECT MIN(timestamp) FROM olympiad_history WHERE olympiad_id=?", (oid,))
                    res_ts = c_h.fetchone()
                    if res_ts and res_ts[0]:
                        start_time = res_ts[0]
                        status = 'running'

            parts = {}
            for p in res['participants_list']:
                task_ids = json.loads(row['task_ids_json'])
                last_subs = p.get('submissions') or {str(t):"" for t in task_ids}
                parts[p['participant_uuid']] = {
                    'nickname': p['nickname'],
                    'organization': p.get('organization'),
                    'scores': p['scores'],
                    'last_submissions': last_subs,
                    'finished_early': False,
                    'disqualified': p.get('disqualified', False),
                    'pending_submissions': 0
                }

            # Parse allowed_languages from DB (if exists)
            allowed_languages_raw = None
            try:
                allowed_languages_raw = row['allowed_languages']
            except (KeyError, IndexError):
                pass
            allowed_languages = json.loads(allowed_languages_raw) if allowed_languages_raw else ['Python', 'C++', 'C#']

            restored[oid] = {
                'status': status,
                'task_ids': json.loads(row['task_ids_json']),
                'tasks_details': res['tasks'],
                'config': {
                    'duration_minutes': row['duration_minutes'] or 300, 
                    'scoring': row['scoring_type'] or 'icpc',           
                    'mode': 'free',
                    'allowed_languages': allowed_languages
                },
                'start_time': start_time,
                'participants': parts,
                'is_dirty': True,
                'first_solves': res['results']['first_solves'],
                'cached_state': None
            }
        return restored
    
    def add_scheduled_olympiad(self, olympiad_id, name, start_time, config, task_ids):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO scheduled_olympiads (olympiad_id, name, start_time, config_json, task_ids_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(olympiad_id) DO UPDATE SET
                    name=excluded.name, start_time=excluded.start_time, 
                    config_json=excluded.config_json, task_ids_json=excluded.task_ids_json
                """, (olympiad_id, name, start_time, json.dumps(config), json.dumps(task_ids)))
                conn.commit()

    def get_all_scheduled_olympiads(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM scheduled_olympiads")
            return c.fetchall()
    
    def update_scheduled_time(self, olympiad_id, new_time):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("UPDATE scheduled_olympiads SET start_time = ? WHERE olympiad_id = ?", (new_time, olympiad_id))
                conn.commit()

    def remove_scheduled_olympiad(self, olympiad_id):
        with self.write_lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM scheduled_olympiads WHERE olympiad_id = ?", (olympiad_id,))
                conn.commit()
    
    def update_submission_immediate(self, olympiad_id, participant_uuid, nickname, task_id, code):
        with self.write_lock:
            try:
                with self._get_conn() as conn:
                    c = conn.cursor()
                    c.execute("SELECT task_submissions FROM olympiad_submissions WHERE olympiad_id = ? AND participant_uuid = ?", 
                              (olympiad_id, participant_uuid))
                    row = c.fetchone()
                    
                    submissions = json.loads(row['task_submissions']) if row and row['task_submissions'] else {}
                    submissions[str(task_id)] = code
                    submissions_json = json.dumps(submissions)

                    c.execute("""
                        INSERT INTO olympiad_submissions (olympiad_id, participant_uuid, nickname, task_submissions)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(olympiad_id, participant_uuid) DO UPDATE SET
                        task_submissions=excluded.task_submissions,
                        nickname=excluded.nickname
                    """, (olympiad_id, participant_uuid, nickname, submissions_json))
                    conn.commit()
                    return True
            except Exception as e:
                print(f"CRITICAL DB ERROR: {e}")
                return False
    # [FIX] Добавляем поиск UUID по никнейму для восстановления сессии
    def get_participant_uuid_by_nickname(self, olympiad_id, nickname):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT participant_uuid FROM olympiad_results WHERE olympiad_id = ? AND nickname = ?", (olympiad_id, nickname))
            row = c.fetchone()
            return row['participant_uuid'] if row else None

# Скрипт запуска (Mono C# версия)
def _run_batch(code, test_data_list, language, judge_script_filename, docker_image, checker_code=None):
    judge_script = load_judge_script(judge_script_filename)
    if not judge_script: return None, "System Error: Judge script not found"

    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp()
        code_filename = "Program.cs" if language == "C#" else ("source.cpp" if language == "C++" else "script.py")
        
        with open(os.path.join(tmp_dir, code_filename), "w", encoding="utf-8") as f: f.write(code)
        with open(os.path.join(tmp_dir, "judge.py"), "w", encoding="utf-8") as f: f.write(judge_script)
        with open(os.path.join(tmp_dir, "tests.json"), "w", encoding="utf-8") as f: json.dump(test_data_list, f)
        if checker_code:
            with open(os.path.join(tmp_dir, "checker.py"), "w", encoding="utf-8") as f: f.write(checker_code)
            
        abs_path = os.path.abspath(tmp_dir)
        docker_volume_arg = ["-v", f"{_get_docker_path(abs_path)}:/home/appuser/run:ro"]
        total_time_limit = sum(float(t.get('limit', 1.0)) for t in test_data_list)
        
        container_command = ["python3", "/home/appuser/run/judge.py"]
        command = DOCKER_COMMON_ARGS + docker_volume_arg + [docker_image] + container_command

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=total_time_limit + 15.0)
        output = result.stdout.decode('utf-8', errors='replace')
        err = result.stderr.decode('utf-8', errors='replace')

        if err and "System Error" in err: return None, f"Docker/Judge Error: {err}"

        try:
            return json.loads(output), None
        except:
            return None, f"System Error (JSON): {output} | Err: {err}"

    except subprocess.TimeoutExpired: return None, "Time Limit Exceeded (Overall)"
    except Exception as e: return None, f"Execution error: {str(e)}"
    finally:
        if tmp_dir and os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)

def run_python(code, test_data_list, checker_code=None):
    return _run_batch(code, test_data_list, "Python", "py_runner.py", DOCKER_IMAGE_PYTHON, checker_code)
def run_cpp(code, test_data_list, checker_code=None):
    return _run_batch(code, test_data_list, "C++", "cpp_runner.py", DOCKER_IMAGE_CPP, checker_code)
def run_csharp(code, test_data_list, checker_code=None):
    return _run_batch(code, test_data_list, "C#", "cs_runner.py", DOCKER_IMAGE_CSHARP, checker_code)