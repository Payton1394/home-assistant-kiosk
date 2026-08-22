#!/usr/bin/env python3
import serial, time

ser = serial.Serial("/dev/ttyAMA1", 9600, timeout=1)
print("Opened /dev/ttyAMA1 at 9600 baud")

while True:
    data = ser.read(32)
    if data:
        print(time.time(), len(data), data.hex())
