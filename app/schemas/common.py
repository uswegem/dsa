from pydantic import BaseModel

from app.services.bulk_details import BulkUpdateSummary


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
    branch_id: int  # required - branch is mandatory when onboarding a DTL


class DtlUpdate(BaseModel):
    dtl_name: str | None = None
    dtl_account_no: str | None = None
    branch_id: int | None = None  # None = leave unchanged; if provided, must reference a real branch (see get_required_branch)


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
    branch_id: int  # required - branch is mandatory when onboarding a DSA
    dtl_id: int | None = None  # optional initial DTL assignment, effective today


class DsaUpdate(BaseModel):
    dsa_name: str | None = None
    dsa_account_no: str | None = None
    branch_id: int | None = None  # None = leave unchanged; if provided, must reference a real branch (see get_required_branch)
    dtl_id: int | None = None  # if provided (and different from current), reassigned effective today via dsa_dtl_assignments


class BulkUpdateRowOut(BaseModel):
    row_number: int
    name: str
    branch: str
    status: str  # "UPDATED" | "UNMATCHED" | "ERROR"
    message: str | None = None


class BulkUpdateResultOut(BaseModel):
    total_rows: int
    parse_issues: list[str]  # rows skipped before matching (blank name/branch)
    updated_count: int
    unchanged_count: int
    updated: list[BulkUpdateRowOut]
    unmatched: list[BulkUpdateRowOut]
    errors: list[BulkUpdateRowOut]

    @classmethod
    def from_summary(cls, summary: BulkUpdateSummary) -> "BulkUpdateResultOut":
        def _out(o):
            return BulkUpdateRowOut(row_number=o.row_number, name=o.name, branch=o.branch, status=o.status, message=o.message)

        return cls(
            total_rows=summary.total_rows,
            parse_issues=summary.parse_issues,
            updated_count=len(summary.updated),
            unchanged_count=len(summary.unchanged),
            updated=[_out(o) for o in summary.updated],
            unmatched=[_out(o) for o in summary.unmatched],
            errors=[_out(o) for o in summary.errors],
        )


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
