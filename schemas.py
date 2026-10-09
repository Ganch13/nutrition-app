from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(gt=0, le=120)
    height_cm: int = Field(gt=0, le=300)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int
    height_cm: int