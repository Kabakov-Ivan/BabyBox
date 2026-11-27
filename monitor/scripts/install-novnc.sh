#!/bin/bash
# Install noVNC web client on the Raspberry Pi (port 6080 only).
# Does NOT touch babybox-web / Flask panel on port 5000.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-admin}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Запусти так: sudo bash $0" >&2
  exit 1
fi

echo "==> Ставим noVNC + websockify (отдельный сервис, порт 6080)"
apt-get update
apt-get install -y novnc websockify

NOVNC_WEB=""
for candidate in /usr/share/novnc /usr/share/novnc/utils/.. /usr/share/novnc/; do
  if [ -f "${candidate}/vnc.html" ] || [ -f "${candidate}/vnc_lite.html" ]; then
    NOVNC_WEB="$(cd "$candidate" && pwd)"
    break
  fi
done

if [ -z "$NOVNC_WEB" ]; then
  # Некоторые пакеты кладут файлы в /usr/share/novnc без vnc.html на верхнем уровне.
  if [ -d /usr/share/novnc ]; then
    NOVNC_WEB="/usr/share/novnc"
  else
    echo "Пакет novnc установлен, но папка /usr/share/novnc не найдена." >&2
    exit 1
  fi
fi

if [ ! -f "${NOVNC_WEB}/vnc.html" ] && [ -f "${NOVNC_WEB}/vnc_lite.html" ]; then
  ln -sfn vnc_lite.html "${NOVNC_WEB}/vnc.html"
fi

echo "==> noVNC web root: ${NOVNC_WEB}"

SERVICE_SRC="${ROOT}/systemd/babybox-novnc.service"
SERVICE_DST="/etc/systemd/system/babybox-novnc.service"
sed "s|/usr/share/novnc|${NOVNC_WEB}|g" "$SERVICE_SRC" > "$SERVICE_DST"
# На всякий случай явно user из установки
sed -i "s/^User=.*/User=${USER_NAME}/" "$SERVICE_DST"
sed -i "s/^Group=.*/Group=${USER_NAME}/" "$SERVICE_DST"

systemctl daemon-reload
systemctl enable babybox-novnc.service
systemctl restart babybox-novnc.service

# wayvnc на Raspberry Pi по умолчанию требует TLS/PAM (типы RA2/VeNCrypt),
# а браузерный noVNC это не понимает → «ошибка подключения к серверу».
# Для веб-клиента нужен простой режим без TLS-auth (только домашняя сеть).
if [ -f /etc/wayvnc/config ]; then
  echo "==> Настраиваем wayvnc под noVNC (enable_auth=false)"
  cp -a /etc/wayvnc/config "/etc/wayvnc/config.bak.babybox.$(date +%Y%m%d%H%M%S)"
  cat > /etc/wayvnc/config <<'EOF'
use_relative_paths=true
address=::
enable_auth=false
EOF
  systemctl restart wayvnc.service || true
fi

echo
echo "Готово. Панель на :5000 не трогали."
echo "  noVNC:  http://<IP>:6080/vnc.html?autoconnect=1&resize=scale"
echo "  Прокси: websockify :6080 → 127.0.0.1:5900"
echo
echo "Проверка:"
echo "  systemctl status babybox-novnc.service --no-pager"
echo "  systemctl status wayvnc.service --no-pager"
echo "  ss -lntp | grep -E '5000|6080|5900' || true"
echo
echo "Открой VNC из панели или напрямую:"
echo "  http://192.168.0.156:6080/vnc.html?autoconnect=1&resize=scale"
echo
echo "Заметка: wayvnc без пароля (LAN). Панель :5000 не затронута."
