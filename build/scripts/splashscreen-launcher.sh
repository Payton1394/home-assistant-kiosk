#!/bin/bash
# Plays the boot splash - a pre-rotated, pre-composed animated GIF (see
# build/scripts/generate_splash.py) picked by configured display rotation,
# scaled to fit the screen's actual negotiated resolution without stretching
# (letterboxed/pillarboxed with the same brand-blue background so the
# padding is invisible). Runs via ffmpeg's fbdev output rather than fbi:
# fbi's own multi-file slideshow/timer handling proved unreliable for this
# (see project history), while ffmpeg's -re real-time-paced read combined
# with the GIF's own per-frame durations is straightforward and reliable.
#
# Blocks indefinitely (loops forever) until kiosk.service's TTYVHangup kills
# it when Chromium takes over the same VT - same lifecycle as the old
# fbi-based launcher.
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
  right|left|inverted) ;;
  *) ROTATION="normal" ;;
esac

GIF="/home/kiosk/HA_Splash_${ROTATION}.gif"
[ -f "$GIF" ] || GIF="/home/kiosk/HA_Splash.png"

RES="$(cat /sys/class/graphics/fb0/virtual_size 2>/dev/null)"
W="${RES%,*}"
H="${RES#*,}"
if [ -z "$W" ] || [ -z "$H" ]; then
  W=1920
  H=1080
fi

exec ffmpeg -loglevel error -re -stream_loop -1 -i "$GIF" \
  -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x18BCF2" \
  -pix_fmt rgb565le -f fbdev /dev/fb0
