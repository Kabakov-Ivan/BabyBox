"""OLED UI on SSD1306 128x64 (soft / bitbang I2C).

Wiring (physical pins → BCM):
  GND → pin 9
  VDD → pin 17 (3.3V)
  SDA → pin 15 (BCM GPIO22)
  SCK → pin 16 (BCM GPIO23)

Screens (priority):
  1) lamp   — night light toggled ON from panel (3s), then fallback
  2) music  — lullaby playing
  3) wifi   — setup AP is up (hostapd)
  4) time   — default HH:MM
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
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


def _hostapd_active() -> bool:
    try:
        return (
            subprocess.run(
                ["systemctl", "is-active", "--quiet", "hostapd"],
                check=False,
                timeout=1.0,
            ).returncode
            == 0
        )
    except Exception:
        return False


def _resolve_mode(status: dict, now: float) -> str:
    if float(status.get("lamp_until") or 0) > now:
        return "lamp"
    if status.get("lullaby"):
        return "music"
    if _hostapd_active():
        return "wifi"
    return "time"


def _draw_wifi(draw) -> None:
    cx, cy = WIDTH // 2, HEIGHT // 2 + 6
    for r in (14, 24, 34):
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(bbox, start=220, end=320, fill=255, width=3)
    draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=255)


def _draw_music(draw) -> None:
    # Note head + stem + flag, centered.
    hx, hy = WIDTH // 2 - 10, HEIGHT // 2 + 14
    draw.ellipse([hx - 12, hy - 9, hx + 12, hy + 9], fill=255)
    stem_x = hx + 10
    draw.rectangle([stem_x, hy - 34, stem_x + 5, hy], fill=255)
    # Flag
    draw.polygon(
        [
            (stem_x + 5, hy - 34),
            (stem_x + 28, hy - 26),
            (stem_x + 28, hy - 18),
            (stem_x + 5, hy - 24),
        ],
        fill=255,
    )


def _draw_lamp(draw) -> None:
    """Classic outline lightbulb + rays (clean on 1-bit OLED)."""
    cx, cy = WIDTH // 2, HEIGHT // 2 - 2
    # Soft glow rays
    rays = [
        (cx, cy - 34, cx, cy - 26),
        (cx - 24, cy - 24, cx - 17, cy - 17),
        (cx + 24, cy - 24, cx + 17, cy - 17),
        (cx - 30, cy - 6, cx - 22, cy - 6),
        (cx + 30, cy - 6, cx + 22, cy - 6),
    ]
    for x1, y1, x2, y2 in rays:
        draw.line([(x1, y1), (x2, y2)], fill=255, width=2)

    # Bulb glass (outline)
    draw.ellipse([cx - 16, cy - 20, cx + 16, cy + 12], outline=255, width=2)
    # Inner highlight curve
    draw.arc([cx - 10, cy - 14, cx + 2, cy], start=200, end=320, fill=255, width=1)

    # Neck taper
    draw.polygon(
        [(cx - 8, cy + 10), (cx + 8, cy + 10), (cx + 6, cy + 16), (cx - 6, cy + 16)],
        outline=255,
    )
    draw.line([(cx - 8, cy + 10), (cx + 8, cy + 10)], fill=255, width=1)
    draw.line([(cx - 6, cy + 16), (cx + 6, cy + 16)], fill=255, width=1)

    # Screw base
    draw.rectangle([cx - 7, cy + 16, cx + 7, cy + 28], outline=255, width=2)
    draw.line([(cx - 5, cy + 20), (cx + 5, cy + 20)], fill=255, width=1)
    draw.line([(cx - 5, cy + 24), (cx + 5, cy + 24)], fill=255, width=1)
    # Tip
    draw.ellipse([cx - 4, cy + 27, cx + 4, cy + 33], fill=255)


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

    try:
        from oled_status import load as load_status
    except ImportError:
        def load_status():  # type: ignore
            return {"lullaby": False, "lamp_until": 0}

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
    last_key = None

    log.info("OLED UI started")

    try:
        while not stop:
            now = time.time()
            status = load_status()
            mode = _resolve_mode(status, now)
            clock_text = datetime.now().strftime("%H:%M")
            key = (mode, clock_text if mode == "time" else "")

            if key != last_key:
                draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
                if mode == "wifi":
                    _draw_wifi(draw)
                elif mode == "music":
                    _draw_music(draw)
                elif mode == "lamp":
                    _draw_lamp(draw)
                else:
                    _draw_time(draw, font, clock_text)
                display.image(image)
                display.show()
                if last_key is None or (last_key and last_key[0] != mode):
                    log.info("OLED mode → %s", mode)
                last_key = key

            time.sleep(max(0.15, POLL_SEC))
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
        log.info("OLED UI stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
