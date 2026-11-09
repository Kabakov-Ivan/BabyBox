from flask import Flask, render_template, request, jsonify, Response, send_from_directory
import subprocess
import re
import json
import threading
import time
from pathlib import Path

from camera_stream import BOUNDARY, camera
from dht_sensor import dht

MONITOR_ROOT = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(MONITOR_ROOT / "templates"),
    static_folder=str(MONITOR_ROOT / "static"),
)
BOUNDARY_NAME = BOUNDARY.decode("ascii")
IMG_DIR = MONITOR_ROOT / "img"

# Kick off DHT-11 in a background thread so Flask never blocks on GPIO/Blinka.
threading.Thread(target=dht.start, name="dht11-autostart", daemon=True).start()


@app.route("/img/<path:filename>")
def img_files(filename):
    return send_from_directory(IMG_DIR, filename)


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
    dht.start()
    return jsonify(dht.status())


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
