"""DHT-11 bridge: Flask talks to a child worker process (never imports Blinka)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_BCM_PIN = 4
BOOT_TIMEOUT_SEC = 20.0
WORKER_SCRIPT = Path(__file__).resolve().parent / "dht_worker.py"


class DhtSensor:
    """Reads DHT-11 via subprocess so the web server cannot freeze on GPIO bitbang."""

    def __init__(self, bcm_pin: int = DEFAULT_BCM_PIN) -> None:
        self.bcm_pin = bcm_pin
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._started = False
        self._booting = False
        self._disabled = False
        self._error: Optional[str] = None
        self._temperature_c: Optional[float] = None
        self._humidity_pct: Optional[float] = None
        self._updated_at: Optional[float] = None
        self._boot_started_at: Optional[float] = None

    @property
    def available(self) -> bool:
        return self._temperature_c is not None and self._humidity_pct is not None

    def status(self) -> dict:
        self._expire_boot_if_needed()
        with self._lock:
            payload = {
                "sensor": "DHT11",
                "gpio_bcm": self.bcm_pin,
                "available": self.available,
                "started": self._started,
                "booting": self._booting,
                "error": self._error,
                "updated_at": self._updated_at,
            }
            if self._temperature_c is not None:
                payload["temp_c"] = round(self._temperature_c, 1)
                payload["temperature"] = payload["temp_c"]
            if self._humidity_pct is not None:
                payload["humidity_pct"] = round(self._humidity_pct, 1)
                payload["humidity"] = payload["humidity_pct"]
            return payload

    def start(self) -> bool:
        """Start the worker if needed. Always returns quickly."""
        with self._lock:
            if self._disabled:
                return False
            if self._proc and self._proc.poll() is None:
                return True
            self._booting = True
            self._boot_started_at = time.time()
            self._error = None

            env = os.environ.copy()
            env["DHT_BCM_PIN"] = str(self.bcm_pin)
            env["PYTHONUNBUFFERED"] = "1"

            try:
                self._proc = subprocess.Popen(
                    [sys.executable, str(WORKER_SCRIPT)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                    cwd=str(WORKER_SCRIPT.parent),
                )
            except Exception as exc:
                self._disabled = True
                self._booting = False
                self._error = f"Failed to start DHT worker: {exc}"
                log.exception(self._error)
                return False

            self._started = True
            self._reader = threading.Thread(
                target=self._read_stdout,
                name="dht11-stdout",
                daemon=True,
            )
            self._reader.start()
            threading.Thread(
                target=self._read_stderr,
                name="dht11-stderr",
                daemon=True,
            ).start()
            log.info("DHT-11 worker started (BCM GPIO %s, pid %s)", self.bcm_pin, self._proc.pid)
            return True

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            self._started = False
            self._booting = False
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _expire_boot_if_needed(self) -> None:
        with self._lock:
            if not self._booting or self._boot_started_at is None:
                return
            if time.time() - self._boot_started_at < BOOT_TIMEOUT_SEC:
                return
            self._booting = False
            if self._temperature_c is None:
                self._error = (
                    "DHT worker timeout — check wiring (DATA→pin 7 / GPIO4) "
                    "and that the service user can access GPIO"
                )
                log.warning(self._error)

    def _apply_payload(self, payload: dict) -> None:
        with self._lock:
            if "error" in payload and "temp_c" not in payload:
                # Keep last good values; only record error when we have nothing yet.
                if self._temperature_c is None:
                    self._error = str(payload["error"])
                return
            if payload.get("ready"):
                return
            if "temp_c" in payload and "humidity_pct" in payload:
                self._temperature_c = float(payload["temp_c"])
                self._humidity_pct = float(payload["humidity_pct"])
                self._updated_at = time.time()
                self._error = None
                self._booting = False

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                log.debug("DHT worker bad line: %r", line)
                continue
            if isinstance(payload, dict):
                self._apply_payload(payload)
        with self._lock:
            code = proc.poll()
            self._booting = False
            if self._temperature_c is None:
                self._error = f"DHT worker exited (code {code})"
                self._disabled = True
            self._started = False

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            text = line.strip()
            if text:
                log.warning("DHT worker: %s", text)


dht = DhtSensor()
