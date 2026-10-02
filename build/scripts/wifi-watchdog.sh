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
    # On Ethernet the Wi-Fi is not in use: nothing to watch. Until 2026-10-01
    # this took wlan0 down and up about every minute on the wired kiosks.
    if [ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" = "1" ] && /usr/sbin/ip -4 route show default dev eth0 2>/dev/null | grep -q .; then
        sleep "$SLEEP_BETWEEN_CHECKS"
        continue
    fi
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
