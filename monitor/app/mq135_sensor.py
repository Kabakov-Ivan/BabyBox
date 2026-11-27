"""Optional MQ-135 status from /tmp/babybox-mq135.json.

Flask never starts the GPIO worker — babybox-mq135.service does.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STATUS_FILE = Path(os.environ.get("MQ135_STATUS_FILE", "/tmp/babybox-mq135.json"))


class Mq135Sensor:
    def start(self) -> bool:
        return True

    @property
    def available(self) -> bool:
        return bool(self.status().get("available"))

    def status(self) -> dict:
        payload = {
            "mq135_sensor": "MQ-135",
            "mq135_gpio_bcm": 17,
            "mq135_available": False,
            "co2_ppm": None,
            "co2": None,
            "air_alarm": None,
            "co2_state": None,
            "mq135_error": None,
            "mq135_updated_at": None,
        }
        try:
            data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return payload
            payload["mq135_available"] = bool(data.get("available"))
            payload["mq135_gpio_bcm"] = data.get("gpio_bcm", 17)
            payload["mq135_updated_at"] = data.get("updated_at")
            payload["mq135_error"] = data.get("error")
            if data.get("co2_ppm") is not None:
                payload["co2_ppm"] = data["co2_ppm"]
                payload["co2"] = data.get("co2", data["co2_ppm"])
            if "air_alarm" in data:
                payload["air_alarm"] = data["air_alarm"]
            if data.get("co2_state"):
                payload["co2_state"] = data["co2_state"]
        except FileNotFoundError:
            payload["mq135_error"] = "MQ-135 worker not running"
        except Exception as exc:
            payload["mq135_error"] = str(exc)
        return payload


mq135 = Mq135Sensor()
