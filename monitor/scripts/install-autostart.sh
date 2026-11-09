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

if [ ! -f "${APP_DIR}/app/main.py" ]; then
  echo "Expected ${APP_DIR}/app/main.py" >&2
  exit 1
fi

if [ ! -x "${APP_DIR}/.venv/bin/python" ]; then
  echo "Missing venv at ${APP_DIR}/.venv — create it first" >&2
  echo "  python3 -m venv --system-site-packages ${APP_DIR}/.venv" >&2
  echo "  ${APP_DIR}/.venv/bin/pip install -r ${APP_DIR}/requirements.txt" >&2
  exit 1
fi

apt-get update
apt-get install -y hostapd dnsmasq python3-picamera2 libgpiod2 ffmpeg

# Flask + DHT-11 libraries inside the app venv
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# CSI camera / GPIO access for the web service user
usermod -aG video,gpio "$USER_NAME" 2>/dev/null || true

# Photos / clips gallery folder
SAVE_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)/Save_BabyBox"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 755 "$SAVE_DIR"

install -m 755 "${ROOT}/scripts/babybox-boot-wifi" /usr/local/sbin/babybox-boot-wifi
install -m 755 "${ROOT}/scripts/babybox-wifi" /usr/local/sbin/babybox-wifi

install -m 644 "${ROOT}/systemd/babybox-boot-wifi.service" /etc/systemd/system/babybox-boot-wifi.service
sed "s|/home/admin/BabyBox/monitor|${APP_DIR}|g; s|User=admin|User=${USER_NAME}|g; s|Group=admin|Group=${USER_NAME}|g" \
  "${ROOT}/systemd/babybox-web.service" > /etc/systemd/system/babybox-web.service
sed "s|/home/admin/BabyBox/monitor|${APP_DIR}|g; s|User=admin|User=${USER_NAME}|g; s|Group=admin|Group=${USER_NAME}|g" \
  "${ROOT}/systemd/babybox-dht.service" > /etc/systemd/system/babybox-dht.service

# hostapd / dnsmasq only started by boot script or restore_ap — not always-on
systemctl disable --now hostapd 2>/dev/null || true
systemctl disable --now dnsmasq 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

if [ ! -f /etc/hostapd/hostapd.conf ]; then
  cat > /etc/hostapd/hostapd.conf <<'EOF'
interface=wlan0
driver=nl80211
ssid=BABY_BOX_SETUP
hw_mode=g
channel=7
ieee80211n=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=Sas23766732
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
country_code=RU
EOF
else
  sed -i 's/^ssid=.*/ssid=BABY_BOX_SETUP/' /etc/hostapd/hostapd.conf
  sed -i 's/^wpa_passphrase=.*/wpa_passphrase=Sas23766732/' /etc/hostapd/hostapd.conf
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
systemctl enable babybox-dht.service

echo
echo "Installed. Reboot to test:"
echo "  sudo reboot"
echo
echo "Flow:"
echo "  1) Boot → always AP BABY_BOX_SETUP / Sas23766732 + website"
echo "  2) Phone → http://192.168.4.1:5000/wifi → enter home Wi-Fi"
echo "  3) Pi joins home Wi-Fi → site on that network IP:5000"
echo "  4) Camera page auto-loads MJPEG from http://<pi-ip>:5000/stream"
echo "  5) Photos/videos save to ${SAVE_DIR} and show in Записи"
echo
echo "Camera notes:"
echo "  - venv must see system picamera2: python3 -m venv --system-site-packages ${APP_DIR}/.venv"
echo "  - user ${USER_NAME} is in groups video,gpio (re-login/reboot after first install)"
echo "  - quick check: rpicam-hello -t 2000"
echo "  - video clips need ffmpeg (installed by this script)"
echo
# Kernel DHT driver (more reliable than userspace bitbang on Pi)
if [ -f /boot/firmware/config.txt ]; then
  BOOTCFG=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  BOOTCFG=/boot/config.txt
else
  BOOTCFG=""
fi
if [ -n "$BOOTCFG" ]; then
  if grep -q 'dtoverlay=dht11' "$BOOTCFG"; then
    sed -i 's/^dtoverlay=dht11.*/dtoverlay=dht11,gpiopin=4/' "$BOOTCFG"
  else
    echo 'dtoverlay=dht11,gpiopin=4' >> "$BOOTCFG"
  fi
  echo "DHT overlay set to dtoverlay=dht11,gpiopin=4 in $BOOTCFG (reboot if pin changed)"

  # Power button via kernel overlay (GPIO3 ↔ GND). Avoid userspace pinctrl spam.
  systemctl disable --now babybox-power.service 2>/dev/null || true
  LINE='dtoverlay=gpio-shutdown,gpio_pin=3,active_low=1,gpio_pull=up'
  if grep -q '^dtoverlay=gpio-shutdown' "$BOOTCFG"; then
    sed -i "s/^dtoverlay=gpio-shutdown.*/${LINE}/" "$BOOTCFG"
  else
    printf '\n%s\n' "$LINE" >> "$BOOTCFG"
  fi
  echo "Power-button overlay set (GPIO3) in $BOOTCFG"
fi

echo "DHT-11 notes:"
echo "  - VCC→3.3V (pin 1), GND→pin 6, DATA→pin 7 (BCM GPIO 4)"
echo "  - kernel overlay: dtoverlay=dht11,gpiopin=4"
echo "  - separate service: sudo systemctl status babybox-dht"
echo "  - check file: cat /tmp/babybox-dht.json"
echo "  - check API: curl -s http://127.0.0.1:5000/api/status"
echo
echo "Power button notes:"
echo "  - Button: GPIO3 (phys pin 5) ↔ GND (phys pin 20)"
echo "  - dtoverlay=gpio-shutdown (reboot once after install)"
echo "  - Press while running → shutdown; while halted → power on"
