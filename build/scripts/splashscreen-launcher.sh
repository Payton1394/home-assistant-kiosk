#!/bin/bash
# Shows the boot splash - an animated (spinner) sequence generated at build
# time if present, matching the configured display rotation, falling back
# to a static per-rotation image and finally the generic un-rotated source
# if the animated frames weren't generated. fbi loops a multi-file slideshow
# indefinitely by default, so this blocks (as desired) until kiosk.service's
# TTYVHangup kills it when Chromium takes over the same VT.
CONFIG_FILE="/home/kiosk/kiosk_config.ini"
FRAMES_DIR="/home/kiosk/splash_frames"
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
  right|left|inverted) ;;
  *) ROTATION="normal" ;;
esac

FRAMES=("$FRAMES_DIR/${ROTATION}_"*.png)
if [ -e "${FRAMES[0]}" ]; then
  exec fbi -d /dev/fb0 --noverbose -a -t 0.1 "${FRAMES[@]}"
fi

case "$ROTATION" in
  right)    IMG=/home/kiosk/HA_Splash_right.png ;;
  left)     IMG=/home/kiosk/HA_Splash_left.png ;;
  inverted) IMG=/home/kiosk/HA_Splash_inverted.png ;;
  *)        IMG=/home/kiosk/HA_Splash_normal.png ;;
esac
[ -f "$IMG" ] || IMG=/home/kiosk/HA_Splash.png

exec fbi -d /dev/fb0 --noverbose -a "$IMG"
