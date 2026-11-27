"""Standalone MQ-135 digital (DOUT) reader for BabyBox.

Wiring (as connected):
  DOUT → physical pin 11 = BCM GPIO17
  VCC  → 5V (physical pin 2)
  GND  → physical pin 6

DOUT is a threshold comparator (not real ppm). We map:
  clean  → MQ135_CLEAN_PPM  (default 450)
  alarm  → MQ135_ALARM_PPM  (default 1500)
so the panel / reports can show Уровень CO₂ like temp/humidity.

Typical modules: DO goes LOW when air is above the pot threshold.
Override with MQ135_ALARM_IS_LOW=0 if inverted.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s MQ135 %(levelname)s: %(message)s",
)
log = logging.getLogger("mq135_worker")

BCM_PIN = int(os.environ.get("MQ135_BCM_PIN", "17"))
INTERVAL_SEC = float(os.environ.get("MQ135_INTERVAL_SEC", "2"))
OUT_PATH = Path(os.environ.get("MQ135_STATUS_FILE", "/tmp/babybox-mq135.json"))
ALARM_IS_LOW = os.environ.get("MQ135_ALARM_IS_LOW", "1") != "0"
CLEAN_PPM = int(os.environ.get("MQ135_CLEAN_PPM", "450"))
ALARM_PPM = int(os.environ.get("MQ135_ALARM_PPM", "1500"))

try:
    from sensor_history import append_co2_sample
except ImportError:
    def append_co2_sample(co2_ppm, *, force=False):  # type: ignore
        return False


def _pinctrl(*args: str) -> str:
    return subprocess.check_output(
        ["pinctrl", *args],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=0.8,
    )


def _parse_level(out: str) -> int | None:
    match = re.search(r"level=(\d)", out)
    if match:
        return int(match.group(1))
    if re.search(r"\|\s*hi\b", out, re.IGNORECASE):
        return 1
    if re.search(r"\|\s*lo\b", out, re.IGNORECASE):
        return 0
    return None


def ensure_input() -> None:
    # Digital input with pull-up (open-collector DO on many boards).
    _pinctrl("set", str(BCM_PIN), "ip", "pu")


def read_alarm() -> tuple[bool, int]:
    """Return (air_alarm, raw_level)."""
    out = _pinctrl("get", str(BCM_PIN))
    level = _parse_level(out)
    if level is None:
        raise RuntimeError(f"bad pinctrl output: {out.strip()!r}")
    alarm = (level == 0) if ALARM_IS_LOW else (level == 1)
    return alarm, level


def write_status(payload: dict, *, keep_last: bool = False) -> None:
    current: dict = {}
    if keep_last and OUT_PATH.exists():
        try:
            current = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            current = {}

    data = dict(current) if keep_last else {}
    data.update(payload)
    data["sensor"] = "MQ-135"
    data["gpio_bcm"] = BCM_PIN
    data["updated_at"] = time.time()

    if keep_last and payload.get("error") and current.get("co2_ppm") is not None:
        data["available"] = True
        data["co2_ppm"] = current["co2_ppm"]
        data["co2"] = current.get("co2", current["co2_ppm"])
        data["air_alarm"] = current.get("air_alarm")
        data["co2_state"] = current.get("co2_state")
        data["error"] = None
        data["updated_at"] = current.get("updated_at", data["updated_at"])

    tmp = OUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    tmp.replace(OUT_PATH)


def main() -> int:
    log.info(
        "starting MQ-135 DOUT on BCM GPIO%s → %s (alarm_is_low=%s)",
        BCM_PIN,
        OUT_PATH,
        ALARM_IS_LOW,
    )
    write_status({"available": False, "booting": True, "started": False, "error": None})

    try:
        ensure_input()
    except FileNotFoundError:
        msg = "pinctrl not found (sudo apt install raspi-utils)"
        log.error(msg)
        write_status({"available": False, "booting": False, "started": False, "error": msg})
        return 1
    except Exception as exc:
        log.exception("GPIO setup failed")
        write_status({"available": False, "booting": False, "started": False, "error": str(exc)})
        return 1

    write_status(
        {
            "available": False,
            "booting": True,
            "started": True,
            "error": None,
        }
    )

    fails = 0
    while True:
        try:
            alarm, level = read_alarm()
            ppm = ALARM_PPM if alarm else CLEAN_PPM
            state = "Высокий" if alarm else "Норма"
            fails = 0
            write_status(
                {
                    "available": True,
                    "started": True,
                    "booting": False,
                    "co2_ppm": ppm,
                    "co2": ppm,
                    "air_alarm": alarm,
                    "dout_level": level,
                    "co2_state": state,
                    "error": None,
                }
            )
            append_co2_sample(ppm)
            log.debug("ok alarm=%s level=%s ppm=%s", alarm, level, ppm)
        except Exception as exc:
            fails += 1
            log.warning("read failed (%s): %s", fails, exc)
            write_status(
                {"started": True, "booting": False, "error": str(exc)},
                keep_last=True,
            )
            time.sleep(2)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
