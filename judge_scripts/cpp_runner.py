import sys
import os
import json
import subprocess
import time
import io
from contextlib import redirect_stdout

try:
    import checker
    HAS_CHECKER = True
except ImportError:
    HAS_CHECKER = False

def get_tokens(text):
    if not text:
        return []
    return text.strip().split()

def run_judge():
    results = []
    
    # 1. Компиляция
    # Важно: пишем output в /tmp/a.out, т.к. текущая директория Read-Only
    try:
        compile_proc = subprocess.run(
            ['g++', 'source.cpp', '-o', '/tmp/a.out', '-O3', '-march=native', '-std=c++17'],
            capture_output=True, text=True, timeout=15
        )
    except subprocess.TimeoutExpired:
        print(json.dumps([{"verdict": "Compilation Error", "error": "Compilation timed out (> 15s)"}]))
        return

    if compile_proc.returncode != 0:
        error_msg = compile_proc.stderr.replace("source.cpp:", "line ")
        print(json.dumps([{"verdict": "Compilation Error", "error": error_msg}]))
        return

    # 2. Чтение тестов
    try:
        with open('tests.json', 'r') as f:
            tests = json.load(f)
    except Exception as e:
        print(json.dumps([{"verdict": "Internal Error", "error": f"Failed to read tests.json: {e}"}]))
        return

    # 3. Прогоняем тесты
    for i, test in enumerate(tests):
        test_input = test.get('input', '')
        expected_output = test.get('output', '')
        time_limit = float(test.get('limit', 1.0))
        cmd_timeout = time_limit
        
        try:
            start_time = time.monotonic()
            
            # Запуск скомпилированного бинарника из /tmp
            process = subprocess.run(
                ['timeout', str(cmd_timeout), '/tmp/a.out'],
                input=test_input.encode('utf-8'),
                capture_output=True,
                timeout=cmd_timeout + 0.5
            )
            
            output = process.stdout.decode('utf-8', errors='replace')
            error = process.stderr.decode('utf-8', errors='replace')
            return_code = process.returncode
            
            verdict = ""
            
            if return_code == 124:
                verdict = "Time Limit Exceeded"
            elif return_code != 0:
                verdict = "Runtime Error"
            else:
                if HAS_CHECKER:
                    try:
                        f_dummy = io.StringIO()
                        with redirect_stdout(f_dummy):
                            is_ok = checker.check(test_input, output, expected_output)
                        verdict = "Accepted" if is_ok else "Wrong Answer"
                    except Exception as check_err:
                        verdict = "Judge Error"
                        error += f"\nChecker failed: {check_err}"
                else:
                    user_tokens = get_tokens(output)
                    expected_tokens = get_tokens(expected_output)
                    if user_tokens == expected_tokens:
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

    print(json.dumps(results))

if __name__ == "__main__":
    run_judge()