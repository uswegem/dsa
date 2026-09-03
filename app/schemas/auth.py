from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    branch_id: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole
    branch_id: int | None = None
