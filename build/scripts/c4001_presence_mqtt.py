#!/usr/bin/env python3
import json
import queue
import re
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

# Tuning from Home Assistant (2026-10-17): the sensor's presence-mode settings
# are Home Assistant number entities on the kiosk's own device, made by the
# ha_kiosk_panel integration (0.4.0+, custom_components in this repo) from the
# topics below. Without that integration, `[c4001] ha_discovery = true` makes
# them by MQTT discovery instead (a "<Room> Kiosk Presence" device); with it off
# (the default) the discovery entries are cleared, so the two never double up.
# A change arrives on <base>/presence/tuning/<key>/set;
# the main loop stops the sensor, sends the setting, saves it to the sensor's
# flash, reads every setting back and starts it again (about three seconds with
# no frames), then publishes what the sensor now holds as JSON on
# <base>/presence/tuning/state. Commands and their order are DFRobot's C4001
# manual: setRange <min m> <max m>, setTrigRange <m>, setSensitivity <hold 0-9>
# <trigger 0-9>, setLatency <confirm s> <clear s>, saveConfig, sensorStart; each
# answered "Done" or "Error", a get* with "Response <values>".
TUNABLES = [
    # key, name, min, max, step, unit, icon
    ("max_range", "Detection distance", 1.0, 12.0, 0.1, "m", "mdi:signal-distance-variant"),
    ("trig_range", "Trigger distance", 0.6, 12.0, 0.1, "m", "mdi:ray-start-arrow"),
    ("trig_sens", "Trigger sensitivity", 0, 9, 1, None, "mdi:tune-vertical"),
    ("hold_sens", "Hold sensitivity", 0, 9, 1, None, "mdi:tune-vertical-variant"),
    ("confirm_delay", "Confirmation delay", 0.0, 5.0, 0.05, "s", "mdi:timer-sand"),
    ("clear_delay", "Clear after", 1, 600, 1, "s", "mdi:timer-off-outline"),
]
LIMITS = {k: (lo, hi) for k, _n, lo, hi, _s, _u, _i in TUNABLES}


def load_config():
    cfg = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    cfg.read(CONFIG_PATH)

    if "mqtt" not in cfg or "c4001" not in cfg:
        raise KeyError("Missing [mqtt] or [c4001] section in config")

    m = cfg["mqtt"]
    c = cfg["c4001"]

    k = cfg["kiosk"] if "kiosk" in cfg else {}
    panel = (k.get("panel_name") or "").strip()
    ha_name = c.get("ha_name", fallback=panel.replace("-", " ").title() or "Kiosk")
    discovery_prefix = c.get("discovery_prefix", fallback="homeassistant")
    tuning = c.getboolean("tuning", fallback=True)
    ha_discovery = c.getboolean("ha_discovery", fallback=False)

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
        "base_topic": base_topic.rstrip("/"),
        "ha_name": ha_name,
        "discovery_prefix": discovery_prefix,
        "tuning": tuning,
        "ha_discovery": ha_discovery,
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


# ---- the sensor's command line ------------------------------------------------

def transact(ser, cmd, timeout=2.5):
    """Send one command; return its answer lines (frames skipped) up to Done/Error."""
    ser.write((cmd + "\r\n").encode("ascii"))
    ser.flush()
    lines, end = [], time.time() + timeout
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        s = raw.decode("ascii", errors="ignore").strip()
        if not s or s.startswith("$DF") or s.startswith("DFRobot:"):
            continue
        lines.append(s)
        if s in ("Done", "Error"):
            break
    return lines


def response(lines):
    for s in lines:
        m = re.match(r"Response\s+(.*)", s)
        if m:
            try:
                return [float(x) for x in m.group(1).split()]
            except ValueError:
                return None
    return None


def stop_sensor(ser):
    for _ in range(5):
        if "Done" in transact(ser, "sensorStop", 3.0):
            return True
        time.sleep(0.4)
    return False


def read_settings(ser):
    """What the (stopped) sensor holds, in TUNABLES' keys."""
    out = {}
    r = response(transact(ser, "getRange"))
    if r and len(r) >= 2:
        out["min_range"], out["max_range"] = round(r[0], 2), round(r[1], 2)
    r = response(transact(ser, "getTrigRange"))
    if r:
        out["trig_range"] = round(r[0], 2)
    r = response(transact(ser, "getSensitivity"))
    if r and len(r) >= 2:
        out["hold_sens"], out["trig_sens"] = int(r[0]), int(r[1])
    r = response(transact(ser, "getLatency"))
    if r and len(r) >= 2:
        out["confirm_delay"], out["clear_delay"] = round(r[0], 3), round(r[1], 1)
    return out


def apply_settings(ser, current, changes):
    """Stop, set what changed, save, read back, start. Returns (settings, ok)."""
    want = {**current, **changes}
    for key, (lo, hi) in LIMITS.items():
        if key in want:
            want[key] = max(lo, min(hi, want[key]))
    min_range = want.get("min_range", 0.6)
    want["max_range"] = max(want.get("max_range", 6.0), min_range + 0.1)
    want["trig_range"] = min(want.get("trig_range", want["max_range"]), want["max_range"])
    ok = stop_sensor(ser)
    sent = []
    if ok and ({"max_range", "trig_range"} & changes.keys()):
        sent += [f"setRange {min_range:.1f} {want['max_range']:.1f}", f"setTrigRange {want['trig_range']:.1f}"]
    if ok and ({"trig_sens", "hold_sens"} & changes.keys()):
        sent.append(f"setSensitivity {int(round(want.get('hold_sens', 7)))} {int(round(want.get('trig_sens', 5)))}")
    if ok and ({"confirm_delay", "clear_delay"} & changes.keys()):
        sent.append(f"setLatency {want.get('confirm_delay', 0.5):.2f} {want.get('clear_delay', 15):.1f}")
    for cmd in sent:
        if "Done" not in transact(ser, cmd):
            ok = False
            print(f"c4001: {cmd!r} was refused", flush=True)
    if sent:
        transact(ser, "saveConfig", 3.0)
    settings = read_settings(ser) or current
    transact(ser, "sensorStart", 3.0)
    return settings, ok


def open_mqtt(cfg, commands):
    client = mqtt.Client(client_id="c4001_" + cfg["presence_topic"].replace("/", "_"))   # unique per kiosk (a shared id made every kiosk kick the others off the broker)
    if cfg["mqtt_user"]:
        client.username_pw_set(cfg["mqtt_user"], cfg["mqtt_pass"])
    base = cfg["base_topic"]
    avail = f"{base}/presence/tuning/available"
    if cfg["tuning"]:
        client.will_set(avail, "offline", qos=1, retain=True)

    def on_connect(c, _userdata, _flags, rc, *_):
        if not cfg["tuning"]:
            return
        c.subscribe(f"{base}/presence/tuning/+/set", qos=1)
        publish_discovery(c, cfg)
        c.publish(avail, "online", qos=1, retain=True)
        commands.put(("refresh", None, None))   # (re)send the state after a reconnect

    def on_message(_c, _userdata, msg):
        parts = msg.topic.split("/")
        key = parts[-2] if len(parts) >= 2 else ""
        if key not in LIMITS:
            return
        try:
            value = float(msg.payload.decode().strip())
        except ValueError:
            return
        commands.put(("set", key, value))

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg["mqtt_host"], cfg["mqtt_port"], 60)
    client.loop_start()
    return client


def publish_discovery(client, cfg):
    """One Home Assistant number per setting, on a "<Room> Kiosk Presence" device
    (ha_discovery on), or the empty retained configs that remove them (off)."""
    base = cfg["base_topic"]
    node = base.replace("/", "_").replace("-", "_") + "_c4001"
    device = {"identifiers": [node], "name": f"{cfg['ha_name']} Kiosk Presence",
              "manufacturer": "DFRobot", "model": "C4001 mmWave"}
    for key, name, lo, hi, step, unit, ico in TUNABLES:
        payload = {
            "name": name, "unique_id": f"{node}_{key}", "icon": ico,
            "command_topic": f"{base}/presence/tuning/{key}/set",
            "state_topic": f"{base}/presence/tuning/state",
            "value_template": "{{ value_json.%s }}" % key,
            "availability_topic": f"{base}/presence/tuning/available",
            "min": lo, "max": hi, "step": step, "mode": "slider",
            "entity_category": "config", "device": device,
        }
        if unit:
            payload["unit_of_measurement"] = unit
        topic = f"{cfg['discovery_prefix']}/number/{node}/{key}/config"
        client.publish(topic, json.dumps(payload) if cfg["ha_discovery"] else "", qos=1, retain=True)


def main():
    cfg = load_config()
    ser = open_serial(cfg["uart_device"], cfg["baud"])
    commands = queue.Queue()
    mqttc = open_mqtt(cfg, commands)
    tuning_topic = f"{cfg['base_topic']}/presence/tuning/state"
    settings = {}
    if cfg["tuning"]:
        # What the sensor holds now: stop, read, start (a moment without frames).
        stop_sensor(ser)
        settings = read_settings(ser)
        transact(ser, "sensorStart", 3.0)
        mqttc.publish(tuning_topic, json.dumps(settings), qos=1, retain=True)
        print(f"c4001: settings {settings}", flush=True)

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
        # Settings from Home Assistant: everything waiting, applied in one go.
        changes, refresh = {}, False
        while True:
            try:
                kind, key, value = commands.get_nowait()
            except queue.Empty:
                break
            if kind == "set":
                changes[key] = value
            else:
                refresh = True
        if changes:
            settings, ok = apply_settings(ser, settings, changes)
            print(f"c4001: {changes} -> {settings}{'' if ok else ' (not all applied)'}", flush=True)
            if last_state == "ON":
                last_present_ts = time.time()   # the pause was ours, not someone leaving
        if changes or refresh:
            mqttc.publish(tuning_topic, json.dumps(settings), qos=1, retain=True)

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
