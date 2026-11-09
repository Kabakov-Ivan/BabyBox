"""DHT-11 temperature / humidity reader for Raspberry Pi GPIO."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

# Physical pin 7 on the 40-pin header == BCM GPIO 4
DEFAULT_BCM_PIN = 4
READ_INTERVAL_SEC = 3.0
MAX_RETRIES = 3


class DhtSensor:
    """Background DHT-11 reader with last-good-value cache."""

    def __init__(self, bcm_pin: int = DEFAULT_BCM_PIN) -> None:
        self.bcm_pin = bcm_pin
        self._lock = threading.Lock()
        self._device = None
        self._thread: Optional[threading.Thread] = None
        self._boot_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._started = False
        self._booting = False
        self._disabled = False
        self._error: Optional[str] = None
        self._temperature_c: Optional[float] = None
        self._humidity_pct: Optional[float] = None
        self._updated_at: Optional[float] = None

    @property
    def available(self) -> bool:
        return self._started and self._error is None and self._temperature_c is not None

    def status(self) -> dict:
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
        """Kick off DHT init in a background thread (never blocks the web server)."""
        with self._lock:
            if self._disabled or self._started or self._booting:
                return self._started and not self._disabled
            self._booting = True
            self._boot_thread = threading.Thread(
                target=self._boot,
                name="dht11-boot",
                daemon=True,
            )
            self._boot_thread.start()
            return True

    def _boot(self) -> None:
        try:
            import adafruit_dht
            import board
        except ImportError as exc:
            with self._lock:
                self._disabled = True
                self._booting = False
                self._error = (
                    "DHT library missing — "
                    "pip install adafruit-circuitpython-dht Adafruit-Blinka"
                )
            log.warning("%s (%s)", self._error, exc)
            return
        except Exception as exc:
            with self._lock:
                self._disabled = True
                self._booting = False
                self._error = f"DHT import failed: {exc}"
            log.exception(self._error)
            return

        pin = getattr(board, f"D{self.bcm_pin}", None)
        if pin is None:
            with self._lock:
                self._disabled = True
                self._booting = False
                self._error = f"GPIO BCM {self.bcm_pin} is not available on this board"
            log.error(self._error)
            return

        try:
            # use_pulseio=False is more reliable on recent Raspberry Pi OS.
            device = adafruit_dht.DHT11(pin, use_pulseio=False)
        except Exception as exc:
            with self._lock:
                self._disabled = True
                self._booting = False
                self._error = f"Failed to open DHT-11 on GPIO {self.bcm_pin}: {exc}"
                self._device = None
            log.exception(self._error)
            return

        with self._lock:
            self._device = device
            self._error = None
            self._started = True
            self._booting = False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._poll_loop,
                name="dht11-reader",
                daemon=True,
            )
            self._thread.start()
        log.info("DHT-11 reader started on BCM GPIO %s", self.bcm_pin)

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        self._stop.set()
        thread = self._thread
        device = self._device
        self._thread = None
        self._device = None
        self._started = False
        self._booting = False
        if thread and thread.is_alive() and thread is not threading.current_thread():
            # Join outside would be safer; keep short to avoid hanging stop().
            thread.join(timeout=2.0)
        if device is not None:
            try:
                device.exit()
            except Exception:
                pass

    def _poll_loop(self) -> None:
        while not self._stop.wait(READ_INTERVAL_SEC):
            self._read_once()

    def _read_once(self) -> None:
        with self._lock:
            device = self._device
        if device is None:
            return

        last_error: Optional[str] = None
        for _ in range(MAX_RETRIES):
            try:
                temperature = device.temperature
                humidity = device.humidity
                if temperature is None or humidity is None:
                    last_error = "DHT-11 returned empty values"
                    time.sleep(0.2)
                    continue
                with self._lock:
                    self._temperature_c = float(temperature)
                    self._humidity_pct = float(humidity)
                    self._updated_at = time.time()
                    self._error = None
                return
            except Exception as exc:
                # DHT checksum / timing failures are common; keep last good reading.
                last_error = str(exc)
                time.sleep(0.25)

        if last_error and self._temperature_c is None:
            with self._lock:
                self._error = last_error
            log.debug("DHT-11 read failed: %s", last_error)


dht = DhtSensor()
