"""Night light LED on BCM GPIO26 (phys pin 37), GND on phys pin 39."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from typing import Optional

log = logging.getLogger(__name__)

BCM_PIN = int(os.environ.get("NIGHTLIGHT_BCM", "26"))
# Active-high: GPIO high → LED on (LED to GPIO, other side to GND via resistor/module).
ACTIVE_HIGH = os.environ.get("NIGHTLIGHT_ACTIVE_HIGH", "1") != "0"


class NightLight:
    def __init__(self, bcm_pin: int = BCM_PIN) -> None:
        self.bcm_pin = bcm_pin
        self._lock = threading.Lock()
        self._on = False
        self._ready = False
        self._error: Optional[str] = None

    def status(self) -> dict:
        with self._lock:
            return {
                "light": self._on,
                "gpio_bcm": self.bcm_pin,
                "ready": self._ready,
                "error": self._error,
            }

    def is_on(self) -> bool:
        with self._lock:
            return self._on

    def _pinctrl(self, *args: str) -> str:
        return subprocess.check_output(
            ["pinctrl", *args],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=0.8,
        )

    def _ensure_output(self) -> None:
        if self._ready:
            return
        try:
            # Output mode; start low (off for active-high).
            self._pinctrl("set", str(self.bcm_pin), "op", "dl")
            self._ready = True
            self._error = None
            log.info("Night light ready on BCM GPIO %s", self.bcm_pin)
        except FileNotFoundError:
            self._error = "pinctrl not found (sudo apt install raspi-utils)"
            raise
        except Exception as exc:
            self._error = str(exc)
            raise

    def set(self, on: bool) -> bool:
        with self._lock:
            try:
                self._ensure_output()
                drive = "dh" if (on if ACTIVE_HIGH else not on) else "dl"
                self._pinctrl("set", str(self.bcm_pin), "op", drive)
                self._on = bool(on)
                self._error = None
                log.info("Night light %s", "ON" if self._on else "OFF")
                return True
            except Exception as exc:
                self._error = str(exc)
                log.warning("Night light set failed: %s", exc)
                return False

    def read_level(self) -> Optional[int]:
        try:
            out = self._pinctrl("get", str(self.bcm_pin))
        except Exception:
            return None
        match = re.search(r"level=(\d)", out)
        if match:
            return int(match.group(1))
        if re.search(r"\|\s*hi\b", out, re.IGNORECASE):
            return 1
        if re.search(r"\|\s*lo\b", out, re.IGNORECASE):
            return 0
        return None


nightlight = NightLight()
