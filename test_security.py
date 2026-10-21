
from security import hash_password, verify_password


# Исходный пароль для проверки.
password = "TestPassword123!"

# Получаем хеш пароля.
hashed_password = hash_password(password)

# Проверяем правильный и неправильный пароли.
assert verify_password(password, hashed_password) is True
assert verify_password("WrongPassword123!", hashed_password) is False

# Убедимся, что исходный пароль не совпадает с хешем.
assert password != hashed_password

print("Все проверки безопасности паролей пройдены!")
print(f"Исходный пароль: {password}")
print(f"Полученный хеш: {hashed_password}")
