#!/bin/bash
# kiosk-net-watchdog.sh
# Pings the gateway; after FAIL_THRESHOLD consecutive failed checks,
# restarts NetworkManager to recover from a stuck/hung wifi association.
# Runs every 2 min via kiosk-net-watchdog.timer.

LOG=/home/kiosk/kiosk-net.log
TARGET=192.168.1.1
IFACE=wlan0
STATE_DIR=/run/kiosk-net-watchdog
FAIL_COUNT_FILE="$STATE_DIR/fail_count"
LAST_RESTART_FILE="$STATE_DIR/last_restart"
FAIL_THRESHOLD=2       # consecutive failed checks before acting (~4 min of outage)
RESTART_COOLDOWN=180   # seconds; minimum gap between restarts

mkdir -p "$STATE_DIR"

timestamp() { date "+%Y-%m-%d %H:%M:%S"; }

ping -I "$IFACE" -c2 -W3 "$TARGET" >/dev/null 2>&1
RC=$?

if [ "$RC" -eq 0 ]; then
  echo 0 > "$FAIL_COUNT_FILE"
  exit 0
fi

COUNT=0
[ -f "$FAIL_COUNT_FILE" ] && COUNT=$(cat "$FAIL_COUNT_FILE")
COUNT=$((COUNT + 1))
echo "$COUNT" > "$FAIL_COUNT_FILE"

if [ "$COUNT" -lt "$FAIL_THRESHOLD" ]; then
  exit 0
fi

NOW=$(date +%s)
LAST=0
[ -f "$LAST_RESTART_FILE" ] && LAST=$(cat "$LAST_RESTART_FILE")
ELAPSED=$((NOW - LAST))

if [ "$ELAPSED" -lt "$RESTART_COOLDOWN" ]; then
  echo "==== $(timestamp) watchdog: threshold reached (count=$COUNT) but in cooldown (${ELAPSED}s since last restart) - skipping ====" >> "$LOG"
  exit 0
fi

echo "==== $(timestamp) watchdog: $COUNT consecutive ping failures, restarting NetworkManager ====" >> "$LOG"
{
  echo "--- iw dev $IFACE link ---"
  iw dev "$IFACE" link 2>&1
  echo "--- nmcli dev show $IFACE ---"
  nmcli dev show "$IFACE" 2>&1
  echo "--- journalctl -u NetworkManager (last 5 min) ---"
  journalctl -u NetworkManager --since "5 minutes ago" 2>&1
} >> "$LOG"

systemctl restart NetworkManager
echo "$NOW" > "$LAST_RESTART_FILE"
echo 0 > "$FAIL_COUNT_FILE"

sleep 10
ping -I "$IFACE" -c2 -W3 "$TARGET" >/dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "==== $(timestamp) watchdog: NetworkManager restart succeeded, connectivity restored ====" >> "$LOG"
else
  echo "==== $(timestamp) watchdog: NetworkManager restart did NOT restore connectivity ====" >> "$LOG"
fi
