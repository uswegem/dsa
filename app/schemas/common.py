from pydantic import BaseModel


class BranchOut(BaseModel):
    id: int
    name: str
    code: str | None

    model_config = {"from_attributes": True}


class BranchCreate(BaseModel):
    name: str
    code: str | None = None


class DtlOut(BaseModel):
    id: int
    dtl_code: str
    dtl_name: str
    dtl_account_no: str | None
    branch_id: int | None

    model_config = {"from_attributes": True}


class DtlCreate(BaseModel):
    dtl_code: str
    dtl_name: str
    dtl_account_no: str | None = None
    branch_id: int | None = None


class DtlUpdate(BaseModel):
    dtl_name: str | None = None
    dtl_account_no: str | None = None
    branch_id: int | None = None


class DsaOut(BaseModel):
    id: int
    dsa_code: str
    dsa_name: str
    dsa_account_no: str | None
    branch_id: int | None
    current_dtl_id: int | None = None
    current_dtl_code: str | None = None
    current_dtl_name: str | None = None

    model_config = {"from_attributes": True}


class DsaCreate(BaseModel):
    dsa_code: str
    dsa_name: str
    dsa_account_no: str | None = None
    branch_id: int | None = None
    dtl_id: int | None = None  # optional initial DTL assignment, effective today


class DsaUpdate(BaseModel):
    dsa_name: str | None = None
    dsa_account_no: str | None = None
    branch_id: int | None = None
    dtl_id: int | None = None  # if provided (and different from current), reassigned effective today via dsa_dtl_assignments


class PermissionOut(BaseModel):
    id: int
    key: str
    description: str | None

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_system_role: bool
    permission_count: int
    permissions: list[str] = []

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_keys: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_keys: list[str] | None = None  # None = leave permissions unchanged
