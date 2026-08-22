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

BR_CMD_TOPIC="$(ini_read "$CONFIG_FILE" brightness command_topic)"
BR_STATE_TOPIC="$(ini_read "$CONFIG_FILE" brightness state_topic)"
BR_MIN="$(ini_read "$CONFIG_FILE" brightness min)"
BR_MAX="$(ini_read "$CONFIG_FILE" brightness max)"
BR_DISP="$(ini_read "$CONFIG_FILE" brightness display)"

CMD_FULL_TOPIC="${MQTT_BASE}/${BR_CMD_TOPIC}"
STATE_FULL_TOPIC="${MQTT_BASE}/${BR_STATE_TOPIC}"

publish_state() {
  local val="$1"
  mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" \
    -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "$STATE_FULL_TOPIC" -m "$val"
}

get_brightness() {
  ddcutil getvcp 10 --display "$BR_DISP" 2>/dev/null | \
    awk -F'[=,]' '/current value/ {
      gsub(/^[ \t]+|[ \t]+$/, "", $2)
      print $2
    }'
}

set_brightness() {
  local val="$1"
  if [ "$val" -lt "$BR_MIN" ]; then val="$BR_MIN"; fi
  if [ "$val" -gt "$BR_MAX" ]; then val="$BR_MAX"; fi
  ddcutil setvcp 10 "$val" --display "$BR_DISP" >/dev/null 2>&1
}

cur=$(get_brightness)
[ -n "$cur" ] && publish_state "$cur"

watch_brightness() {
  local last="$cur"
  while true; do
    now=$(get_brightness)
    if [ -n "$now" ] && [ "$now" != "$last" ]; then
      publish_state "$now"
      last="$now"
    fi
    sleep 10
  done
}

watch_brightness &

mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
  -u "$MQTT_USER" -P "$MQTT_PASS" \
  -t "$CMD_FULL_TOPIC" -q 1 | while read -r payload; do
    case "$payload" in
      +*|-*)
        ddcutil setvcp 10 "$payload" --display "$BR_DISP" >/dev/null 2>&1
        ;;
      *)
        if [[ "$payload" =~ ^[0-9]+$ ]]; then
          set_brightness "$payload"
        fi
        ;;
    esac
    new=$(get_brightness)
    [ -n "$new" ] && publish_state "$new"
  done
