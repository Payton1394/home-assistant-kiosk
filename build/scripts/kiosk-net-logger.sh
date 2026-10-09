#!/bin/bash
LOG=/home/kiosk/kiosk-net.log
IFACE=wlan0
# Ping the Wi-Fi's own default gateway, whatever network the kiosk is on (was a fixed 192.168.1.1).
# No route on wlan0 means no connectivity, so an empty target simply counts as a failed check.
TARGET=$(/usr/sbin/ip -4 route show default dev "$IFACE" 2>/dev/null | awk '{print $3; exit}')
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

# On Ethernet the Wi-Fi is not in use: no ping, no snapshot. Until 2026-10-01
# this wrote ~95 KB to kiosk-net.log every 2 minutes on the wired kiosks.
# (The throttle-status line above still runs.)
if [ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" = "1" ] && /usr/sbin/ip -4 route show default dev eth0 2>/dev/null | grep -q .; then
  exit 0
fi
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
