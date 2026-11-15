"""OLED clock on SSD1306 128x64 (soft / bitbang I2C).

Wiring (physical pins → BCM):
  GND → pin 9
  VDD → pin 17 (3.3V)
  SDA → pin 15 (BCM GPIO22)
  SCK → pin 16 (BCM GPIO23)

Must use adafruit_bitbangio — Blinka bitbangio is stubbed on Linux, and
busio.I2C only talks to /dev/i2c-* (hardware I2C1 pins 3/5 stay free
for the power button on BCM GPIO3).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s OLED %(levelname)s: %(message)s",
)
log = logging.getLogger("oled_clock")

SCL_BCM = int(os.environ.get("OLED_SCL_BCM", "23"))
SDA_BCM = int(os.environ.get("OLED_SDA_BCM", "22"))
# Comma-separated list; first successful address wins.
I2C_ADDRS = [
    int(x.strip(), 0)
    for x in os.environ.get("OLED_I2C_ADDR", "0x3C,0x3D").split(",")
    if x.strip()
]
WIDTH = int(os.environ.get("OLED_WIDTH", "128"))
HEIGHT = int(os.environ.get("OLED_HEIGHT", "64"))
POLL_SEC = float(os.environ.get("OLED_POLL_SEC", "1.0"))

FONT_CANDIDATES = [
    Path(os.environ["OLED_FONT"]) if os.environ.get("OLED_FONT") else None,
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]


def _board_pin(bcm: int):
    import board

    pin = getattr(board, f"D{bcm}", None)
    if pin is None:
        raise RuntimeError(f"Blinka board has no D{bcm}")
    return pin


def _find_font_path() -> Path | None:
    for path in FONT_CANDIDATES:
        if path and path.is_file():
            return path
    return None


def _largest_font(draw, text: str, font_path: Path | None, max_w: int, max_h: int):
    from PIL import ImageFont

    if font_path is None:
        return ImageFont.load_default()

    best = ImageFont.truetype(str(font_path), 10)
    lo, hi = 12, 80
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(str(font_path), mid)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= max_w and h <= max_h:
            best = font
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _open_display(i2c):
    import adafruit_ssd1306

    last_exc: Exception | None = None
    for addr in I2C_ADDRS:
        try:
            display = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c, addr=addr)
            display.fill(0)
            display.show()
            log.info("SSD1306 ready at 0x%02X", addr)
            return display
        except Exception as exc:
            last_exc = exc
            log.warning("SSD1306 not at 0x%02X: %s", addr, exc)
    raise RuntimeError(f"SSD1306 not found on {I2C_ADDRS}: {last_exc}")


def main() -> int:
    try:
        import adafruit_bitbangio as bitbangio
        import adafruit_ssd1306  # noqa: F401
        from PIL import Image, ImageDraw
    except ImportError as exc:
        log.error(
            "Missing dependency: %s. "
            "Install: pip install adafruit-circuitpython-ssd1306 "
            "adafruit-circuitpython-bitbangio Pillow",
            exc,
        )
        return 1

    stop = False

    def _stop(*_args) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    scl = _board_pin(SCL_BCM)
    sda = _board_pin(SDA_BCM)
    log.info(
        "Opening SSD1306 %sx%s soft-I2C SCL=BCM%s SDA=BCM%s addrs=%s",
        WIDTH,
        HEIGHT,
        SCL_BCM,
        SDA_BCM,
        [hex(a) for a in I2C_ADDRS],
    )

    i2c = None
    display = None
    try:
        # Software I2C on arbitrary GPIO (not hardware /dev/i2c-1).
        i2c = bitbangio.I2C(scl, sda)
        display = _open_display(i2c)
    except Exception:
        log.error("Failed to init OLED:\n%s", traceback.format_exc())
        if i2c is not None:
            try:
                i2c.deinit()
            except Exception:
                pass
        return 1

    font_path = _find_font_path()
    if font_path:
        log.info("Using font %s", font_path)
    else:
        log.warning("No TTF font found — using tiny default bitmap font")

    image = Image.new("1", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    font = _largest_font(draw, "88:88", font_path, WIDTH - 4, HEIGHT - 4)
    last_text = ""

    log.info("OLED clock started")

    try:
        while not stop:
            now = datetime.now()
            text = now.strftime("%H:%M")
            if text != last_text:
                draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = (WIDTH - tw) // 2 - bbox[0]
                y = (HEIGHT - th) // 2 - bbox[1]
                draw.text((x, y), text, font=font, fill=255)
                display.image(image)
                display.show()
                last_text = text

            time.sleep(max(0.2, POLL_SEC))
    except Exception:
        log.error("OLED loop crashed:\n%s", traceback.format_exc())
        return 1
    finally:
        try:
            if display is not None:
                display.fill(0)
                display.show()
        except Exception:
            pass
        try:
            if i2c is not None:
                i2c.deinit()
        except Exception:
            pass
        log.info("OLED clock stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
