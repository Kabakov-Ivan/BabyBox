"""Power button on BCM GPIO3 (phys pin 5) ↔ GND (phys pin 20).

GPIO3 is a special pin (fixed pull-up / I2C SCL) — gpiozero/lgpio often cannot
claim it. We poll level via `pinctrl` instead.

Press+hold → shutdown. Shorting GPIO3 to GND while halted still wakes the Pi.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s POWER %(levelname)s: %(message)s",
)
log = logging.getLogger("power_button")

BCM_PIN = int(os.environ.get("POWER_BTN_BCM", "3"))
HOLD_SEC = float(os.environ.get("POWER_BTN_HOLD_SEC", "0.8"))
POLL_SEC = float(os.environ.get("POWER_BTN_POLL_SEC", "0.05"))


def read_level(pin: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["pinctrl", "get", str(pin)],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=1,
        )
    except FileNotFoundError:
        log.error("pinctrl not found. Install: sudo apt install -y raspi-utils")
        raise
    except Exception as exc:
        log.warning("pinctrl get failed: %s", exc)
        return None

    # Formats seen across Pi OS builds:
    #   "3: ip ... | hi // GPIO3 = input"
    #   "... level=1 ..."
    match = re.search(r"level=(\d)", out)
    if match:
        return int(match.group(1))
    if re.search(r"\|\s*hi\b", out, re.IGNORECASE):
        return 1
    if re.search(r"\|\s*lo\b", out, re.IGNORECASE):
        return 0
    log.warning("unexpected pinctrl output: %r", out.strip())
    return None


def shutdown() -> None:
    log.info("Power button held — shutting down")
    subprocess.run(["/sbin/shutdown", "-h", "now"], check=False)


def main() -> int:
    # Make sure pin is an input with pull-up (safe if already so).
    try:
        subprocess.run(
            ["pinctrl", "set", str(BCM_PIN), "ip", "pu"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except Exception as exc:
        log.warning("pinctrl set skipped: %s", exc)

    level = read_level(BCM_PIN)
    if level is None:
        return 1

    log.info(
        "Listening BCM GPIO %s via pinctrl (level=%s). Hold ~%.1fs to shutdown.",
        BCM_PIN,
        level,
        HOLD_SEC,
    )

    pressed_since: float | None = None
    last_level = level

    while True:
        level = read_level(BCM_PIN)
        if level is None:
            time.sleep(0.5)
            continue

        if level != last_level:
            log.info("GPIO%s level %s → %s", BCM_PIN, last_level, level)
            last_level = level

        # Active low: pressed = 0 (to GND)
        if level == 0:
            now = time.monotonic()
            if pressed_since is None:
                pressed_since = now
                log.info("button pressed")
            elif now - pressed_since >= HOLD_SEC:
                shutdown()
                time.sleep(60)
                pressed_since = None
        else:
            if pressed_since is not None:
                log.info("button released")
            pressed_since = None

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    sys.exit(main())
