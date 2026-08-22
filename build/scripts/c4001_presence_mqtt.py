#!/usr/bin/env python3
import time
import statistics
import serial
import configparser
import paho.mqtt.client as mqtt
from pathlib import Path

CONFIG_PATH = Path("/home/kiosk/kiosk_config.ini")  # adjust if needed

# Presence ON fires on the very first detected frame (fast to notice someone's there).
# OFF is still debounced via hold_seconds below (slow to clear), so we get quick
# detection without flapping. An earlier version required multiple consecutive
# "present" frames before firing ON, but the sensor is noisy enough on initial
# acquisition (flag flickers 1/0/1) that this was delaying detection significantly.


def load_config():
    cfg = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    cfg.read(CONFIG_PATH)

    if "mqtt" not in cfg or "c4001" not in cfg:
        raise KeyError("Missing [mqtt] or [c4001] section in config")

    m = cfg["mqtt"]
    c = cfg["c4001"]

    mqtt_host = m.get("host", "127.0.0.1")
    mqtt_port = m.getint("port", fallback=1883)
    mqtt_user = m.get("username", fallback=None)
    mqtt_pass = m.get("password", fallback=None)
    base_topic = m.get("base_topic", "kiosk")

    uart_device = c.get("uart_device", "/dev/ttyAMA1")
    baud = c.getint("baud", fallback=9600)
    hold_seconds = c.getint("hold_seconds", fallback=10)
    topic_suffix = c.get("topic", "presence/state")
    distance_suffix = c.get("distance_topic", "presence/distance")

    # Sanity bounds for a raw distance reading, in meters - readings outside this
    # are treated as UART noise/misparsed frames and dropped before smoothing.
    # This is per-device on purpose: each C4001 unit is tuned independently via
    # c4001_tune.py's `setDetectionRange`, so a kiosk in a small space (tight
    # range) and one in a bigger room (wider range) need different bounds here.
    # Defaults are deliberately generous (the sensor's untuned factory range)
    # so a device with no [c4001] min/max_valid_distance_m set doesn't have
    # legitimate readings silently thrown away.
    min_valid_distance = c.getfloat("min_valid_distance_m", fallback=0.05)
    max_valid_distance = c.getfloat("max_valid_distance_m", fallback=6.0)

    # Smoothing/throttle settings for the published distance value. This sensor
    # runs in speed/motion-measurement mode (see c4001_config.py), so real
    # detections can arrive as short bursts of only a few frames - if the
    # publish interval is longer than a typical burst, some detections would
    # never get a distance published at all. Tunable per-device since some
    # kiosks may see more continuous motion than others.
    distance_window = c.getint("distance_window", fallback=5)
    distance_publish_interval = c.getfloat("distance_publish_interval", fallback=0.2)
    distance_change_threshold = c.getfloat("distance_change_threshold", fallback=0.1)

    presence_topic = f"{base_topic}/{topic_suffix}".rstrip("/")
    distance_topic = f"{base_topic}/{distance_suffix}".rstrip("/")

    return {
        "mqtt_host": mqtt_host,
        "mqtt_port": mqtt_port,
        "mqtt_user": mqtt_user,
        "mqtt_pass": mqtt_pass,
        "presence_topic": presence_topic,
        "distance_topic": distance_topic,
        "uart_device": uart_device,
        "baud": baud,
        "hold_seconds": hold_seconds,
        "min_valid_distance": min_valid_distance,
        "max_valid_distance": max_valid_distance,
        "distance_window": distance_window,
        "distance_publish_interval": distance_publish_interval,
        "distance_change_threshold": distance_change_threshold,
    }


def open_serial(dev, baud):
    return serial.Serial(dev, baudrate=baud, timeout=1)


def open_mqtt(cfg):
    client = mqtt.Client(client_id="kiosk_c4001")
    if cfg["mqtt_user"]:
        client.username_pw_set(cfg["mqtt_user"], cfg["mqtt_pass"])
    client.connect(cfg["mqtt_host"], cfg["mqtt_port"], 60)
    client.loop_start()
    return client


def main():
    cfg = load_config()
    ser = open_serial(cfg["uart_device"], cfg["baud"])
    mqttc = open_mqtt(cfg)

    # Explicitly clear presence on startup. Without this, a restart (service
    # crash, redeploy, manual restart) leaves whatever was last retained on
    # the broker in place - if that happened to be "ON", it stays stuck ON
    # forever until the next real detection cycles through, even though the
    # sensor itself is correctly reporting "absent" the whole time.
    mqttc.publish(cfg["presence_topic"], "OFF", qos=1, retain=True)

    last_state = "OFF"
    last_present_ts = 0

    # Periodically re-publish the current state even without a change, so a
    # single dropped MQTT packet (QoS 0 default has no delivery guarantee)
    # can't desync the broker/HA from what the script believes internally -
    # it self-corrects within one heartbeat interval instead of staying stuck.
    HEARTBEAT_SECONDS = 5
    last_heartbeat_ts = 0.0

    dist_buf = []
    last_dist_publish_ts = 0.0
    last_dist_published = None

    while True:
        now = time.time()
        line = ser.readline()

        if line:
            try:
                s = line.decode("ascii", errors="ignore").strip()
            except Exception:
                continue

            # This sensor can be configured in two different modes (see
            # c4001_tune.py / c4001_tune_presence_mode.py), each with
            # its own output sentence - handle both so the same script works
            # regardless of which mode a given kiosk's sensor is tuned for.
            #
            # Presence-detection mode: $DFHPD,flag, , , *  (flag only, no
            # distance/speed - the sensor's own setLatency handles confirm/
            # disappear debouncing internally, so we mostly just mirror it)
            #
            # Speed/distance-measurement mode:
            #   present: $DFDMD,1,1,1.204,0.224,401, , *
            #   absent : $DFDMD,0, , , , , , *
            if s.startswith("$DFHPD"):
                parts = s.split(",")
                if len(parts) >= 2:
                    flag = parts[1].strip()
                    new_state = "ON" if flag == "1" else "OFF"
                    if new_state == "ON":
                        last_present_ts = now
                    if new_state != last_state:
                        mqttc.publish(cfg["presence_topic"], new_state, qos=1, retain=True)
                        last_state = new_state

            elif s.startswith("$DFDMD"):
                parts = s.split(",")
                if len(parts) >= 2:
                    flag = parts[1].strip()  # "0" or "1"

                    if flag == "1":
                        last_present_ts = now
                        if last_state != "ON":
                            mqttc.publish(cfg["presence_topic"], "ON", qos=1, retain=True)
                            last_state = "ON"

                    # Distance field (par3) for info - only present in $DFDMD
                    if len(parts) >= 4:
                        dist_str = parts[3].strip()
                        if dist_str:
                            try:
                                distance_m = float(dist_str)
                            except ValueError:
                                distance_m = None

                            # Drop physically implausible readings outright - these
                            # are almost always corrupted/misaligned UART frames or
                            # multipath reflections, not real detections, and were
                            # the cause of the value jumping wildly (e.g. to 14+).
                            if distance_m is not None and not (
                                cfg["min_valid_distance"] <= distance_m <= cfg["max_valid_distance"]
                            ):
                                distance_m = None

                            if distance_m is not None:
                                dist_buf.append(distance_m)
                                if len(dist_buf) > cfg["distance_window"]:
                                    dist_buf.pop(0)

                                # median is more robust than mean against single
                                # wild outlier readings (reflections, multi-target noise)
                                smoothed = statistics.median(dist_buf)

                                due = (now - last_dist_publish_ts) >= cfg["distance_publish_interval"]
                                moved = (
                                    last_dist_published is None
                                    or abs(smoothed - last_dist_published) >= cfg["distance_change_threshold"]
                                )
                                if due and moved:
                                    mqttc.publish(
                                        cfg["distance_topic"],
                                        f"{smoothed:.3f}",
                                        retain=True,
                                    )
                                    last_dist_published = smoothed
                                    last_dist_publish_ts = now

        # Failsafe: if we haven't seen a fresh "present" signal for hold_seconds,
        # force OFF. In $DFHPD/presence mode the sensor's own setLatency disappear
        # delay normally handles this already (set hold_seconds comfortably above
        # that value so this is a backstop, not the primary mechanism); in $DFDMD/
        # distance mode this is the only debounce, since that mode has no
        # equivalent onboard disappearance timer.
        if last_state == "ON" and (now - last_present_ts) > cfg["hold_seconds"]:
            mqttc.publish(cfg["presence_topic"], "OFF", qos=1, retain=True)
            last_state = "OFF"

        # Heartbeat: re-assert current state periodically regardless of change,
        # so a lost packet gets corrected quickly instead of persisting.
        if (now - last_heartbeat_ts) >= HEARTBEAT_SECONDS:
            mqttc.publish(cfg["presence_topic"], last_state, qos=1, retain=True)
            last_heartbeat_ts = now


if __name__ == "__main__":
    main()
