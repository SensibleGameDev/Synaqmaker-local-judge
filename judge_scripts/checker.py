# Это заглушка, чтобы IDE не ругалась на import checker
# В реальной работе этот файл будет заменен кодом чекера из базы данных.

def check(test_input, user_output, expected_output):
    """
    Функция чекера должна возвращать True, если решение верное, 
    и False, если нет.
    """
    return user_output.strip() == expected_output.strip()