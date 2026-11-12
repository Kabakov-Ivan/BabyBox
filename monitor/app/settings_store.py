"""Small JSONL stores for the optional account, sound and panel PIN settings."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any

SAVE_ROOT = Path(os.environ.get("BABYBOX_SAVE_ROOT", "/home/admin/Save_BabyBox"))
PROFILE_DIR = SAVE_ROOT / "profile"
SOUND_SAVE_DIR = SAVE_ROOT / "sounds"
MONITOR_ROOT = Path(__file__).resolve().parent.parent
SECURITY_DIR = Path(os.environ.get("BABYBOX_PIN_DIR", str(MONITOR_ROOT / "security")))
PIN_ITERATIONS = 180_000
PIN_PATTERN = re.compile(r"^\d{4,8}$")
_pin_guard = threading.Lock()
_pin_failures = 0
_pin_blocked_until = 0.0


def _latest(path: Path) -> dict[str, Any] | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            return row
    return None


def _append(directory: Path, filename: str, row: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / filename).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _replace_latest(directory: Path, filename: str, row: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    temporary = directory / f".{filename}.tmp"
    temporary.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass


def load_profile() -> dict[str, Any] | None:
    return _latest(PROFILE_DIR / "profile.jsonl")


def save_profile(row: dict[str, Any]) -> None:
    _append(PROFILE_DIR, "profile.jsonl", row)


def save_sound_default(filename: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+\.wav", filename):
        raise ValueError("Неизвестный аудиофайл")
    _append(SOUND_SAVE_DIR, "default.jsonl", {
        "ts": int(time.time()),
        "file": filename,
        "path": f"~/BabyBox/monitor/sounds/{filename}",
    })


def load_sound_default() -> dict[str, Any] | None:
    return _latest(SOUND_SAVE_DIR / "default.jsonl")


def _pin_record() -> dict[str, Any] | None:
    return _latest(SECURITY_DIR / "pin.jsonl")


def pin_is_set() -> bool:
    return bool(_pin_record())


def _pin_matches(pin: str, record: dict[str, Any]) -> bool:
    try:
        salt = bytes.fromhex(record["salt"])
        expected = bytes.fromhex(record["hash"])
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PIN_ITERATIONS)
        return hmac.compare_digest(actual, expected)
    except (KeyError, TypeError, ValueError):
        return False


def verify_pin(pin: str) -> bool:
    global _pin_failures, _pin_blocked_until
    now = time.monotonic()
    with _pin_guard:
        if now < _pin_blocked_until:
            return False
        record = _pin_record()
        matched = bool(record and _pin_matches(pin, record))
        if matched:
            _pin_failures = 0
            _pin_blocked_until = 0.0
        else:
            _pin_failures += 1
            if _pin_failures >= 5:
                _pin_failures = 0
                _pin_blocked_until = now + 30
        return matched


def save_pin(pin: str) -> None:
    if not PIN_PATTERN.fullmatch(pin):
        raise ValueError("PIN-код должен состоять из 4–8 цифр")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PIN_ITERATIONS)
    _replace_latest(SECURITY_DIR, "pin.jsonl", {
        "ts": int(time.time()),
        "algorithm": f"pbkdf2-sha256-{PIN_ITERATIONS}",
        "salt": salt.hex(),
        "hash": digest.hex(),
    })
