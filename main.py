from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import SessionLocal
from models import User

app = FastAPI()


class UserCreate(BaseModel):
    name: str
    age: int
    height_cm: int


@app.get("/hello")
def hello():
    print("Hello World")
    return {"message": "Hello Daniil"}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    db = SessionLocal()

    try:
        db_user = db.get(User, user_id)

        if db_user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        return {
            "id": db_user.id,
            "name": db_user.name,
            "age": db_user.age,
            "height_cm": db_user.height_cm
        }

    finally:
        db.close()

@app.post("/users")
def create_user(user: UserCreate):
    db = SessionLocal()

    try:
        db_user = User(
            name=user.name,
            age=user.age,
            height_cm=user.height_cm
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return {
            "id": db_user.id,
            "name": db_user.name,
            "age": db_user.age,
            "height_cm": db_user.height_cm
        }

    finally:
        db.close()




