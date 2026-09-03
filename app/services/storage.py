import datetime as dt
import os
import uuid

from app.core.config import get_settings

settings = get_settings()


def save_upload_file(contents: bytes, original_filename: str, subdir: str) -> str:
    """Saves raw bytes to UPLOAD_DIR/subdir/<timestamp>_<uuid>_<original>, returns the storage path."""
    ext = os.path.splitext(original_filename)[1] or ".xlsx"
    safe_name = f"{dt.datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    target_dir = os.path.join(settings.upload_dir, subdir)
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, safe_name)
    with open(path, "wb") as f:
        f.write(contents)
    return path
