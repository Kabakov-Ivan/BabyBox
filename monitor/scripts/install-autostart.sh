#!/bin/bash
# Install BabyBox boot AP + web autostart on the Raspberry Pi.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-admin}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
APP_DIR="${HOME_DIR}/BabyBox/monitor"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

if [ ! -d "$APP_DIR" ]; then
  echo "Expected app at $APP_DIR" >&2
  exit 1
fi

if [ ! -x "${APP_DIR}/.venv/bin/python" ]; then
  echo "Missing venv at ${APP_DIR}/.venv — create it first" >&2
  exit 1
fi

apt-get update
apt-get install -y hostapd dnsmasq

install -m 755 "${ROOT}/scripts/babybox-boot-wifi" /usr/local/sbin/babybox-boot-wifi
install -m 755 "${ROOT}/scripts/babybox-wifi" /usr/local/sbin/babybox-wifi

install -m 644 "${ROOT}/systemd/babybox-boot-wifi.service" /etc/systemd/system/babybox-boot-wifi.service
sed "s|/home/admin/BabyBox/monitor|${APP_DIR}|g; s|User=admin|User=${USER_NAME}|g; s|Group=admin|Group=${USER_NAME}|g" \
  "${ROOT}/systemd/babybox-web.service" > /etc/systemd/system/babybox-web.service

# hostapd / dnsmasq only started by boot script or restore_ap — not always-on
systemctl disable --now hostapd 2>/dev/null || true
systemctl disable --now dnsmasq 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

if [ ! -f /etc/hostapd/hostapd.conf ]; then
  cat > /etc/hostapd/hostapd.conf <<'EOF'
interface=wlan0
driver=nl80211
ssid=BabyBox-Setup
hw_mode=g
channel=7
ieee80211n=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=babybox123
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
country_code=RU
EOF
fi
echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd

if [ ! -f /etc/dnsmasq.d/babybox-ap.conf ]; then
  cat > /etc/dnsmasq.d/babybox-ap.conf <<'EOF'
interface=wlan0
bind-interfaces
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
domain=local
address=/#/192.168.4.1
EOF
fi

# Prefer drop-in over replacing whole dnsmasq.conf if missing essentials
if [ ! -f /etc/dnsmasq.conf ]; then
  echo 'conf-dir=/etc/dnsmasq.d/,*.conf' > /etc/dnsmasq.conf
fi

cat > /etc/sudoers.d/babybox-wifi <<EOF
${USER_NAME} ALL=(root) NOPASSWD: /usr/local/sbin/babybox-wifi
EOF
chmod 440 /etc/sudoers.d/babybox-wifi

systemctl daemon-reload
systemctl enable babybox-boot-wifi.service
systemctl enable babybox-web.service

echo
echo "Installed. Reboot to test:"
echo "  sudo reboot"
echo
echo "Flow:"
echo "  1) No saved Wi-Fi → AP BabyBox-Setup / babybox123"
echo "  2) Phone → http://192.168.4.1:5000/wifi"
echo "  3) After connect → site on home Wi-Fi IP:5000"
