"""Standalone DHT-11 reader. Writes /tmp/babybox-dht.json for the web app."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

BCM_PIN = int(os.environ.get("DHT_BCM_PIN", "4"))
INTERVAL_SEC = float(os.environ.get("DHT_INTERVAL_SEC", "3"))
OUT_PATH = Path(os.environ.get("DHT_STATUS_FILE", "/tmp/babybox-dht.json"))


def write_status(payload: dict) -> None:
    payload = dict(payload)
    payload["sensor"] = "DHT11"
    payload["gpio_bcm"] = BCM_PIN
    payload["updated_at"] = time.time()
    tmp = OUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    tmp.replace(OUT_PATH)


def main() -> int:
    write_status({"available": False, "booting": True})

    try:
        import adafruit_dht
        import board
    except Exception as exc:
        write_status({"available": False, "error": f"import failed: {exc}"})
        return 1

    pin = getattr(board, f"D{BCM_PIN}", None)
    if pin is None:
        write_status({"available": False, "error": f"GPIO BCM {BCM_PIN} unavailable"})
        return 1

    try:
        device = adafruit_dht.DHT11(pin, use_pulseio=False)
    except Exception as exc:
        write_status({"available": False, "error": f"open failed: {exc}"})
        return 1

    write_status({"available": False, "booting": True, "started": True})

    while True:
        try:
            temperature = device.temperature
            humidity = device.humidity
            if temperature is None or humidity is None:
                raise RuntimeError("empty reading")
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
        except Exception as exc:
            # Keep previous file contents on transient checksum errors when possible.
            write_status(
                {
                    "available": False,
                    "started": True,
                    "booting": False,
                    "error": str(exc),
                }
            )
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
