#!/bin/bash
# Power button: GPIO3 (phys pin 5) ↔ GND (phys pin 20)
# Uses kernel overlay — does NOT burn CPU with pinctrl polling.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

# Stop the heavy userspace watcher if it was installed earlier.
systemctl disable --now babybox-power.service 2>/dev/null || true

if [ -f /boot/firmware/config.txt ]; then
  BOOTCFG=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  BOOTCFG=/boot/config.txt
else
  echo "config.txt not found" >&2
  exit 1
fi

LINE='dtoverlay=gpio-shutdown,gpio_pin=3,active_low=1,gpio_pull=up'

if grep -q '^dtoverlay=gpio-shutdown' "$BOOTCFG"; then
  sed -i "s/^dtoverlay=gpio-shutdown.*/${LINE}/" "$BOOTCFG"
else
  printf '\n%s\n' "$LINE" >> "$BOOTCFG"
fi

if grep -qE '^dtparam=i2c_arm=on|^dtparam=i2c=on' "$BOOTCFG"; then
  echo "WARNING: I2C is enabled — GPIO3 is SCL. Prefer disabling I2C:"
  echo "  sudo raspi-config → Interface Options → I2C → No"
fi

echo "Updated $BOOTCFG"
echo "  $LINE"
echo
echo "Userspace babybox-power.service disabled (it was lagging the Pi)."
echo "Wiring: GPIO3 (pin 5) ↔ GND (pin 20)"
echo "Reboot required:"
echo "  sudo reboot"
echo
echo "After reboot: short press → shutdown; press while halted → power on"
