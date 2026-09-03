import json

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(db: Session, user_id: int | None, action: str, entity_type: str | None = None, entity_id: int | None = None, **details) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=json.dumps(details, default=str) if details else None,
        )
    )
    db.flush()
