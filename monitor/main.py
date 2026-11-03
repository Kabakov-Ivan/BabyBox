from flask import Flask, render_template, request, jsonify
import subprocess
import re

app = Flask(__name__)


def run_nmcli(args, timeout=20):
    """Запустить nmcli и вернуть результат."""
    return subprocess.run(
        ["nmcli"] + args,
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
    result = run_nmcli([
        "-t", "-f", "SSID,SECURITY",
        "device", "wifi", "list", "--rescan", "yes"
    ])

    if result.returncode != 0:
        return jsonify(error="Не удалось просканировать Wi-Fi сети."), 500

    networks = []
    seen = set()

    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        # Формат nmcli -t экранирует специальные символы через обратный слеш.
        parts = re.split(r"(?<!\\):", line, maxsplit=1)
        if len(parts) != 2:
            continue

        ssid = parts[0].replace(r"\:", ":").replace(r"\\", "\\").strip()
        security = parts[1].replace(r"\:", ":").replace(r"\\", "\\").strip()

        if ssid and ssid not in seen:
            networks.append({
                "ssid": ssid,
                "security": security or "Открытая сеть"
            })
            seen.add(ssid)

    return jsonify(networks=networks)


@app.route("/wifi/connect", methods=["POST"])
def wifi_connect():
    data = request.get_json(silent=True) or {}
    ssid = data.get("ssid", "")
    password = data.get("password", "")

    if not isinstance(ssid, str) or not ssid.strip():
        return jsonify(error="Выберите Wi-Fi сеть."), 400

    if not isinstance(password, str):
        return jsonify(error="Некорректный пароль."), 400

    # Пока только проверяем данные. Сетевые настройки не меняем,
    # чтобы не потерять текущее соединение и доступ к устройству.
    return jsonify(
        message="Сеть выбрана. Подключение пока не включено: сначала нужно настроить безопасные права для NetworkManager."
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)