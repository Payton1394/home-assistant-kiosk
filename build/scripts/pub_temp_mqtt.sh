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

MQTT_HOST="$(ini_read "$CONFIG_FILE" mqtt host)"
MQTT_PORT="$(ini_read "$CONFIG_FILE" mqtt port)"
MQTT_USER="$(ini_read "$CONFIG_FILE" mqtt username)"
MQTT_PASS="$(ini_read "$CONFIG_FILE" mqtt password)"
MQTT_BASE="$(ini_read "$CONFIG_FILE" mqtt base_topic)"

REGEX="temp=([0-9]+\.[0-9])"

while true; do
  RAW=$(/usr/bin/vcgencmd measure_temp)
  if [[ $RAW =~ $REGEX ]]; then
    VAL="${BASH_REMATCH[1]}"
    mosquitto_pub \
      -h "$MQTT_HOST" \
      -p "$MQTT_PORT" \
      -u "$MQTT_USER" \
      -P "$MQTT_PASS" \
      -t "${MQTT_BASE}/cpu_temp" \
      -m "$VAL"
  fi
  sleep 30
done
