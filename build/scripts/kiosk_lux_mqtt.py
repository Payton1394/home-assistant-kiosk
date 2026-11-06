#!/usr/bin/env python3
"""Ambient light -> MQTT for the kiosk's lux-based brightness.

Works with either sensor on I2C bus 1, whichever answers:
  - VEML7700 (Adafruit #4162) at 0x10: reads down to ~0.004 lx, so it tells
    a dim room from a dark one (the BH1750 bottoms out at ~1 lx). Auto-ranges:
    starts at its most sensitive setting (gain x2, 800 ms) and steps gain and
    integration time down in bright light so the count never saturates;
    above 1000 lx Vishay's non-linearity correction is applied.
  - BH1750 (GY-302 breakout) at 0x23, the original sensor.

Publishes <base_topic>/lux/state (retained) when the light changes by 3 % or
0.05 lx, and at least once a minute, instead of on every read: a precise
sensor jitters, and Home Assistant records every state change.
"""
import time
import configparser
import json
from pathlib import Path

import smbus2
import paho.mqtt.client as mqtt

CONFIG_PATH = Path("/home/kiosk/kiosk_config.ini")

I2C_BUS = 1
VEML7700_ADDR = 0x10
BH1750_ADDR = 0x23
BH1750_CONT_HIRES = 0x10

REL_CHANGE = 0.03          # publish when the light changes by 3 % ...
ABS_CHANGE = 0.05          # ... or by 0.05 lx, whichever is larger
HEARTBEAT_S = 60           # and at least this often
BH1750_POLL_S = 0.5


def load_config():
    cfg = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Config file not found: {CONFIG_PATH}")
    cfg.read(CONFIG_PATH)

    if not cfg.has_section("mqtt"):
        raise RuntimeError("Missing [mqtt] section in kiosk_config.ini")

    host = cfg.get("mqtt", "host")
    port = cfg.getint("mqtt", "port", fallback=1883)
    user = cfg.get("mqtt", "username", fallback=None)
    password = cfg.get("mqtt", "password", fallback=None)
    base = cfg.get("mqtt", "base_topic").rstrip("/")   # kiosk/lulus_room

    return {
        "mqtt_host": host,
        "mqtt_port": port,
        "mqtt_user": user,
        "mqtt_pass": password,
        "base_topic": base,
    }


# ---- VEML7700 -------------------------------------------------------------
# Register 0x00 (ALS_CONF): gain in bits 12:11, integration time in bits 9:6,
# bit 0 = shut down. Register 0x04 = ALS count. Words are little-endian,
# which is what SMBus word reads/writes use.
VEML_GAIN_BITS = {2: 0b01, 1: 0b00, 0.25: 0b11, 0.125: 0b10}
VEML_IT_BITS = {800: 0b0011, 400: 0b0010, 200: 0b0001, 100: 0b0000, 50: 0b1000, 25: 0b1100}
# Most sensitive first. Resolution (lx per count) is 0.0036 at gain 2 / 800 ms
# and scales inversely with gain and integration time.
VEML_STEPS = ([(g, 800) for g in (2, 1, 0.25, 0.125)] +
              [(0.125, it) for it in (400, 200, 100, 50, 25)])
VEML_HIGH = 50000          # step to less sensitive above this count
VEML_LOW = 100             # step to more sensitive below this count


class Veml7700:
    name = "VEML7700"
    address = VEML7700_ADDR

    def __init__(self, bus):
        self.bus = bus
        self.step = 0
        self._apply()

    def _apply(self):
        gain, it = VEML_STEPS[self.step]
        conf = (VEML_GAIN_BITS[gain] << 11) | (VEML_IT_BITS[it] << 6)   # power on, no interrupts
        self.bus.write_word_data(VEML7700_ADDR, 0x00, conf)
        # Let one full integration run with the new setting.
        time.sleep(it / 1000 * 1.2 + 0.05)

    def settings(self):
        gain, it = VEML_STEPS[self.step]
        return {"gain": gain, "integration_ms": it}

    def read(self):
        """Lux, auto-ranging first. Returns (lux, seconds to wait before the next read)."""
        for _ in range(len(VEML_STEPS)):
            raw = self.bus.read_word_data(VEML7700_ADDR, 0x04)
            if raw > VEML_HIGH and self.step < len(VEML_STEPS) - 1:
                self.step += 1
                self._apply()
                continue
            if raw < VEML_LOW and self.step > 0:
                self.step -= 1
                self._apply()
                continue
            break
        gain, it = VEML_STEPS[self.step]
        lux = raw * 0.0036 * (800 / it) * (2 / gain)
        if lux > 1000:
            # Vishay's correction for the sensor's non-linearity in bright light.
            lux = (6.0135e-13 * lux ** 4 - 9.3924e-9 * lux ** 3 + 8.1488e-5 * lux ** 2 + 1.0023 * lux)
        return lux, it / 1000


class Bh1750:
    name = "BH1750 (GY-302)"
    address = BH1750_ADDR

    def __init__(self, bus):
        self.bus = bus

    def settings(self):
        return {}

    def read(self):
        self.bus.write_byte(BH1750_ADDR, BH1750_CONT_HIRES)
        time.sleep(0.18)
        data = self.bus.read_i2c_block_data(BH1750_ADDR, 0x00, 2)
        raw = (data[0] << 8) | data[1]
        return raw / 1.2, BH1750_POLL_S


def find_sensor(bus):
    """The fitted sensor: VEML7700 first, then BH1750; None if neither answers."""
    try:
        bus.read_word_data(VEML7700_ADDR, 0x00)
        return Veml7700(bus)
    except OSError:
        pass
    try:
        bus.write_byte(BH1750_ADDR, 0x01)        # power on
        return Bh1750(bus)
    except OSError:
        return None


def rounded(lux):
    # Two decimals in the dark, where the VEML7700's resolution matters.
    return round(lux, 2) if lux < 10 else round(lux, 1)


def main():
    cfg = load_config()
    bus = smbus2.SMBus(I2C_BUS)

    sensor = None
    while sensor is None:
        sensor = find_sensor(bus)
        if sensor is None:
            print("No VEML7700 (0x10) or BH1750 (0x23) on I2C bus 1; retrying in 30 s")
            time.sleep(30)
    print(f"Lux sensor: {sensor.name} at {hex(sensor.address)}")

    mqttc = mqtt.Client()
    if cfg["mqtt_user"]:
        mqttc.username_pw_set(cfg["mqtt_user"], cfg["mqtt_pass"])
    mqttc.connect(cfg["mqtt_host"], cfg["mqtt_port"], 60)
    mqttc.loop_start()

    # Final topics: kiosk/lulus_room/lux/state and /attributes
    lux_topic = f"{cfg['base_topic']}/lux/state"
    attr_topic = f"{cfg['base_topic']}/lux/attributes"

    last_lux = None
    last_sent = 0.0

    while True:
        try:
            lux, wait = sensor.read()
        except OSError as e:
            print(f"{sensor.name} read error: {e}")
            time.sleep(1)
            continue

        lux = rounded(max(lux, 0.0))
        now = time.monotonic()
        changed = last_lux is None or abs(lux - last_lux) >= max(ABS_CHANGE, REL_CHANGE * last_lux)
        if changed or now - last_sent >= HEARTBEAT_S:
            mqttc.publish(lux_topic, str(lux), qos=1, retain=True)
            attrs = {
                "unit_of_measurement": "lx",
                "sensor": sensor.name,
                "bus": I2C_BUS,
                "address": hex(sensor.address),
                **sensor.settings(),
            }
            mqttc.publish(attr_topic, json.dumps(attrs), qos=0, retain=True)
            if changed:
                print(f"Lux: {lux}")
            last_lux, last_sent = lux, now

        time.sleep(wait)


if __name__ == "__main__":
    main()
