#!/usr/bin/env python3
import time
import signal
import configparser
from pathlib import Path

import gpiod
import paho.mqtt.client as mqtt

CONFIG_PATH = Path("/home/kiosk/kiosk_config.ini")

# GPIO (libgpiod)
CHIP = "/dev/gpiochip0"
SENSOR_LINE = 14          # RCWL OUT -> BCM 23
POLL_INTERVAL = 0.1       # seconds

# Debounce: RCWL-0516 is electrically noisy and self-triggers, so require the
# reading to be stable for a bit before we believe it and publish a change.
# Fast to confirm someone arrived, slower to confirm they left (avoids flicker).
ON_CONFIRM_SECONDS = 0.3
OFF_CONFIRM_SECONDS = 2.0

running = True


def handle_signal(signum, frame):
    global running
    running = False


def load_mqtt_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    m = cfg["mqtt"]
    base = m.get("base_topic", "kiosk")
    return {
        "host": m.get("host", "127.0.0.1"),
        "port": m.getint("port", fallback=1883),
        "user": m.get("username", fallback=None),
        "pass": m.get("password", fallback=None),
        # same topic name convention already used elsewhere in the fleet
        "topic": f"{base}/presence",
    }


def setup_gpio():
    req = gpiod.request_lines(
        CHIP,
        consumer="rcwl_presence",
        config={
            SENSOR_LINE: gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT
            )
        },
    )
    return req


def read_sensor(req):
    vals = req.get_values([SENSOR_LINE])
    return bool(vals[0])


def setup_mqtt(cfg):
    client = mqtt.Client()
    if cfg["user"]:
        client.username_pw_set(cfg["user"], cfg["pass"])
    client.connect(cfg["host"], cfg["port"], keepalive=60)
    client.loop_start()
    return client


def publish_state(client, topic, state: bool):
    client.publish(topic, "ON" if state else "OFF", retain=True)


def main():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    cfg = load_mqtt_config()
    req = setup_gpio()
    client = setup_mqtt(cfg)

    published_state = False
    candidate_state = False
    candidate_since = time.time()

    try:
        publish_state(client, cfg["topic"], False)

        while running:
            raw = read_sensor(req)
            now = time.time()

            if raw != candidate_state:
                candidate_state = raw
                candidate_since = now

            confirm_needed = ON_CONFIRM_SECONDS if candidate_state else OFF_CONFIRM_SECONDS
            if candidate_state != published_state and (now - candidate_since) >= confirm_needed:
                published_state = candidate_state
                publish_state(client, cfg["topic"], published_state)

            time.sleep(POLL_INTERVAL)

    finally:
        client.loop_stop()
        client.disconnect()
        req.release()


if __name__ == "__main__":
    main()
