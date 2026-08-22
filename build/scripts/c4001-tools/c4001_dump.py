#!/usr/bin/env python3
import serial, time

ser = serial.Serial("/dev/ttyAMA1", 9600, timeout=1)
print("Opened /dev/ttyAMA1 at 9600 baud")

while True:
    line = ser.readline()
    if not line:
        continue
    try:
        s = line.decode("ascii", errors="ignore").strip()
    except:
        continue
    print(time.time(), s)
