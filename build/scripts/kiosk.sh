#!/bin/bash

CONFIG_FILE="/home/kiosk/kiosk_config.ini"
PROVISIONED_MARKER="/home/kiosk/.provisioned"

ini_read() {
  local file="$1" section="$2" key="$3"
  awk -F'=' -v s="[$section]" -v k="$key" '
    $0==s { in_section=1; next }
    /^\[/ { in_section=0 }
    in_section && $1~"^ *"k" *$" {
      gsub(/^[ \t]+|[ \t]+$/, "", $2)
      print $2
      exit
    }' "$file"
}

if [ -f "$PROVISIONED_MARKER" ] && [ -f "$CONFIG_FILE" ]; then
  URL="$(ini_read "$CONFIG_FILE" kiosk url)"
else
  # Not set up yet - point at the local first-boot setup wizard instead.
  URL="http://127.0.0.1:8080/"
fi

# Give X a moment
sleep 3

# Clean up Chromium state so it doesn’t show “restore” dialogs
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' \
  ~/.config/chromium/Default/Preferences 2>/dev/null || true
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' \
  ~/.config/chromium/Default/Preferences 2>/dev/null || true

EXT_DIR="/home/kiosk/keyboard_extension"

while true; do
  chromium \
    --kiosk "$URL" \
    --noerrdialogs \
    --disable-infobars \
    --enable-smooth-scrolling \
    --enable-accelerated-2d-canvas \
    --force-gpu-rasterization \
    --disable-pinch \
    --ignore-gpu-blocklist \
    --use-gl=egl \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --load-extension="$EXT_DIR" \
    --disable-extensions-except="$EXT_DIR" \
    --start-maximized
  sleep 2
done
