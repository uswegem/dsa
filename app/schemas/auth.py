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
    # Optional at the schema level - whether it's actually required (and
    # what value wins) depends on the role: BRANCH_MANAGER requires exactly
    # one branch, BUSINESS_MANAGER is always forced to Head Office
    # regardless of what's sent. See app/api/admin/users.py::_resolve_branch_for_role.
    branch_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role_id: int | None = None
    branch_id: int | None = None  # None = leave unchanged; role-dependent enforcement, see _resolve_branch_for_role
    is_active: bool | None = None
    password: str | None = None  # provide to reset the password; omitted/blank leaves it unchanged
