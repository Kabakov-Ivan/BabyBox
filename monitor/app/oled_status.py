"""OLED status file: /tmp/babybox-oled.json

Only stores panel events (lullaby / lamp flash).
Wi-Fi vs time is a simple ready-flag file (see READY_FLAG).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

STATUS_FILE = Path(os.environ.get("OLED_STATUS_FILE", "/tmp/babybox-oled.json"))
# Exists → show clock. Missing → show Wi-Fi icon.
READY_FLAG = Path(os.environ.get("OLED_READY_FLAG", "/tmp/babybox-oled-ready"))
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
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    tmp.replace(STATUS_FILE)


def load() -> dict[str, Any]:
    data = _read()
    return {
        "ready": READY_FLAG.exists(),
        "lullaby": bool(data.get("lullaby")),
        "lamp_until": float(data.get("lamp_until") or 0),
        "updated_at": data.get("updated_at"),
    }


def mark_setup() -> None:
    """Boot / AP mode → Wi-Fi icon."""
    try:
        READY_FLAG.unlink(missing_ok=True)
    except TypeError:
        # Python <3.8 style (shouldn't happen on Pi 3.13)
        if READY_FLAG.exists():
            READY_FLAG.unlink()
    except FileNotFoundError:
        pass


def mark_ready() -> None:
    """Home Wi-Fi connected → clock."""
    READY_FLAG.write_text("1\n", encoding="utf-8")


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
