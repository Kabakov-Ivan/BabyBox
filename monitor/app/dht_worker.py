"""Standalone DHT reader for BabyBox.

Backends (env DHT_BACKEND):
  auto  — prefer Linux IIO (dtoverlay=dht11), else Adafruit
  iio   — only /sys/bus/iio/...
  adafruit — only Blinka/adafruit_dht
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s DHT %(levelname)s: %(message)s",
)
log = logging.getLogger("dht_worker")

BCM_PIN = int(os.environ.get("DHT_BCM_PIN", "17"))
DHT_MODEL = os.environ.get("DHT_MODEL", "11").strip()
BACKEND = os.environ.get("DHT_BACKEND", "auto").strip().lower()
INTERVAL_SEC = float(os.environ.get("DHT_INTERVAL_SEC", "3"))
OUT_PATH = Path(os.environ.get("DHT_STATUS_FILE", "/tmp/babybox-dht.json"))
IIO_ROOT = Path("/sys/bus/iio/devices")


def write_status(payload: dict, *, keep_last_reading: bool = False) -> None:
    current = {}
    if keep_last_reading and OUT_PATH.exists():
        try:
            current = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            current = {}

    data = dict(current) if keep_last_reading else {}
    data.update(payload)
    data["sensor"] = f"DHT{DHT_MODEL}"
    data["gpio_bcm"] = BCM_PIN
    data["updated_at"] = time.time()

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


def find_iio_device() -> Optional[Path]:
    if not IIO_ROOT.exists():
        return None
    for device in sorted(IIO_ROOT.glob("iio:device*")):
        temp = device / "in_temp_input"
        hum = device / "in_humidityrelative_input"
        if temp.exists() and hum.exists():
            return device
    return None


def read_iio(device: Path) -> Tuple[float, float]:
    # IIO reports milli-degrees C and milli-% RH.
    temp_c = int((device / "in_temp_input").read_text().strip()) / 1000.0
    humidity = int((device / "in_humidityrelative_input").read_text().strip()) / 1000.0
    return temp_c, humidity


def loop_iio() -> int:
    device = find_iio_device()
    if device is None:
        write_status(
            {
                "available": False,
                "booting": False,
                "started": False,
                "backend": "iio",
                "error": (
                    "IIO DHT not found. Add to /boot/firmware/config.txt: "
                    f"dtoverlay=dht11,gpiopin={BCM_PIN}  then reboot"
                ),
            }
        )
        log.error("IIO DHT device not found")
        return 1

    log.info("using IIO backend at %s", device)
    write_status(
        {
            "available": False,
            "booting": True,
            "started": True,
            "backend": "iio",
            "error": None,
        }
    )

    fails = 0
    while True:
        try:
            temperature, humidity = read_iio(device)
            fails = 0
            write_status(
                {
                    "available": True,
                    "started": True,
                    "booting": False,
                    "backend": "iio",
                    "temp_c": round(temperature, 1),
                    "humidity_pct": round(humidity, 1),
                    "temperature": round(temperature, 1),
                    "humidity": round(humidity, 1),
                    "error": None,
                }
            )
            log.info("ok temp=%sC humidity=%s%%", temperature, humidity)
        except Exception as exc:
            fails += 1
            log.warning("IIO read failed (%s): %s", fails, exc)
            write_status(
                {"started": True, "booting": False, "backend": "iio", "error": str(exc)},
                keep_last_reading=True,
            )
            time.sleep(2)
        time.sleep(INTERVAL_SEC)


def loop_adafruit() -> int:
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
        sensor_cls = adafruit_dht.DHT22 if DHT_MODEL == "22" else adafruit_dht.DHT11
        device = sensor_cls(pin, use_pulseio=False)
    except Exception as exc:
        log.exception("open failed")
        write_status({"available": False, "booting": False, "error": f"open failed: {exc}"})
        return 1

    time.sleep(2)
    write_status(
        {
            "available": False,
            "booting": True,
            "started": True,
            "backend": "adafruit",
            "error": None,
        }
    )
    log.info("using Adafruit DHT%s on BCM %s", DHT_MODEL, BCM_PIN)

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
                    "backend": "adafruit",
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
                    "backend": "adafruit",
                    "error": str(exc),
                },
                keep_last_reading=True,
            )
            time.sleep(2)
        time.sleep(INTERVAL_SEC)


def main() -> int:
    log.info(
        "starting backend=%s model=%s gpio=%s → %s",
        BACKEND,
        DHT_MODEL,
        BCM_PIN,
        OUT_PATH,
    )
    write_status({"available": False, "booting": True, "started": False, "error": None})

    if BACKEND == "iio":
        return loop_iio()
    if BACKEND == "adafruit":
        return loop_adafruit()

    # auto
    if find_iio_device() is not None:
        return loop_iio()
    log.warning("IIO not present, falling back to Adafruit bitbang")
    return loop_adafruit()


if __name__ == "__main__":
    raise SystemExit(main())
