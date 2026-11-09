"""Optional power-button watcher (fallback).

Prefer kernel overlay instead — see scripts/enable-power-button.sh:
  dtoverlay=gpio-shutdown,gpio_pin=3

This process must NOT spawn pinctrl in a tight loop (it freezes the Pi).
Default poll is slow; set POWER_BTN_POLL_SEC only if you know what you are doing.
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
HOLD_SEC = float(os.environ.get("POWER_BTN_HOLD_SEC", "1.0"))
# Keep this high — each read is a subprocess.
POLL_SEC = float(os.environ.get("POWER_BTN_POLL_SEC", "0.35"))


def read_level(pin: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["pinctrl", "get", str(pin)],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=0.4,
        )
    except FileNotFoundError:
        log.error("pinctrl not found. Install: sudo apt install -y raspi-utils")
        raise
    except Exception as exc:
        log.warning("pinctrl get failed: %s", exc)
        return None

    match = re.search(r"level=(\d)", out)
    if match:
        return int(match.group(1))
    if re.search(r"\|\s*hi\b", out, re.IGNORECASE):
        return 1
    if re.search(r"\|\s*lo\b", out, re.IGNORECASE):
        return 0
    return None


def shutdown() -> None:
    log.info("Power button held — shutting down")
    subprocess.run(["/sbin/shutdown", "-h", "now"], check=False)


def main() -> int:
    log.warning(
        "Userspace power button is a fallback. Prefer dtoverlay=gpio-shutdown "
        "(see enable-power-button.sh). Polling every %.2fs.",
        POLL_SEC,
    )
    try:
        subprocess.run(
            ["pinctrl", "set", str(BCM_PIN), "ip", "pu"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.4,
        )
    except Exception:
        pass

    level = read_level(BCM_PIN)
    if level is None:
        return 1

    log.info("Listening BCM GPIO %s (level=%s). Hold ~%.1fs.", BCM_PIN, level, HOLD_SEC)
    pressed_since: float | None = None
    last_level = level

    while True:
        level = read_level(BCM_PIN)
        if level is None:
            time.sleep(1.0)
            continue

        if level != last_level:
            log.info("GPIO%s %s → %s", BCM_PIN, last_level, level)
            last_level = level

        if level == 0:
            now = time.monotonic()
            if pressed_since is None:
                pressed_since = now
            elif now - pressed_since >= HOLD_SEC:
                shutdown()
                time.sleep(60)
                pressed_since = None
        else:
            pressed_since = None

        time.sleep(max(POLL_SEC, 0.2))


if __name__ == "__main__":
    sys.exit(main())
