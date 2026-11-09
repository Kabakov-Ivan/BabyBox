#!/bin/bash
# Enable Raspberry Pi power button on GPIO3 (phys pin 5) ↔ GND (phys pin 20).
# Kernel handles shutdown; the same pin wakes the board from halt.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

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

echo "Updated $BOOTCFG"
echo "  $LINE"
echo
echo "Wiring:"
echo "  button between GPIO3 (physical pin 5) and GND (physical pin 20)"
echo
echo "Reboot required:"
echo "  sudo reboot"
echo
echo "After reboot:"
echo "  press button → shutdown"
echo "  press again while halted → power on"
