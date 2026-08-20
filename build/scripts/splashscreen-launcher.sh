#!/bin/bash
# Picks the pre-rotated splash image matching the configured display
# rotation (generated at build time - see build-image.sh) and shows it.
# Falls back to "normal" if unconfigured (e.g. very first boot).
CONFIG_FILE="/home/kiosk/kiosk_config.ini"
ROTATION="normal"

if [ -f "$CONFIG_FILE" ]; then
  R="$(awk -F'=' '
    /^\[display\]/ { f=1; next }
    /^\[/ { f=0 }
    f && $1 ~ "^ *rotation *$" {
      gsub(/^[ \t]+|[ \t]+$/, "", $2)
      print $2
      exit
    }' "$CONFIG_FILE")"
  [ -n "$R" ] && ROTATION="$R"
fi

case "$ROTATION" in
  right)    IMG=/home/kiosk/HA_Splash_right.png ;;
  left)     IMG=/home/kiosk/HA_Splash_left.png ;;
  inverted) IMG=/home/kiosk/HA_Splash_inverted.png ;;
  *)        IMG=/home/kiosk/HA_Splash_normal.png ;;
esac

[ -f "$IMG" ] || IMG=/home/kiosk/HA_Splash.png

exec fbi -d /dev/fb0 --noverbose -a "$IMG"
