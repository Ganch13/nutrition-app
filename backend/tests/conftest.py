import os

# Задаём тестовый секрет ДО импорта приложения: security.py читает
# JWT_SECRET_KEY при импорте. setdefault не затирает уже заданное значение,
# а load_dotenv() в security.py по умолчанию не перезаписывает переменные окружения.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-not-for-production")
# Для тестов задаём разрешённый адрес frontend жёстко, а не из .env:
# тесты CORS проверяют точные значения, и результат не должен зависеть
# от настроек на вашем компьютере.
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import get_db
from main import app
from models import Base

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://nutrition:nutrition_pass@localhost:5432/nutrition_test",
)


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(TEST_DATABASE_URL)

    # Защита: тесты стирают данные, поэтому работают только с базой на _test
    assert test_engine.url.database.endswith("_test"), (
        "Тесты должны работать только с тестовой базой (имя оканчивается на _test)"
    )

    # Схему создаём из моделей. Миграции Alembic здесь не проверяются.
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)

    yield test_engine

    test_engine.dispose()


@pytest.fixture()
def client(engine):
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    # Подменяем зависимость: приложение будет работать с тестовой базой.
    # Подмена действует и на get_current_user, который тоже использует get_db.
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()

    # После каждого теста очищаем все таблицы и сбрасываем счётчики id
    table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


