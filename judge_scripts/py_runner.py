import sys
import os
import json
import subprocess
import time
import traceback
import io
from contextlib import redirect_stdout

# Import shared utilities
try:
    from judge_utils import get_tokens, compare_outputs, check_verdict_with_checker
    HAS_JUDGE_UTILS = True
except ImportError:
    HAS_JUDGE_UTILS = False
    # Fallback implementation if judge_utils is not available
    def get_tokens(text):
        if not text:
            return []
        return text.strip().split()
    
    def compare_outputs(user_output, expected_output):
        return get_tokens(user_output) == get_tokens(expected_output)

# Пытаемся импортировать чекер, если он есть
try:
    import checker
    HAS_CHECKER = True
except ImportError:
    HAS_CHECKER = False

def run_judge():
    results = []
    
    # Читаем тесты
    try:
        with open('tests.json', 'r') as f:
            tests = json.load(f)
    except Exception as e:
        print(json.dumps([{"verdict": "Internal Error", "error": f"Failed to read tests.json: {e}"}]))
        return

    for i, test in enumerate(tests):
        test_input = test.get('input', '')
        expected_output = test.get('output', '')
        # Используем жесткий лимит
        time_limit = float(test.get('limit', 1.0))
        cmd_timeout = time_limit 
        
        try:
            start_time = time.monotonic()
            
            # Запуск решения студента
            # Используем системный timeout для надежности процесса
            process = subprocess.run(
                ['timeout', str(cmd_timeout), 'python3', '-u', 'script.py'],
                input=test_input.encode('utf-8'),
                capture_output=True,
                # Даем Python чуть больше времени, чтобы он успел поймать код возврата timeout (124)
                timeout=cmd_timeout + 0.5 
            )
            
            output = process.stdout.decode('utf-8', errors='replace')
            error = process.stderr.decode('utf-8', errors='replace')
            return_code = process.returncode
            
            verdict = ""
            
            if return_code == 124: # Код возврата timeout в Linux
                verdict = "Time Limit Exceeded"
            elif return_code != 0:
                verdict = "Runtime Error"
            else:
                # Проверка ответа
                if HAS_CHECKER:
                    if HAS_JUDGE_UTILS:
                        verdict, checker_error = check_verdict_with_checker(
                            checker, test_input, output, expected_output
                        )
                        if checker_error:
                            error += checker_error
                    else:
                        # Fallback to original implementation
                        try:
                            f_dummy = io.StringIO()
                            with redirect_stdout(f_dummy):
                                is_ok = checker.check(test_input, output, expected_output)
                            verdict = "Accepted" if is_ok else "Wrong Answer"
                        except Exception as check_err:
                            verdict = "Judge Error"
                            error += f"\nChecker failed: {check_err}"
                else:
                    if compare_outputs(output, expected_output):
                        verdict = "Accepted"
                    else:
                        verdict = "Wrong Answer"
            
            results.append({
                "test_num": i + 1,
                "verdict": verdict,
                "output": output,
                "error": error
            })

        except subprocess.TimeoutExpired:
            results.append({
                "test_num": i + 1,
                "verdict": "Time Limit Exceeded",
                "output": "",
                "error": "Judge subprocess timeout"
            })
        except Exception as e:
            results.append({
                "test_num": i + 1,
                "verdict": "Internal Error",
                "output": "",
                "error": str(e)
            })

    # Выводим JSON с результатами в stdout (его читает Synaqmaker)
    print(json.dumps(results))

if __name__ == "__main__":
    run_judge()