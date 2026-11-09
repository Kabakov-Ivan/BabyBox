"""Saved photos / clips under /home/admin/Save_BabyBox/camera."""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SAVE_DIR = Path(os.environ.get("BABYBOX_SAVE_DIR", "/home/admin/Save_BabyBox/camera"))
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mjpeg", ".mjpg"}


class MediaStore:
    def __init__(self, root: Path = SAVE_DIR) -> None:
        self.root = root
        self._lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def stamp_name(self, kind: str, ext: str) -> str:
        now = datetime.now(timezone.utc).astimezone()
        if not ext.startswith("."):
            ext = f".{ext}"
        return f"babybox-{kind}-{now.strftime('%Y%m%d-%H%M%S')}{ext.lower()}"

    def prepare_path(self, kind: str, ext: str) -> Path:
        self.ensure()
        return self.root / self.stamp_name(kind, ext)

    def resolve(self, name: str) -> Optional[Path]:
        if not name or not SAFE_NAME.match(name):
            return None
        path = (self.root / name).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return None
        return path

    def save_bytes(self, data: bytes, kind: str, ext: str) -> dict:
        path = self.prepare_path(kind, ext)
        with self._lock:
            path.write_bytes(data)
        return self.meta_for(path)

    def save_upload(self, data: bytes, filename: str, kind: str = "clip") -> dict:
        suffix = Path(filename or "").suffix.lower() or ".webm"
        if suffix not in IMAGE_EXT | VIDEO_EXT:
            suffix = ".webm" if kind == "clip" else ".jpg"
        return self.save_bytes(data, kind, suffix)

    def list_items(self) -> list[dict]:
        self.ensure()
        items = []
        for path in self.root.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in IMAGE_EXT | VIDEO_EXT:
                continue
            items.append(self.meta_for(path))
        items.sort(key=lambda item: item["mtime"], reverse=True)
        return items

    def delete(self, name: str) -> bool:
        path = self.resolve(name)
        if path is None or not path.is_file():
            return False
        with self._lock:
            path.unlink(missing_ok=True)
        return True

    def meta_for(self, path: Path) -> dict:
        stat = path.stat()
        ext = path.suffix.lower()
        kind = "photo" if ext in IMAGE_EXT else "video"
        return {
            "name": path.name,
            "kind": kind,
            "url": f"/api/media/file/{path.name}",
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }


media_store = MediaStore()
