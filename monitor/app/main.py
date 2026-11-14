from flask import Flask, render_template, request, jsonify, Response, send_from_directory
import subprocess
import re
import json
import threading
import time
from pathlib import Path

from camera_stream import BOUNDARY, camera
from dht_sensor import dht
from media_store import media_store
from nightlight import nightlight
import settings_store
from sensor_history import day_report

# Start with LED off.
nightlight.set(False)

MONITOR_ROOT = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(MONITOR_ROOT / "templates"),
    static_folder=str(MONITOR_ROOT / "static"),
)
BOUNDARY_NAME = BOUNDARY.decode("ascii")
IMG_DIR = MONITOR_ROOT / "img"
SOUNDS_DIR = MONITOR_ROOT / "sounds"
AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@app.route("/img/<path:filename>")
def img_files(filename):
    return send_from_directory(IMG_DIR, filename)


@app.route("/sounds/<path:filename>")
def sound_file(filename):
    return send_from_directory(SOUNDS_DIR, filename, conditional=True)


def _profile_has_content(profile: dict) -> bool:
    return bool(
        str(profile.get("first_name") or "").strip()
        or str(profile.get("last_name") or "").strip()
        or str(profile.get("email") or "").strip()
        or profile.get("avatar")
    )


@app.route("/api/profile", methods=["GET", "POST"])
def api_profile():
    if request.method == "GET":
        try:
            profile = settings_store.load_profile() or {}
            avatar = profile.get("avatar")
            profile["avatar_url"] = f"/api/profile/avatar/{avatar}" if avatar else None
            return jsonify(profile=profile, saved=_profile_has_content(profile))
        except OSError:
            return jsonify(saved=False, error="Нет доступа к папке профиля на устройстве"), 503

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    if len(first_name) > 80 or len(last_name) > 80 or len(email) > 254:
        return jsonify(error="Проверьте длину полей профиля"), 400
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Укажите корректный адрес почты"), 400

    try:
        old = settings_store.load_profile() or {}
    except OSError:
        return jsonify(saved=False, error="Нет доступа к папке профиля на устройстве"), 503

    avatar_file = request.files.get("avatar")
    avatar_name = old.get("avatar")
    if avatar_file and avatar_file.filename:
        suffix = Path(avatar_file.filename).suffix.lower()
        if suffix not in AVATAR_EXTENSIONS:
            return jsonify(error="Аватар должен быть JPG, PNG или WebP"), 400
        data = avatar_file.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            return jsonify(error="Размер аватара не должен превышать 4 МБ"), 413
        avatar_name = f"avatar{suffix}"
        try:
            settings_store.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            for stale in settings_store.PROFILE_DIR.glob("avatar.*"):
                if stale.name != avatar_name:
                    try:
                        stale.unlink()
                    except OSError:
                        pass
            (settings_store.PROFILE_DIR / avatar_name).write_bytes(data)
        except OSError:
            return jsonify(saved=False, error="Нет доступа к папке профиля на устройстве"), 503

    profile = {
        "ts": int(time.time()),
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "avatar": avatar_name,
    }
    try:
        settings_store.save_profile(profile)
    except OSError:
        return jsonify(saved=False, error="Нет доступа к папке профиля на устройстве"), 503
    profile["avatar_url"] = f"/api/profile/avatar/{avatar_name}" if avatar_name else None
    return jsonify(saved=True, profile=profile)


@app.route("/api/profile/avatar/<path:filename>")
def api_profile_avatar(filename):
    if filename not in {"avatar.jpg", "avatar.jpeg", "avatar.png", "avatar.webp"}:
        return jsonify(error="Файл не найден"), 404
    try:
        return send_from_directory(settings_store.PROFILE_DIR, filename)
    except OSError:
        return jsonify(error="Файл не найден"), 404


@app.route("/api/theme", methods=["GET", "POST"])
def api_theme():
    if request.method == "GET":
        try:
            theme = settings_store.load_theme() or {}
        except OSError:
            return jsonify(saved=False, error="Нет доступа к папке темы на устройстве"), 503
        palette = theme.get("palette") if theme.get("palette") in {"blue", "graphite"} else "blue"
        return jsonify(saved=bool(theme), palette=palette, theme=theme)

    data = request.get_json(silent=True) or {}
    palette = data.get("palette", "blue")
    if palette not in {"blue", "graphite"}:
        return jsonify(error="Выберите синюю или чёрную тему"), 400
    try:
        theme = settings_store.save_theme(palette)
    except OSError:
        return jsonify(saved=False, error="Нет доступа к папке темы на устройстве"), 503
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(saved=True, palette=theme["palette"], theme=theme)


@app.route("/api/autonight", methods=["GET", "POST"])
def api_autonight():
    if request.method == "GET":
        try:
            row = settings_store.load_autonight() or {}
        except OSError:
            return jsonify(saved=False, error="Нет доступа к папке ночника на устройстве"), 503
        enabled = bool(row.get("enabled")) if row else False
        return jsonify(saved=bool(row), enabled=enabled, nightlight=row)

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled"))
    try:
        row = settings_store.save_autonight(enabled)
    except OSError:
        return jsonify(saved=False, error="Нет доступа к папке ночника на устройстве"), 503
    return jsonify(saved=True, enabled=row["enabled"], nightlight=row)


@app.route("/api/sounds", methods=["GET", "POST"])
def api_sounds():
    sound_files = sorted(path.name for path in SOUNDS_DIR.glob("*.wav")) if SOUNDS_DIR.exists() else []
    if request.method == "GET":
        try:
            selected = settings_store.load_sound_default()
        except OSError:
            selected = None
        return jsonify(sounds=[{"name": name, "url": f"/sounds/{name}"} for name in sound_files],
                       default=(selected or {}).get("file"))

    filename = (request.get_json(silent=True) or {}).get("file", "")
    if filename not in sound_files:
        return jsonify(error="Выберите мелодию из списка"), 400
    try:
        settings_store.save_sound_default(filename)
    except OSError:
        return jsonify(saved=False, error="Нет доступа к папке звуков на устройстве"), 503
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(saved=True, file=filename,
                   path=f"~/BabyBox/monitor/sounds/{filename}")


@app.route("/api/pin/status")
def api_pin_status():
    try:
        return jsonify(configured=settings_store.pin_is_set())
    except OSError:
        return jsonify(configured=False, error="Нет доступа к папке безопасности на устройстве"), 503


@app.route("/api/pin/set", methods=["POST"])
def api_pin_set():
    data = request.get_json(silent=True) or {}
    pin = data.get("pin", "")
    if not isinstance(pin, str) or not settings_store.PIN_PATTERN.fullmatch(pin):
        return jsonify(error="PIN-код должен состоять из 4–8 цифр"), 400
    try:
        if settings_store.pin_is_set() and not settings_store.verify_pin(str(data.get("current_pin", ""))):
            return jsonify(error="Текущий PIN-код не подошёл"), 403
        settings_store.save_pin(pin)
    except OSError:
        return jsonify(saved=False, error="Нет доступа к папке безопасности на устройстве"), 503
    return jsonify(saved=True)


@app.route("/api/pin/verify", methods=["POST"])
def api_pin_verify():
    data = request.get_json(silent=True) or {}
    pin = data.get("pin", "")
    if not isinstance(pin, str) or not settings_store.PIN_PATTERN.fullmatch(pin):
        return jsonify(unlocked=False, error="Введите PIN-код из 4–8 цифр"), 400
    try:
        configured = settings_store.pin_is_set()
        if not configured:
            return jsonify(unlocked=False, error="PIN-код ещё не настроен"), 409
        if not settings_store.verify_pin(pin):
            return jsonify(unlocked=False, error="PIN-код не подошёл или включена пауза после ошибок"), 403
    except OSError:
        return jsonify(unlocked=False, error="Нет доступа к папке безопасности на устройстве"), 503
    return jsonify(unlocked=True)


def run_nmcli(args, timeout=20):
    """Run nmcli and return the result."""
    return subprocess.run(
        ["/usr/bin/nmcli"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False
    )


def connect_wifi_background(ssid, password):
    """Join home Wi-Fi after the phone has received the HTTP response."""
    time.sleep(1.5)
    try:
        result = subprocess.run(
            ["sudo", "-n", "/usr/local/sbin/babybox-wifi"],
            input=json.dumps({"ssid": ssid, "password": password}),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0:
            app.logger.info("Wi-Fi connected to %r", ssid)
        else:
            app.logger.warning(
                "Wi-Fi connection failed for SSID %r: %s",
                ssid,
                result.stderr.strip() or result.stdout.strip(),
            )
    except Exception:
        app.logger.exception("Background Wi-Fi connect failed for %r", ssid)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/wifi")
def wifi_setup():
    return render_template("wifi_setup.html")


@app.route("/api/camera")
def api_camera():
    """Camera status for the web panel (auto-connect uses /stream)."""
    if not camera.available:
        camera.start()
    return jsonify(camera.status())


@app.route("/api/status")
def api_status():
    """Live sensor readings for the web panel (temperature / humidity)."""
    payload = dht.status()
    payload.update(nightlight.status())
    return jsonify(payload)


@app.route("/api/control", methods=["POST"])
def api_control():
    """Device controls from the web panel (night light, …)."""
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    enabled = bool(data.get("enabled"))

    if action == "light":
        ok = nightlight.set(enabled)
        if not ok:
            return jsonify(
                error=nightlight.status().get("error") or "Не удалось переключить ночник",
                light=nightlight.is_on(),
            ), 500
        return jsonify(ok=True, action="light", enabled=nightlight.is_on(), **nightlight.status())

    if action == "lullaby":
        # Sound is handled in the browser for now.
        return jsonify(ok=True, action="lullaby", enabled=enabled)

    return jsonify(error=f"Unknown action: {action}"), 400


@app.route("/api/reports/today")
def api_reports_today():
    """Daily climate report: series + min/max/current for the Reports tab."""
    return jsonify(day_report())


@app.route("/stream")
def video_stream():
    """MJPEG multipart stream from the CSI / ribbon-cable Pi Camera."""
    return Response(
        camera.mjpeg_generator(),
        mimetype=f"multipart/x-mixed-replace; boundary={BOUNDARY_NAME}",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.route("/api/media")
def api_media_list():
    return jsonify(items=media_store.list_items(), save_dir=str(media_store.root))


@app.route("/api/media/file/<path:filename>")
def api_media_file(filename):
    path = media_store.resolve(filename)
    if path is None or not path.is_file():
        return jsonify(error="Файл не найден"), 404
    return send_from_directory(media_store.root, path.name)


@app.route("/api/media/snapshot", methods=["POST"])
def api_media_snapshot():
    frame = camera.capture_jpeg()
    if not frame:
        return jsonify(error=camera.error or "Не удалось получить кадр с камеры"), 503
    item = media_store.save_bytes(frame, kind="photo", ext=".jpg")
    return jsonify(item=item, message="Снимок сохранён в Записи")


@app.route("/api/media/record/start", methods=["POST"])
def api_media_record_start():
    path = media_store.prepare_path("video", ".mp4")
    ok, message = camera.start_clip(path)
    if not ok:
        return jsonify(error=message, recording=camera.recording), 409 if camera.recording else 503
    return jsonify(recording=True, message=message, name=path.name)


@app.route("/api/media/record/stop", methods=["POST"])
def api_media_record_stop():
    ok, path, message = camera.stop_clip()
    if not ok or path is None:
        return jsonify(error=message, recording=False), 400
    item = media_store.meta_for(path)
    return jsonify(item=item, recording=False, message=message)


@app.route("/api/media/upload", methods=["POST"])
def api_media_upload():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="Файл не передан"), 400
    data = uploaded.read()
    if not data:
        return jsonify(error="Пустой файл"), 400
    kind = (request.form.get("kind") or "clip").strip().lower()
    if kind not in {"photo", "clip", "video"}:
        kind = "clip"
    if kind == "video":
        kind = "clip"
    item = media_store.save_upload(data, uploaded.filename, kind=kind)
    return jsonify(item=item, message="Файл сохранён в Записи")


@app.route("/api/media/<path:filename>", methods=["DELETE"])
def api_media_delete(filename):
    if not media_store.delete(filename):
        return jsonify(error="Файл не найден"), 404
    return jsonify(ok=True, message="Файл удалён")


@app.route("/wifi/networks")
def wifi_networks():
    try:
        result = run_nmcli([
            "-t", "-f", "SSID,SECURITY",
            "device", "wifi", "list", "--rescan", "yes"
        ])
    except subprocess.TimeoutExpired:
        return jsonify(error="Wi-Fi scan timed out. Please try again."), 504

    if result.returncode != 0:
        return jsonify(error="Failed to scan Wi-Fi networks."), 500

    networks = []
    seen = set()

    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        parts = re.split(r"(?<!\\):", line, maxsplit=1)
        if len(parts) != 2:
            continue

        ssid = parts[0].replace(r"\:", ":").replace(r"\\", "\\").strip()
        security = parts[1].replace(r"\:", ":").replace(r"\\", "\\").strip()

        if ssid and ssid not in seen:
            networks.append({
                "ssid": ssid,
                "security": security or "Open network"
            })
            seen.add(ssid)

    return jsonify(networks=networks)


@app.route("/wifi/connect", methods=["POST"])
def wifi_connect():
    data = request.get_json(silent=True) or {}
    ssid = data.get("ssid", "")
    password = data.get("password", "")

    if not isinstance(ssid, str) or not ssid.strip():
        return jsonify(error="Please select a Wi-Fi network."), 400

    ssid = ssid.strip()

    if len(ssid) > 32:
        return jsonify(error="The Wi-Fi network name is too long."), 400

    if not isinstance(password, str) or len(password) > 63:
        return jsonify(error="Invalid Wi-Fi password."), 400

    # Reply first: killing the AP mid-request makes the phone show "Load failed".
    threading.Thread(
        target=connect_wifi_background,
        args=(ssid, password),
        daemon=True,
    ).start()

    return jsonify(
        message=(
            "Принято. BabyBox подключается к домашней сети. "
            "Точка настройки пропадёт — зайдите в ту же Wi-Fi "
            "и откройте сайт по IP малины :5000."
        )
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
