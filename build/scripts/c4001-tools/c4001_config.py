#!/usr/bin/env python3
import time
import serial

PORT = "/dev/ttyAMA1"   # UART1
BAUD = 9600             # current baud

ser = serial.Serial(PORT, BAUD, timeout=1)
print(f"Opened {PORT} at {BAUD} baud")

def send_cmd(cmd: str, wait: float = 0.2):
    line = (cmd + "\r\n").encode("ascii")
    print(f"--> {cmd!r}")
    ser.write(line)
    ser.flush()
    time.sleep(wait)
    # read any response lines
    while True:
        resp = ser.readline()
        if not resp:
            break
        try:
            s = resp.decode("ascii", errors="ignore").strip()
        except:
            continue
        if s:
            print(f"<-- {s!r}")

# 1) Stop the sensor so it will accept config commands
send_cmd("sensorStop", wait=0.5)

# 2) Switch to speed & distance measurement mode (runApp 1)
send_cmd("setRunApp 1", wait=0.5)

# 3) Save configuration to flash
send_cmd("saveConfig", wait=0.5)

# 4) Restart sensor so new mode takes effect
send_cmd("resetSystem 0", wait=1.0)

print("Done. Power-cycle not required; sensor restarted.")
