from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role_id: int
    role_name: str
    branch_id: int | None
    is_active: bool
    permissions: list[str] = []  # this user's current effective permission keys, for frontend UI gating

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user) -> "UserOut":
        from app.services.permissions import user_permission_keys

        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role_id=user.role_id,
            role_name=user.role.name,
            branch_id=user.branch_id,
            is_active=user.is_active,
            permissions=user_permission_keys(user),
        )


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role_id: int
    branch_id: int | None = None
