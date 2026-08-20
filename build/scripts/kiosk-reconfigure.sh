#!/bin/bash
# Puts the kiosk back into first-boot setup wizard mode so settings (Wi-Fi,
# MQTT, dashboard URL, sensors, etc.) can be changed without reflashing the
# SD card. Run this via SSH or the local terminal:
#
#   kiosk-reconfigure            # reboots into the wizard immediately
#   kiosk-reconfigure --no-reboot   # just arms it; reboot yourself when ready
#
# The existing kiosk_config.ini is left in place (not wiped) - the wizard
# pre-fills the form from it, so this is "edit settings", not "start over".
set -euo pipefail

MARKER="/home/kiosk/.provisioned"

if [ "$(id -u)" -ne 0 ]; then
  exec sudo "$0" "$@"
fi

rm -f "$MARKER"
echo "Setup wizard is armed - it will run on next boot."

if [ "${1:-}" = "--no-reboot" ]; then
  echo "Not rebooting (--no-reboot given). Run 'sudo reboot' when ready."
else
  echo "Rebooting in 3 seconds... (Ctrl+C to cancel)"
  sleep 3
  systemctl reboot
fi
