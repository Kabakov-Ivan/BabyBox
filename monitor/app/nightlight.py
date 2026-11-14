"""Night light LED + ambient light sensor.

LED:        BCM GPIO26 (phys pin 37), GND pin 39
Light DO:   BCM GPIO27 (phys pin 13), VCC 3.3V pin 1, GND pin 6

Auto mode reads /home/admin/Save_BabyBox/nightlight/nightlight.jsonl
(`enabled: true` → dark turns LED on, bright turns it off).
Manual OFF while auto is enabled disables auto mode.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

LED_BCM = int(os.environ.get("NIGHTLIGHT_BCM", "26"))
LIGHT_BCM = int(os.environ.get("LIGHT_SENSOR_BCM", "27"))
# Active-high LED: GPIO high → on.
LED_ACTIVE_HIGH = os.environ.get("NIGHTLIGHT_ACTIVE_HIGH", "1") != "0"
# Many LM393 light modules: DO=HIGH when dark, DO=LOW when bright.
DARK_IS_HIGH = os.environ.get("LIGHT_DARK_IS_HIGH", "1") != "0"
AUTO_POLL_SEC = float(os.environ.get("NIGHTLIGHT_AUTO_POLL_SEC", "1.5"))


class NightLight:
    def __init__(self, led_pin: int = LED_BCM, light_pin: int = LIGHT_BCM) -> None:
        self.led_pin = led_pin
        self.light_pin = light_pin
        self._lock = threading.Lock()
        self._on = False
        self._led_ready = False
        self._sensor_ready = False
        self._error: Optional[str] = None
        self._sensor_error: Optional[str] = None
        self._dark: Optional[bool] = None
        self._auto_enabled = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def status(self) -> dict:
        with self._lock:
            return {
                "light": self._on,
                "gpio_bcm": self.led_pin,
                "ready": self._led_ready,
                "error": self._error,
                "light_sensor_gpio": self.light_pin,
                "dark": self._dark,
                "autonight_enabled": self._auto_enabled,
                "sensor_error": self._sensor_error,
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

    @staticmethod
    def _parse_level(out: str) -> Optional[int]:
        match = re.search(r"level=(\d)", out)
        if match:
            return int(match.group(1))
        if re.search(r"\|\s*hi\b", out, re.IGNORECASE):
            return 1
        if re.search(r"\|\s*lo\b", out, re.IGNORECASE):
            return 0
        return None

    def _ensure_led(self) -> None:
        if self._led_ready:
            return
        self._pinctrl("set", str(self.led_pin), "op", "dl")
        self._led_ready = True
        self._error = None
        log.info("Night light LED ready on BCM GPIO %s", self.led_pin)

    def _ensure_sensor(self) -> None:
        if self._sensor_ready:
            return
        # Digital input with pull-up (module DO is open-collector style on many boards).
        self._pinctrl("set", str(self.light_pin), "ip", "pu")
        self._sensor_ready = True
        self._sensor_error = None
        log.info("Light sensor ready on BCM GPIO %s", self.light_pin)

    def set(self, on: bool, *, source: str = "manual") -> bool:
        """Turn LED on/off. source=manual|auto."""
        disable_auto = False
        with self._lock:
            try:
                self._ensure_led()
                drive_high = on if LED_ACTIVE_HIGH else (not on)
                self._pinctrl("set", str(self.led_pin), "op", "dh" if drive_high else "dl")
                was_on = self._on
                self._on = bool(on)
                self._error = None
                if source == "manual" and was_on and not self._on and self._auto_enabled:
                    # User turned off an auto-lit night light → leave auto mode.
                    self._auto_enabled = False
                    disable_auto = True
                log.info(
                    "Night light %s (%s)%s",
                    "ON" if self._on else "OFF",
                    source,
                    " · auto disabled" if disable_auto else "",
                )
            except FileNotFoundError:
                self._error = "pinctrl not found (sudo apt install raspi-utils)"
                log.warning(self._error)
                return False
            except Exception as exc:
                self._error = str(exc)
                log.warning("Night light set failed: %s", exc)
                return False

        if disable_auto:
            try:
                import settings_store
                settings_store.save_autonight(False)
            except Exception as exc:
                log.warning("Could not save autonight=false: %s", exc)
        return True

    def read_dark(self) -> Optional[bool]:
        """Return True when room is dark, False when bright, None on error."""
        try:
            self._ensure_sensor()
            out = self._pinctrl("get", str(self.light_pin))
            level = self._parse_level(out)
            if level is None:
                self._sensor_error = f"bad pinctrl output: {out.strip()!r}"
                return None
            dark = bool(level) if DARK_IS_HIGH else (not bool(level))
            with self._lock:
                self._dark = dark
                self._sensor_error = None
            return dark
        except Exception as exc:
            with self._lock:
                self._sensor_error = str(exc)
            log.debug("Light sensor read failed: %s", exc)
            return None

    def set_auto_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._auto_enabled = bool(enabled)
        log.info("Autonight %s", "enabled" if enabled else "disabled")
        if enabled:
            self._apply_auto_once()

    def refresh_auto_from_disk(self) -> bool:
        try:
            import settings_store
            row = settings_store.load_autonight() or {}
            enabled = bool(row.get("enabled")) if row else False
        except Exception:
            enabled = False
        with self._lock:
            self._auto_enabled = enabled
        return enabled

    def _apply_auto_once(self) -> None:
        with self._lock:
            if not self._auto_enabled:
                return
        dark = self.read_dark()
        if dark is None:
            return
        # dark → on, bright → off
        desired = bool(dark)
        with self._lock:
            if self._on == desired:
                return
        self.set(desired, source="auto")

    def start_auto_loop(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.refresh_auto_from_disk()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._auto_loop,
            name="nightlight-auto",
            daemon=True,
        )
        self._thread.start()

    def _auto_loop(self) -> None:
        log.info(
            "Nightlight auto loop started (LED GPIO%s, sensor GPIO%s, poll %.1fs)",
            self.led_pin,
            self.light_pin,
            AUTO_POLL_SEC,
        )
        while not self._stop.wait(AUTO_POLL_SEC):
            try:
                self.refresh_auto_from_disk()
                with self._lock:
                    enabled = self._auto_enabled
                if not enabled:
                    continue
                self._apply_auto_once()
            except Exception:
                log.exception("Autonight loop error")


nightlight = NightLight()
