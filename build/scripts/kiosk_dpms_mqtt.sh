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
    -r -q 1 -t "$STATE_FULL_TOPIC" -m "$state"
}

# State watcher using xset q. The state is published retained, so Home
# Assistant has it as soon as it subscribes -- after its own restart too, not
# only after the next change -- and it is sent again every 5 minutes. A
# publish that fails (at boot the network may not be up yet) is tried again
# on the next poll rather than taken as sent.
watch_dpms() {
  local last="" sent=0 out cur now
  # Until X is up xset q fails, which would read as ON.
  while ! DISPLAY=:0 xset q >/dev/null 2>&1; do
    sleep 1
  done
  while true; do
    out=$(DISPLAY=:0 xset q 2>/dev/null)
    if [ -z "$out" ]; then
      sleep 2
      continue
    fi
    if echo "$out" | grep -q "Monitor is Off"; then
      cur="OFF"
    else
      cur="ON"
    fi

    now=$(date +%s)
    if [ "$cur" != "$last" ] || [ $((now - sent)) -ge 300 ]; then
      if publish_state "$cur"; then
        last="$cur"
        sent=$now
      fi
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
