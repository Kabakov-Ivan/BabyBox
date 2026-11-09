"""Power button on BCM GPIO3 (phys pin 5) ↔ GND (phys pin 20).

Press → shutdown. The same GPIO3 short wakes the Pi from halt (firmware).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from signal import pause

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s POWER %(levelname)s: %(message)s",
)
log = logging.getLogger("power_button")

BCM_PIN = int(os.environ.get("POWER_BTN_BCM", "3"))
# Hold a moment so noise / bounce doesn't kill the box instantly.
HOLD_SEC = float(os.environ.get("POWER_BTN_HOLD_SEC", "0.8"))


def shutdown() -> None:
    log.info("Power button held — shutting down")
    subprocess.run(["/sbin/shutdown", "-h", "now"], check=False)


def main() -> int:
    try:
        from gpiozero import Button
    except ImportError:
        log.error("gpiozero not installed. On Pi: sudo apt install -y python3-gpiozero")
        return 1

    button = Button(BCM_PIN, pull_up=True, bounce_time=0.05, hold_time=HOLD_SEC)
    button.when_pressed = lambda: log.info("button pressed (hold %.1fs to shutdown)", HOLD_SEC)
    button.when_released = lambda: log.info("button released")
    button.when_held = shutdown
    log.info(
        "Listening BCM GPIO %s (phys pin 5). Hold ~%.1fs to shutdown.",
        BCM_PIN,
        HOLD_SEC,
    )
    pause()
    return 0


if __name__ == "__main__":
    sys.exit(main())
