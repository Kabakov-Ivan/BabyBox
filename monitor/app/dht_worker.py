"""Standalone DHT-11 reader. Writes /tmp/babybox-dht.json for the web app.

Run separately from Flask (systemd babybox-dht.service) so Blinka cannot freeze the site.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s DHT %(levelname)s: %(message)s",
)
log = logging.getLogger("dht_worker")

BCM_PIN = int(os.environ.get("DHT_BCM_PIN", "4"))
# 11 = DHT11, 22 = DHT22/AM2302 (некоторые модули подписаны неверно)
DHT_MODEL = os.environ.get("DHT_MODEL", "11").strip()
INTERVAL_SEC = float(os.environ.get("DHT_INTERVAL_SEC", "3"))
OUT_PATH = Path(os.environ.get("DHT_STATUS_FILE", "/tmp/babybox-dht.json"))


def write_status(payload: dict, *, keep_last_reading: bool = False) -> None:
    current = {}
    if keep_last_reading and OUT_PATH.exists():
        try:
            current = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            current = {}

    data = dict(current) if keep_last_reading else {}
    data.update(payload)
    data["sensor"] = "DHT11"
    data["gpio_bcm"] = BCM_PIN
    data["updated_at"] = time.time()

    # If this update is only an error and we already have numbers, keep available=True.
    if (
        keep_last_reading
        and payload.get("error")
        and current.get("temp_c") is not None
        and current.get("humidity_pct") is not None
    ):
        data["available"] = True
        data["temp_c"] = current["temp_c"]
        data["humidity_pct"] = current["humidity_pct"]
        data["temperature"] = current.get("temperature", current["temp_c"])
        data["humidity"] = current.get("humidity", current["humidity_pct"])

    tmp = OUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    tmp.replace(OUT_PATH)


def main() -> int:
    log.info("starting on BCM GPIO %s → %s", BCM_PIN, OUT_PATH)
    write_status({"available": False, "booting": True, "started": False, "error": None})

    try:
        import adafruit_dht
        import board
    except Exception as exc:
        log.exception("import failed")
        write_status({"available": False, "booting": False, "error": f"import failed: {exc}"})
        return 1

    pin = getattr(board, f"D{BCM_PIN}", None)
    if pin is None:
        msg = f"GPIO BCM {BCM_PIN} unavailable on this board"
        log.error(msg)
        write_status({"available": False, "booting": False, "error": msg})
        return 1

    try:
        # use_pulseio=False works more often on Raspberry Pi OS / Bookworm.
        sensor_cls = adafruit_dht.DHT22 if DHT_MODEL == "22" else adafruit_dht.DHT11
        device = sensor_cls(pin, use_pulseio=False)
    except Exception as exc:
        log.exception("open failed")
        write_status({"available": False, "booting": False, "error": f"open failed: {exc}"})
        return 1

    # First read right after open is often empty — give the bus a moment.
    time.sleep(2)

    write_status({"available": False, "booting": True, "started": True, "error": None})
    log.info("device opened (DHT%s) on BCM %s, reading every %ss", DHT_MODEL, BCM_PIN, INTERVAL_SEC)

    fails = 0
    while True:
        try:
            temperature = device.temperature
            humidity = device.humidity
            if temperature is None or humidity is None:
                raise RuntimeError("empty reading")
            fails = 0
            write_status(
                {
                    "available": True,
                    "started": True,
                    "booting": False,
                    "temp_c": round(float(temperature), 1),
                    "humidity_pct": round(float(humidity), 1),
                    "temperature": round(float(temperature), 1),
                    "humidity": round(float(humidity), 1),
                    "error": None,
                }
            )
            log.info("ok temp=%sC humidity=%s%%", temperature, humidity)
        except Exception as exc:
            fails += 1
            log.warning("read failed (%s): %s", fails, exc)
            write_status(
                {
                    "started": True,
                    "booting": False,
                    "error": str(exc),
                },
                keep_last_reading=True,
            )
            # DHT often needs a short recovery pause after checksum errors.
            time.sleep(2)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
