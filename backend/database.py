import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from collections.abc import Generator
from sqlalchemy.orm import Session





# Адрес базы берём из переменной окружения DATABASE_URL (в Docker её задаёт compose).
# Если переменной нет, работает как раньше: база на этом же компьютере.
# Пример значения в Docker: postgresql+psycopg2://nutrition:ПАРОЛЬ@db:5432/nutrition
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://nutrition:nutrition_pass@localhost:5432/nutrition",
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()