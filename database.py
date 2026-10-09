from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base


DATABASE_URL = "postgresql+psycopg2://nutrition:nutrition_pass@localhost:5432/nutrition"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(engine)