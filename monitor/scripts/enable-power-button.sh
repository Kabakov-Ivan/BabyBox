#!/bin/bash
# Power button: GPIO3 (phys pin 5) ↔ GND (phys pin 20)
# Userspace service for shutdown; GPIO3 still wakes Pi from halt.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-admin}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
APP_DIR="${HOME_DIR}/BabyBox/monitor"

apt-get install -y python3-gpiozero

# Kernel overlay and our service fight for the same pin — use the service only.
if [ -f /boot/firmware/config.txt ]; then
  BOOTCFG=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  BOOTCFG=/boot/config.txt
else
  BOOTCFG=""
fi
if [ -n "$BOOTCFG" ] && grep -q '^dtoverlay=gpio-shutdown' "$BOOTCFG"; then
  sed -i '/^dtoverlay=gpio-shutdown/d' "$BOOTCFG"
  echo "Removed dtoverlay=gpio-shutdown from $BOOTCFG (userspace service instead)"
fi

# Warn if I2C owns GPIO3 (SCL)
if [ -n "$BOOTCFG" ] && grep -qE '^dtparam=i2c_arm=on|^dtparam=i2c=on' "$BOOTCFG"; then
  echo "WARNING: I2C is enabled — it uses GPIO3. Power button may not work until I2C is off."
fi

sed "s|/home/admin/BabyBox/monitor|${APP_DIR}|g" \
  "${ROOT}/systemd/babybox-power.service" > /etc/systemd/system/babybox-power.service

systemctl daemon-reload
systemctl enable --now babybox-power.service

echo
echo "Installed babybox-power.service"
echo "Wiring: button between GPIO3 (pin 5) and GND (pin 20)"
echo "Hold ~0.8s while running → shutdown"
echo "Press while halted → power on"
echo
echo "Check:"
echo "  sudo systemctl status babybox-power --no-pager"
echo "  sudo journalctl -u babybox-power -f"
