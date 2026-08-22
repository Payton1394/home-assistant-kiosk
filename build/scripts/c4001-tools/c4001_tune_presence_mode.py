#!/usr/bin/env python3
# Switches this kiosk's C4001 from speed/distance-measurement mode into
# dedicated presence-detection mode, which has proper long-range trigger/hold
# sensitivity and a configurable trigger range - built for "detect someone at
# 4-20ft" use cases, unlike distance mode.
#
# Trade-off: presence mode outputs $DFHPD (just a 0/1 flag), not $DFDMD -
# there is no distance/speed value in this mode. If this kiosk has an HA
# entity bound to its distance topic (e.g. sensor.<room>_presence_distance),
# that entity will stop updating once this is deployed - repoint any
# automation depending on it at the presence binary_sensor instead.
#
# Generic/reusable across kiosks - no hardcoded topics or device names here,
# just the local UART port. Run ON the kiosk Pi, with c4001_presence.service
# stopped first (it holds the serial port open):
#   sudo systemctl stop c4001_presence.service
#   python3 c4001_tune_presence_mode.py
#   sudo systemctl start c4001_presence.service   (after deploying the
#     updated c4001_presence_mqtt.py that understands $DFHPD)

import time
import serial

PORT = "/dev/ttyAMA1"
BAUD = 9600

ser = serial.Serial(PORT, BAUD, timeout=1)
print(f"Opened {PORT} at {BAUD} baud")


def send_cmd(cmd: str, wait: float = 0.3):
    line = (cmd + "\r\n").encode("ascii")
    print(f"--> {cmd}")
    ser.write(line)
    ser.flush()
    time.sleep(wait)
    while True:
        resp = ser.readline()
        if not resp:
            break
        try:
            s = resp.decode("ascii", errors="ignore").strip()
        except Exception:
            continue
        if s:
            print(f"<-- {s}")


send_cmd("sensorStop", wait=0.5)

# Switch to presence detection mode. Per DFRobot docs this takes effect
# immediately once recognized, so the presence-only commands below can be
# configured in the same session.
send_cmd("setRunApp 0")

# Overall detection range in meters (min, max) - covers out past 20ft.
send_cmd("setRange 0.6 6.5")

# Trigger distance in meters: how far away "someone" can first be detected.
# Set to ~20ft (6.1m) with a touch of margin under the 6.5m max range.
# Adjust down if this kiosk's room is smaller and you want a tighter zone.
send_cmd("setTrigRange 6.1")

# Sensitivity: hold (0-9, how well it keeps tracking once triggered) and
# trigger (0-9, how easily it first triggers). Docs recommend keeping
# trigger between 2-6 to avoid false alarms; going with 6 for reliable
# detection at the far end of a 20ft range. Raise hold if it loses lock
# on a stationary person too quickly.
send_cmd("setSensitivity 7 6")

# Confirmation delay (seconds before reporting "someone", filters noise) and
# disappearance delay (seconds of no detection before reporting "no one").
send_cmd("setLatency 0.5 15")

send_cmd("saveConfig", wait=0.5)
send_cmd("sensorStart", wait=0.5)

print("Done. Sensor now in presence-detection mode: range 0.6-6.5m,")
print("trigger range 6.1m (~20ft), sensitivity hold=7/trigger=6,")
print("confirm 0.5s / disappear 15s.")
