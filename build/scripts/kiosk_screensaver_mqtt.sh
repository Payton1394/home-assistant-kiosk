#!/bin/bash

CONFIG_FILE="/home/kiosk/kiosk_config.ini"

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
# Wait for XScreenSaver to be reachable
while ! DISPLAY=:0 xscreensaver-command -time >/dev/null 2>&1; do
  sleep 1
done

MQTT_HOST="$(ini_read "$CONFIG_FILE" mqtt host)"
MQTT_PORT="$(ini_read "$CONFIG_FILE" mqtt port)"
MQTT_USER="$(ini_read "$CONFIG_FILE" mqtt username)"
MQTT_PASS="$(ini_read "$CONFIG_FILE" mqtt password)"
MQTT_BASE="$(ini_read "$CONFIG_FILE" mqtt base_topic)"

SS_CMD_TOPIC="$(ini_read "$CONFIG_FILE" screensaver command_topic)"
SS_STATE_TOPIC="$(ini_read "$CONFIG_FILE" screensaver state_topic)"

CMD_FULL_TOPIC="${MQTT_BASE}/${SS_CMD_TOPIC}"
STATE_FULL_TOPIC="${MQTT_BASE}/${SS_STATE_TOPIC}"

publish_state() {
  local state="$1"
  mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" \
    -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "$STATE_FULL_TOPIC" -m "$state"
}

# --- State watcher: polls xscreensaver and publishes on change ---
# Wrapped in a retry loop: `xscreensaver-command --watch` can fail/exit
# immediately if it races xscreensaver's own startup at boot (systemd starts
# this unit as soon as the network is up, which can be before the X session's
# xscreensaver daemon has actually registered). Without the retry, that one
# failed attempt was silent (stderr -> /dev/null) and permanent - the command
# listener below kept working, but the switch never got another state update
# until the service was manually restarted.
watch_state() {
  while true; do
    DISPLAY=:0 xscreensaver-command --watch 2>/dev/null | while read -r line; do
      case "$line" in
        BLANK*|LOCK*)
          publish_state "ON"
          ;;
        UNBLANK*)
          publish_state "OFF"
          ;;
      esac
    done
    sleep 2
  done
}

# Start watcher in background
watch_state &

# --- Command listener: ON/OFF/TOGGLE via MQTT ---
mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
  -u "$MQTT_USER" -P "$MQTT_PASS" \
  -t "$CMD_FULL_TOPIC" -q 1 | while read -r payload; do
    case "$payload" in
      ON|on|On)
        DISPLAY=:0 xscreensaver-command -activate >/dev/null 2>&1
        ;;
      OFF|off|Off)
        DISPLAY=:0 xscreensaver-command -deactivate >/dev/null 2>&1
        ;;
      TOGGLE|toggle|Toggle)
        state=$(DISPLAY=:0 xscreensaver-command -time 2>/dev/null)
        if echo "$state" | grep -qi "screen saver active"; then
          DISPLAY=:0 xscreensaver-command -deactivate >/dev/null 2>&1
        else
          DISPLAY=:0 xscreensaver-command -activate >/dev/null 2>&1
        fi
        ;;
    esac
  done
