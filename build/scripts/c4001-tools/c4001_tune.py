#!/usr/bin/env python3
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
        except:
            continue
        if s:
            print(f"<-- {s}")

# Stop sensor so it accepts config
send_cmd("sensorStop", wait=0.5)

# Set detection range:
# min = 30 cm, max = 150 cm, trig = 150 cm
send_cmd("setDetectionRange 30 150 150")

# Set trigger sensitivity (0–9, higher = more sensitive)
send_cmd("setTrigSensitivity 2")

# Set keep sensitivity (0–9, higher = more likely to stay ON)
send_cmd("setKeepSensitivity 2")

# Save configuration
send_cmd("saveConfig", wait=0.5)

# Restart sensor
send_cmd("resetSystem 0", wait=1.0)

print("Done tuning C4001.")
