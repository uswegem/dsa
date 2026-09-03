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

    model_config = {"from_attributes": True}


class DtlCreate(BaseModel):
    dtl_code: str
    dtl_name: str


class DsaOut(BaseModel):
    id: int
    dsa_code: str
    dsa_name: str
    dsa_account_no: str | None
    branch_id: int | None

    model_config = {"from_attributes": True}
