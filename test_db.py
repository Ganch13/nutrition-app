from database import engine

with engine.connect() as connection:
    print("Подключение к PostgreSQL успешно!")