"""Optional DHT-11 status from /tmp/babybox-dht.json.

Flask never starts GPIO workers and never imports Blinka.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STATUS_FILE = Path(os.environ.get("DHT_STATUS_FILE", "/tmp/babybox-dht.json"))


class DhtSensor:
    def start(self) -> bool:
        # No-op: web process must never touch DHT hardware.
        return True

    @property
    def available(self) -> bool:
        return bool(self.status().get("available"))

    def status(self) -> dict:
        payload = {
            "sensor": "DHT11",
            "gpio_bcm": 4,
            "available": False,
            "started": False,
            "booting": False,
            "error": None,
            "updated_at": None,
        }
        try:
            data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                payload.update(data)
        except FileNotFoundError:
            payload["error"] = "DHT worker not running"
        except Exception as exc:
            payload["error"] = str(exc)
        return payload


dht = DhtSensor()
