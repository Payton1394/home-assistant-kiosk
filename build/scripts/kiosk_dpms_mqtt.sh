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

DPMS_CMD_TOPIC="$(ini_read "$CONFIG_FILE" dpms command_topic)"
DPMS_STATE_TOPIC="$(ini_read "$CONFIG_FILE" dpms state_topic)"

CMD_FULL_TOPIC="${MQTT_BASE}/${DPMS_CMD_TOPIC}"
STATE_FULL_TOPIC="${MQTT_BASE}/${DPMS_STATE_TOPIC}"

publish_state() {
  local state="$1"
  mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" \
    -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "$STATE_FULL_TOPIC" -m "$state"
}

# State watcher using xset q. Already a self-healing poll loop (unlike the
# screensaver watcher's original one-shot `--watch` subprocess), so it isn't
# vulnerable to the same boot-race-then-silent-death bug - each iteration is
# independent, a single failed `xset q` just gets picked up on the next pass.
watch_dpms() {
  local last=""
  while true; do
    out=$(DISPLAY=:0 xset q 2>/dev/null)
    if echo "$out" | grep -q "Monitor is Off"; then
      cur="OFF"
    else
      cur="ON"
    fi

    if [ "$cur" != "$last" ]; then
      publish_state "$cur"
      last="$cur"
    fi

    sleep 2
  done
}

watch_dpms &

mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
  -u "$MQTT_USER" -P "$MQTT_PASS" \
  -t "$CMD_FULL_TOPIC" -q 1 | while read -r payload; do
    case "$payload" in
      OFF|off|Off)
        DISPLAY=:0 xset dpms force off >/dev/null 2>&1
        ;;
      ON|on|On)
        DISPLAY=:0 xset dpms force on >/dev/null 2>&1
        ;;
      TOGGLE|toggle|Toggle)
        out=$(DISPLAY=:0 xset q 2>/dev/null)
        if echo "$out" | grep -q "Monitor is Off"; then
          DISPLAY=:0 xset dpms force on >/dev/null 2>&1
        else
          DISPLAY=:0 xset dpms force off >/dev/null 2>&1
        fi
        ;;
    esac
  done
