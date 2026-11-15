"""Shared OLED UI state for BabyBox (/tmp/babybox-oled.json).

phase:
  setup — boot / AP / waiting for home Wi-Fi  → Wi-Fi icon
  ready — home Wi-Fi connected                 → clock
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
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    tmp.replace(STATUS_FILE)


def load() -> dict[str, Any]:
    data = _read()
    phase = str(data.get("phase") or "setup").strip().lower()
    if phase not in {"setup", "ready"}:
        phase = "setup"
    return {
        "phase": phase,
        "lullaby": bool(data.get("lullaby")),
        "lamp_until": float(data.get("lamp_until") or 0),
        "updated_at": data.get("updated_at"),
    }


def set_phase(phase: str) -> dict[str, Any]:
    phase = "ready" if str(phase).strip().lower() == "ready" else "setup"
    data = _read()
    data["phase"] = phase
    _write(data)
    return load()


def set_lullaby(enabled: bool) -> dict[str, Any]:
    data = _read()
    data["lullaby"] = bool(enabled)
    if "phase" not in data:
        data["phase"] = "setup"
    _write(data)
    return load()


def flash_lamp(seconds: float | None = None) -> dict[str, Any]:
    data = _read()
    data["lamp_until"] = time.time() + float(LAMP_SEC if seconds is None else seconds)
    if "phase" not in data:
        data["phase"] = "setup"
    _write(data)
    return load()
