from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from collections.abc import Generator
from sqlalchemy.orm import Session





DATABASE_URL = "postgresql+psycopg2://nutrition:nutrition_pass@localhost:5432/nutrition"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()