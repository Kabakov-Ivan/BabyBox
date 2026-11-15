"""OLED clock on SSD1306 128x64 (soft / bitbang I2C).

Wiring: GND→9, VDD→17, SDA→15 (BCM22), SCK→16 (BCM23)

Default: large HH:MM
Overlays from panel (via /tmp/babybox-oled.json):
  lamp  — night light ON, 3 seconds, then back to clock/music
  music — lullaby playing
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
I2C_ADDRS = [
    int(x.strip(), 0)
    for x in os.environ.get("OLED_I2C_ADDR", "0x3C,0x3D").split(",")
    if x.strip()
]
WIDTH = int(os.environ.get("OLED_WIDTH", "128"))
HEIGHT = int(os.environ.get("OLED_HEIGHT", "64"))
POLL_SEC = float(os.environ.get("OLED_POLL_SEC", "0.25"))

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


def _load_status() -> dict:
    try:
        from oled_status import load

        return load()
    except Exception:
        return {"lullaby": False, "lamp_until": 0}


def _resolve_mode(status: dict, now: float) -> str:
    if float(status.get("lamp_until") or 0) > now:
        return "lamp"
    if status.get("lullaby"):
        return "music"
    return "time"


def _draw_music(draw) -> None:
    hx, hy = WIDTH // 2 - 8, HEIGHT // 2 + 12
    draw.ellipse([hx - 10, hy - 8, hx + 10, hy + 8], fill=255)
    stem_x = hx + 8
    draw.rectangle([stem_x, hy - 32, stem_x + 4, hy], fill=255)
    draw.polygon(
        [
            (stem_x + 4, hy - 32),
            (stem_x + 24, hy - 24),
            (stem_x + 24, hy - 16),
            (stem_x + 4, hy - 22),
        ],
        fill=255,
    )


def _draw_lamp(draw) -> None:
    """Simple outline bulb + rays."""
    cx, cy = WIDTH // 2, HEIGHT // 2 - 2
    for x1, y1, x2, y2 in (
        (cx, cy - 30, cx, cy - 22),
        (cx - 20, cy - 22, cx - 14, cy - 16),
        (cx + 20, cy - 22, cx + 14, cy - 16),
        (cx - 26, cy - 4, cx - 18, cy - 4),
        (cx + 26, cy - 4, cx + 18, cy - 4),
    ):
        draw.line([(x1, y1), (x2, y2)], fill=255)

    draw.ellipse([cx - 14, cy - 18, cx + 14, cy + 10], outline=255)
    draw.rectangle([cx - 6, cy + 10, cx + 6, cy + 22], outline=255)
    draw.line([(cx - 4, cy + 14), (cx + 4, cy + 14)], fill=255)
    draw.line([(cx - 4, cy + 18), (cx + 4, cy + 18)], fill=255)
    draw.ellipse([cx - 3, cy + 22, cx + 3, cy + 28], fill=255)


def _draw_time(draw, font, text: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (WIDTH - tw) // 2 - bbox[0]
    y = (HEIGHT - th) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=255)


def main() -> int:
    try:
        import adafruit_bitbangio as bitbangio
        from PIL import Image, ImageDraw
    except ImportError as exc:
        log.error("Missing dependency: %s", exc)
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
        "Opening SSD1306 soft-I2C SCL=BCM%s SDA=BCM%s addrs=%s",
        SCL_BCM,
        SDA_BCM,
        [hex(a) for a in I2C_ADDRS],
    )

    i2c = None
    display = None
    try:
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
    image = Image.new("1", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    font = _largest_font(draw, "88:88", font_path, WIDTH - 4, HEIGHT - 4)
    last_key = None
    log.info("OLED clock started")

    try:
        while not stop:
            try:
                now = time.time()
                status = _load_status()
                mode = _resolve_mode(status, now)
                clock_text = datetime.now().strftime("%H:%M")
                key = (mode, clock_text if mode == "time" else "")

                if key != last_key:
                    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
                    if mode == "music":
                        _draw_music(draw)
                    elif mode == "lamp":
                        _draw_lamp(draw)
                    else:
                        _draw_time(draw, font, clock_text)
                    display.image(image)
                    display.show()
                    if last_key is None or last_key[0] != mode:
                        log.info("OLED mode → %s", mode)
                    last_key = key
            except Exception:
                log.error("OLED frame failed:\n%s", traceback.format_exc())
                last_key = None
                time.sleep(1.0)
                continue

            time.sleep(max(0.15, POLL_SEC))
    finally:
        try:
            if i2c is not None:
                i2c.deinit()
        except Exception:
            pass
        log.info("OLED clock stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
