from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_business_manager, User
from app.services.audit import log_action
from app.services.matching import run_matching

router = APIRouter(prefix="/api/matching", tags=["matching"])


@router.post("/run")
def trigger_matching(db: Session = Depends(get_db), current_user: User = Depends(require_business_manager)):
    """Manually re-run reconciliation across all unresolved rows. Uploads
    already trigger this automatically, but it's exposed directly too since
    the two files can land far apart and an operator may want to force a
    re-check without uploading anything new."""
    result = run_matching(db, branch_upload_id=None, business_upload_id=None)
    log_action(
        db, current_user.id, "MATCHING_RUN", None, None,
        matched=result.matched, matched_with_warning=result.matched_with_warning,
        unmatched_in_business_file=result.unmatched_in_business_file,
        unmatched_in_branch_file=result.unmatched_in_branch_file, duplicates=result.duplicates,
    )
    db.commit()
    return result.__dict__
