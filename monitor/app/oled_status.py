"""OLED overlays for BabyBox (/tmp/babybox-oled.json).

Only lamp (3s) and lullaby. Default screen stays the clock.
Does not touch Wi-Fi / boot scripts.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

STATUS_FILE = Path(os.environ.get("OLED_STATUS_FILE", "/tmp/babybox-oled.json"))
LAMP_SEC = float(os.environ.get("OLED_LAMP_SEC", "3"))


def _read() -> dict[str, Any]:
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(payload: dict[str, Any]) -> None:
    data = dict(payload)
    data["updated_at"] = time.time()
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    tmp.replace(STATUS_FILE)
    try:
        os.chmod(STATUS_FILE, 0o666)
    except OSError:
        pass


def load() -> dict[str, Any]:
    data = _read()
    return {
        "lullaby": bool(data.get("lullaby")),
        "lamp_until": float(data.get("lamp_until") or 0),
        "updated_at": data.get("updated_at"),
    }


def set_lullaby(enabled: bool) -> dict[str, Any]:
    data = _read()
    data["lullaby"] = bool(enabled)
    _write(data)
    return load()


def flash_lamp(seconds: float | None = None) -> dict[str, Any]:
    data = _read()
    data["lamp_until"] = time.time() + float(LAMP_SEC if seconds is None else seconds)
    _write(data)
    return load()
