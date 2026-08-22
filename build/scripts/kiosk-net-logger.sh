#!/bin/bash
LOG=/home/kiosk/kiosk-net.log
TARGET=192.168.1.1
IFACE=wlan0
STATE_DIR=/run/kiosk-net-logger
LAST_THROTTLED_FILE="$STATE_DIR/last_throttled"

mkdir -p "$STATE_DIR"

timestamp() { date "+%Y-%m-%d %H:%M:%S"; }

decode_throttled() {
  local val=$(( $1 ))
  local flags=""
  [ $((val & 0x1))     -ne 0 ] && flags="$flags under-voltage-now"
  [ $((val & 0x2))     -ne 0 ] && flags="$flags freq-capped-now"
  [ $((val & 0x4))     -ne 0 ] && flags="$flags throttled-now"
  [ $((val & 0x8))     -ne 0 ] && flags="$flags soft-temp-limit-now"
  [ $((val & 0x10000)) -ne 0 ] && flags="$flags under-voltage-occurred"
  [ $((val & 0x20000)) -ne 0 ] && flags="$flags freq-capped-occurred"
  [ $((val & 0x40000)) -ne 0 ] && flags="$flags throttled-occurred"
  [ $((val & 0x80000)) -ne 0 ] && flags="$flags soft-temp-limit-occurred"
  [ -z "$flags" ] && flags=" none"
  echo "$flags"
}

THROTTLED_RAW=$(vcgencmd get_throttled 2>/dev/null)
THROTTLED_HEX=$(echo "$THROTTLED_RAW" | cut -d= -f2)
LAST_THROTTLED="0x0"
[ -f "$LAST_THROTTLED_FILE" ] && LAST_THROTTLED=$(cat "$LAST_THROTTLED_FILE")

if [ -n "$THROTTLED_HEX" ] && [ "$THROTTLED_HEX" != "$LAST_THROTTLED" ]; then
  echo "==== $(timestamp) throttle status changed: $THROTTLED_RAW ($(decode_throttled "$THROTTLED_HEX")) ====" >> "$LOG"
fi
[ -n "$THROTTLED_HEX" ] && echo "$THROTTLED_HEX" > "$LAST_THROTTLED_FILE"

ping -I "$IFACE" -c2 -W3 "$TARGET" >/dev/null 2>&1
RC=$?

if [ "$RC" -ne 0 ]; then
  echo "==== $(timestamp) net snapshot (PING FAIL rc=$RC) ====" >> "$LOG"

  {
    echo "--- vcgencmd get_throttled ---"
    echo "$THROTTLED_RAW ($(decode_throttled "$THROTTLED_HEX"))"
    echo "--- iw dev $IFACE link ---"
    iw dev "$IFACE" link 2>&1
    echo "--- iwconfig $IFACE ---"
    iwconfig "$IFACE" 2>&1
    echo "--- nmcli dev show $IFACE ---"
    nmcli dev show "$IFACE" 2>&1
    echo "--- journalctl -u NetworkManager (last 5 min) ---"
    journalctl -u NetworkManager --since "5 minutes ago" 2>&1
    echo "--- dmesg | grep -i brcm ---"
    dmesg | grep -i brcm 2>&1
    echo
  } >> "$LOG"
fi
