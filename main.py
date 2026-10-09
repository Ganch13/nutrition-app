from fastapi import FastAPI, HTTPException, Depends
from schemas import UserCreate, UserResponse
from database import get_db
from models import User
from sqlalchemy.orm import Session



app = FastAPI()




@app.get("/hello")
def hello():
    print("Hello World")
    return {"message": "Hello Daniil"}

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    db_user = db.get(User, user_id)

    if db_user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return db_user


@app.post("/users", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    db_user = User(
        name=user.name,
        age=user.age,
        height_cm=user.height_cm
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user




