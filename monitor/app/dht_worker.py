"""Standalone DHT-11 reader process.

Runs outside the Flask process so bitbang / Blinka cannot freeze the web server.
Prints one JSON object per line to stdout.
"""

from __future__ import annotations

import json
import os
import sys
import time

BCM_PIN = int(os.environ.get("DHT_BCM_PIN", "4"))
INTERVAL_SEC = float(os.environ.get("DHT_INTERVAL_SEC", "3"))


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        import adafruit_dht
        import board
    except Exception as exc:
        emit({"error": f"import failed: {exc}"})
        return 1

    pin = getattr(board, f"D{BCM_PIN}", None)
    if pin is None:
        emit({"error": f"GPIO BCM {BCM_PIN} unavailable"})
        return 1

    try:
        device = adafruit_dht.DHT11(pin, use_pulseio=False)
    except Exception as exc:
        emit({"error": f"open failed: {exc}"})
        return 1

    emit({"ready": True, "gpio_bcm": BCM_PIN})

    while True:
        try:
            temperature = device.temperature
            humidity = device.humidity
            if temperature is None or humidity is None:
                emit({"error": "empty reading"})
            else:
                emit(
                    {
                        "temp_c": float(temperature),
                        "humidity_pct": float(humidity),
                    }
                )
        except Exception as exc:
            emit({"error": str(exc)})
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
