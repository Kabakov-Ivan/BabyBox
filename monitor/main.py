from flask import Flask, render_template, request, jsonify
import subprocess
import re
import json

app = Flask(__name__)


def run_nmcli(args, timeout=20):
    """Run nmcli and return the result."""
    return subprocess.run(
        ["/usr/bin/nmcli"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/wifi")
def wifi_setup():
    return render_template("wifi_setup.html")


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

    try:
        result = subprocess.run(
            ["sudo", "-n", "/usr/local/sbin/babybox-wifi"],
            input=json.dumps({
                "ssid": ssid,
                "password": password
            }),
            capture_output=True,
            text=True,
            timeout=45,
            check=False
        )

    except subprocess.TimeoutExpired:
        return jsonify(
            error="Connection timed out. Please try again."
        ), 504

    except OSError:
        app.logger.exception("Could not start Wi-Fi connection helper")
        return jsonify(
            error="Could not start the Wi-Fi connection service."
        ), 500

    if result.returncode == 0:
        return jsonify(
            message="Wi-Fi connection successful. You may need to reconnect to BabyBox using the new network."
        )

    app.logger.warning(
        "Wi-Fi connection failed for SSID %r: %s",
        ssid,
        result.stderr.strip() or result.stdout.strip()
    )

    return jsonify(
        error="Could not connect to this Wi-Fi network. Check the password and try again."
    ), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)