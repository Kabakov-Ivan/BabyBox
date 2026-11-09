"""Daily sensor history for the Reports tab.

Stores throttled samples under /home/admin/Save_BabyBox/sensors/YYYY-MM-DD.jsonl
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(
    os.environ.get("BABYBOX_SENSOR_DIR", "/home/admin/Save_BabyBox/sensors")
)
SAMPLE_EVERY_SEC = float(os.environ.get("BABYBOX_SENSOR_SAMPLE_SEC", "60"))
KEEP_DAYS = int(os.environ.get("BABYBOX_SENSOR_KEEP_DAYS", "14"))

_lock = threading.Lock()
_last_sample_at = 0.0
_last_cleanup_at = 0.0


def _day_path(day: date) -> Path:
    return DATA_DIR / f"{day.isoformat()}.jsonl"


def _local_today() -> date:
    return datetime.now().astimezone().date()


def append_sample(temp_c: float, humidity_pct: float, *, force: bool = False) -> bool:
    """Append one sample for today. Throttled to SAMPLE_EVERY_SEC unless force."""
    global _last_sample_at
    now = time.time()
    with _lock:
        if not force and (now - _last_sample_at) < SAMPLE_EVERY_SEC:
            return False
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = _day_path(_local_today())
        row = {
            "ts": now,
            "temp_c": round(float(temp_c), 1),
            "humidity_pct": round(float(humidity_pct), 1),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
        _last_sample_at = now
        # Cleanup at most once per hour — not on every sample.
        global _last_cleanup_at
        if now - _last_cleanup_at > 3600:
            _last_cleanup_at = now
            _cleanup_old_files()
        return True


def _cleanup_old_files() -> None:
    if KEEP_DAYS <= 0 or not DATA_DIR.exists():
        return
    cutoff = _local_today() - timedelta(days=KEEP_DAYS)
    for path in DATA_DIR.glob("*.jsonl"):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < cutoff:
            try:
                path.unlink()
            except OSError:
                pass


def _load_day(day: date) -> list[dict[str, Any]]:
    path = _day_path(day)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and "ts" in item:
            rows.append(item)
    rows.sort(key=lambda r: r.get("ts", 0))
    return rows


def _metric_block(rows: list[dict], key: str) -> dict[str, Any]:
    values = []
    series = []
    for row in rows:
        raw = row.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        values.append(value)
        series.append({"t": row.get("ts"), "v": round(value, 1)})

    if not values:
        return {
            "current": None,
            "min": None,
            "max": None,
            "avg": None,
            "count": 0,
            "series": [],
        }

    # Downsample series for the chart if huge (keep ~288 ≈ 5 мин за сутки)
    max_points = 288
    if len(series) > max_points:
        step = len(series) / max_points
        series = [series[int(i * step)] for i in range(max_points)]

    return {
        "current": round(values[-1], 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "avg": round(sum(values) / len(values), 1),
        "count": len(values),
        "series": series,
    }


def day_report(day: Optional[date] = None) -> dict[str, Any]:
    day = day or _local_today()
    rows = _load_day(day)
    return {
        "date": day.isoformat(),
        "timezone": datetime.now().astimezone().tzname(),
        "sample_every_sec": SAMPLE_EVERY_SEC,
        "points": len(rows),
        "temp_c": _metric_block(rows, "temp_c"),
        "humidity_pct": _metric_block(rows, "humidity_pct"),
        "co2_ppm": _metric_block(rows, "co2_ppm"),
    }
