"""Read DHT-11 status from a JSON file written by dht_worker.py.

The Flask process never imports Blinka / touches GPIO, so the web UI cannot hang.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_BCM_PIN = 4
STATUS_FILE = Path(os.environ.get("DHT_STATUS_FILE", "/tmp/babybox-dht.json"))
WORKER_SCRIPT = Path(__file__).resolve().parent / "dht_worker.py"


class DhtSensor:
    def __init__(self, bcm_pin: int = DEFAULT_BCM_PIN) -> None:
        self.bcm_pin = bcm_pin
        self._lock = threading.Lock()
        self._worker_started = False

    def start(self) -> bool:
        """Launch background worker once (detached). Safe to call on every request."""
        with self._lock:
            if self._worker_started:
                return True
            if self._worker_already_running():
                self._worker_started = True
                return True
            try:
                subprocess.Popen(
                    [sys.executable, str(WORKER_SCRIPT)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    cwd=str(WORKER_SCRIPT.parent),
                    env={
                        **os.environ,
                        "DHT_BCM_PIN": str(self.bcm_pin),
                        "DHT_STATUS_FILE": str(STATUS_FILE),
                        "PYTHONUNBUFFERED": "1",
                    },
                )
                self._worker_started = True
                log.info("Started DHT worker for BCM GPIO %s", self.bcm_pin)
                return True
            except Exception as exc:
                log.warning("Could not start DHT worker: %s", exc)
                return False

    def _worker_already_running(self) -> bool:
        try:
            import glob
            for path in glob.glob("/proc/[0-9]*/cmdline"):
                try:
                    raw = Path(path).read_bytes().replace(b"\x00", b" ")
                except OSError:
                    continue
                if b"dht_worker.py" in raw:
                    return True
        except Exception:
            pass
        return False

    def status(self) -> dict:
        payload = {
            "sensor": "DHT11",
            "gpio_bcm": self.bcm_pin,
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
            payload["error"] = "waiting for DHT worker"
            payload["booting"] = True
        except Exception as exc:
            payload["error"] = str(exc)
        return payload

    @property
    def available(self) -> bool:
        return bool(self.status().get("available"))


dht = DhtSensor()
