#!/bin/bash
# Power button: GPIO3 (phys pin 5) ↔ GND (phys pin 20)
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-admin}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
APP_DIR="${HOME_DIR}/BabyBox/monitor"

apt-get install -y raspi-utils

# Kernel overlay fights userspace access to GPIO3 — remove it.
if [ -f /boot/firmware/config.txt ]; then
  BOOTCFG=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  BOOTCFG=/boot/config.txt
else
  BOOTCFG=""
fi
if [ -n "$BOOTCFG" ] && grep -q '^dtoverlay=gpio-shutdown' "$BOOTCFG"; then
  sed -i '/^dtoverlay=gpio-shutdown/d' "$BOOTCFG"
  echo "Removed dtoverlay=gpio-shutdown from $BOOTCFG"
fi

if [ -n "$BOOTCFG" ] && grep -qE '^dtparam=i2c_arm=on|^dtparam=i2c=on' "$BOOTCFG"; then
  echo "WARNING: I2C enabled — GPIO3 is SCL. Disable I2C if button fails:"
  echo "  sudo raspi-config → Interface Options → I2C → No"
fi

sed "s|/home/admin/BabyBox/monitor|${APP_DIR}|g" \
  "${ROOT}/systemd/babybox-power.service" > /etc/systemd/system/babybox-power.service

systemctl daemon-reload
systemctl enable --now babybox-power.service
systemctl restart babybox-power.service

echo
echo "Installed babybox-power.service"
echo "Wiring: left side of button → pin 5 (GPIO3), right side → pin 20 (GND)"
echo "Hold ~0.8s → shutdown | press while halted → power on"
echo
echo "  sudo systemctl status babybox-power --no-pager"
echo "  sudo journalctl -u babybox-power -f"
echo "  pinctrl get 3   # hi=open, lo=pressed"
