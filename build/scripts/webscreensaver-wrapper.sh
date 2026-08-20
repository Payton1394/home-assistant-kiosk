#!/bin/bash

CONFIG_FILE="/home/kiosk/kiosk_config.ini"

get_ini_value() {
  local section="$1"
  local key="$2"
  awk -F '=' '
    $0 ~ "\\["section"\\]" { in_section=1; next }
    /^\[/ { in_section=0 }
    in_section && $1 ~ "^"key"[[:space:]]*$" {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)
      print $2
      exit
    }
  ' section="$section" key="$key" "$CONFIG_FILE"
}

URL="$(get_ini_value "screensaver" "url")"

if [ -z "$URL" ]; then
  # No screensaver URL configured - nothing to show, but do NOT exit here:
  # xscreensaver expects a "hack" to keep running until it kills it, and
  # treats an early exit as a crash (logged as "crashed with status 0"),
  # which can leave its blanking window's input grab stuck rather than
  # cleanly releasing it back to the desktop. Block instead - xscreensaver
  # will just show blank/whatever until it terminates us on deactivation.
  exec sleep infinity
fi

exec webscreensaver -url "$URL"
