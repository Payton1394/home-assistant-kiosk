#!/usr/bin/env python3
import time
import configparser
import json
from pathlib import Path

import smbus2
import paho.mqtt.client as mqtt

CONFIG_PATH = Path("/home/kiosk/kiosk_config.ini")

I2C_BUS = 1
BH1750_ADDR = 0x23
BH1750_CONT_HIRES = 0x10

POLL_INTERVAL = 0.5
CHANGE_THRESHOLD = 0  # publish every read for now


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


def bh1750_read_lux(bus):
    bus.write_byte(BH1750_ADDR, BH1750_CONT_HIRES)
    time.sleep(0.18)
    data = bus.read_i2c_block_data(BH1750_ADDR, 0x00, 2)
    raw = (data[0] << 8) | data[1]
    return raw / 1.2


def main():
    cfg = load_config()
    bus = smbus2.SMBus(I2C_BUS)

    mqttc = mqtt.Client()
    if cfg["mqtt_user"]:
        mqttc.username_pw_set(cfg["mqtt_user"], cfg["mqtt_pass"])
    mqttc.connect(cfg["mqtt_host"], cfg["mqtt_port"], 60)
    mqttc.loop_start()

    # Final topics: kiosk/lulus_room/lux/state and /attributes
    lux_topic = f"{cfg['base_topic']}/lux/state"
    attr_topic = f"{cfg['base_topic']}/lux/attributes"

    last_lux = None

    while True:
        try:
            lux = bh1750_read_lux(bus)
        except OSError as e:
            print(f"BH1750 read error: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        lux_rounded = round(lux, 1)

        if last_lux is None or abs(lux_rounded - last_lux) >= CHANGE_THRESHOLD:
            payload = str(lux_rounded)
            print(f"Lux: {payload}")
            mqttc.publish(lux_topic, payload, qos=1, retain=True)

            attrs = {
                "unit_of_measurement": "lx",
                "sensor": "BH1750 (GY-302)",
                "bus": I2C_BUS,
                "address": hex(BH1750_ADDR),
            }
            mqttc.publish(attr_topic, json.dumps(attrs), qos=0, retain=True)

            last_lux = lux_rounded

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
