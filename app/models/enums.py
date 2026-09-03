import enum

# User roles are no longer a fixed enum - see app/models/rbac.py (Role,
# Permission) and app/services/permissions.py for the RBAC model that
# replaced it.


class UploadType(str, enum.Enum):
    BRANCH_MANAGER = "BRANCH_MANAGER"
    BUSINESS_MANAGER = "BUSINESS_MANAGER"


class UploadStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class MatchStatus(str, enum.Enum):
    MATCHED = "MATCHED"
    MATCHED_WITH_WARNING = "MATCHED_WITH_WARNING"
    UNMATCHED_IN_BUSINESS_FILE = "UNMATCHED_IN_BUSINESS_FILE"
    UNMATCHED_IN_BRANCH_FILE = "UNMATCHED_IN_BRANCH_FILE"
    DUPLICATE = "DUPLICATE"


class LoanType(str, enum.Enum):
    NL = "NL"  # New Loan
    RF = "RF"  # Top-up


class CommissionBase(str, enum.Enum):
    GROSS = "GROSS"
    NET = "NET"


class PayeeType(str, enum.Enum):
    DSA = "DSA"
    DTL = "DTL"


class RunType(str, enum.Enum):
    BRANCH = "BRANCH"
    ORG_WIDE = "ORG_WIDE"


class RunStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    LOCKED = "LOCKED"
    PAID = "PAID"
