from werkzeug.security import generate_password_hash

s = input("Введите пароль: ")
print("Хеш пароля:")
print(generate_password_hash(s))