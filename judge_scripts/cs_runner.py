import sys
import os
import json
import subprocess

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

# [FIX] Добавляем поддержку кастомного чекера
try:
    import checker
    HAS_CHECKER = True
except ImportError:
    HAS_CHECKER = False

def run_judge():
    results = []
    
    # 1. Настройка путей
    # Исходный код читаем из текущей папки (она Read-Only)
    source_file = "Program.cs"
    # Результат (exe) пишем во временную папку /tmp, где есть права на запись
    exe_file = "/tmp/Program.exe"
    
    # === 2. КОМПИЛЯЦИЯ (Mono C# Compiler) ===
    # -out:... указывает компилятору, куда сохранить файл
    compile_cmd = ["mcs", "-out:" + exe_file, source_file]
    
    try:
        compile_proc = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if compile_proc.returncode != 0:
            # Ошибка компиляции
            err_msg = compile_proc.stderr + "\n" + compile_proc.stdout
            print(json.dumps([{"verdict": "Compilation Error", "error": err_msg.strip()}]))
            return

    except subprocess.TimeoutExpired:
        print(json.dumps([{"verdict": "Compilation Error", "error": "Compilation timed out"}]))
        return
    except Exception as e:
        print(json.dumps([{"verdict": "System Error", "error": f"Compiler launch failed: {e}"}]))
        return

    # === 3. ЗАПУСК ТЕСТОВ ===
    try:
        with open('tests.json', 'r') as f:
            tests = json.load(f)
    except Exception as e:
        print(json.dumps([{"verdict": "Internal Error", "error": f"Tests read error: {e}"}]))
        return

    for i, test in enumerate(tests):
        test_input = test.get('input', '')
        expected_output = test.get('output', '')
        
        try:
            time_limit = float(test.get('limit', 1.0))
        except (ValueError, TypeError):
            # Fallback to default if invalid time limit
            time_limit = 1.0
        
        cmd_timeout = time_limit
        
        try:
            # Запускаем скомпилированный файл из /tmp
            run_cmd = ['timeout', str(cmd_timeout), 'mono', exe_file]
            
            process = subprocess.run(
                run_cmd,
                input=test_input.encode('utf-8'),
                capture_output=True,
                # [BEST PRACTICE] timeout чуть больше, чтобы успеть поймать код 124
                timeout=cmd_timeout + 0.5 
            )
            
            output = process.stdout.decode('utf-8', errors='replace')
            error = process.stderr.decode('utf-8', errors='replace')
            
            verdict = ""
            if process.returncode == 124: # Linux timeout signal
                verdict = "Time Limit Exceeded"
            elif process.returncode != 0:
                verdict = "Runtime Error"
            else:
                # [FIX] Логика проверки ответа (Чекер или Стандарт)
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
                            import io
                            from contextlib import redirect_stdout
                            
                            f_dummy = io.StringIO()
                            with redirect_stdout(f_dummy):
                                is_ok = checker.check(test_input, output, expected_output)
                            verdict = "Accepted" if is_ok else "Wrong Answer"
                        except Exception as check_err:
                            verdict = "Judge Error"
                            error += f"\nChecker failed: {check_err}"
                else:
                    # Стандартное сравнение (игнорируя пробелы)
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
            results.append({"test_num": i+1, "verdict": "Time Limit Exceeded", "error": "Timeout"})
        except Exception as e:
            results.append({"test_num": i+1, "verdict": "Internal Error", "error": str(e)})

    # Уборка временного файла
    if os.path.exists(exe_file):
        try: os.remove(exe_file)
        except: pass

    # Вывод результатов для сервера
    print(json.dumps(results))

if __name__ == "__main__":
    run_judge()