#!/bin/bash
IFACE="wlan0"          # change if your WiFi iface is different
TARGET="8.8.8.8"
PING_COUNT=3
SLEEP_BETWEEN_CHECKS=30
SLEEP_AFTER_RESTART=10

PING_BIN="/usr/bin/ping"
IP_BIN="/usr/sbin/ip"
LOGGER_BIN="/usr/bin/logger"

while true; do
    $PING_BIN -I "$IFACE" -c "$PING_COUNT" "$TARGET" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        $LOGGER_BIN "wifi-watchdog: No network on $IFACE, restarting interface"
        $IP_BIN link set dev "$IFACE" down
        sleep 5
        $IP_BIN link set dev "$IFACE" up
        sleep "$SLEEP_AFTER_RESTART"
    fi
    sleep "$SLEEP_BETWEEN_CHECKS"
done
