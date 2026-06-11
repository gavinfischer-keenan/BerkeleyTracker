"""Photo management — attach images to aircraft/vessels."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from tracker.registry.db import TrackerDB

log = structlog.get_logger(__name__)


class PhotoManager:
    def __init__(self, db: TrackerDB, photo_dir: str = "/data/photos") -> None:
        self.db = db
        self.photo_dir = Path(photo_dir)

    def save_uploaded(self, craft_type: str, craft_id: str,
                      file_bytes: bytes, filename: str, caption: str = "") -> str:
        """Save uploaded photo and link to craft. Returns photo_id."""
        craft_dir = self.photo_dir / craft_type / craft_id
        craft_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(filename).suffix or ".jpg"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        safe_name = f"{date_str}_{uuid.uuid4().hex[:6]}{ext}"
        file_path = craft_dir / safe_name

        file_path.write_bytes(file_bytes)
        log.info("photo.saved", path=str(file_path), size=len(file_bytes))

        return self.add_photo(craft_type, craft_id, str(file_path), caption)

    def add_photo(self, craft_type: str, craft_id: str,
                  file_path: str, caption: str = "") -> str:
        photo_id = f"photo-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        self.db.execute(
            "INSERT INTO photos (photo_id, craft_type, craft_id, file_path, "
            "caption, taken_at, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (photo_id, craft_type, craft_id, file_path, caption, now, now))

        log.info("photo.added", photo_id=photo_id, craft_type=craft_type, craft_id=craft_id)
        return photo_id

    def get_photos(self, craft_type: str, craft_id: str) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM photos WHERE craft_type = ? AND craft_id = ? ORDER BY taken_at DESC",
            (craft_type, craft_id))
        return [dict(r) for r in rows]

    def delete_photo(self, photo_id: str) -> bool:
        row = self.db.query_one("SELECT file_path FROM photos WHERE photo_id = ?", (photo_id,))
        if not row:
            return False

        try:
            os.remove(row["file_path"])
        except FileNotFoundError:
            pass

        self.db.execute("DELETE FROM photos WHERE photo_id = ?", (photo_id,))
        log.info("photo.deleted", photo_id=photo_id)
        return True
