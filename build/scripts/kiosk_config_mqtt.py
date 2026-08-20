#!/usr/bin/env python3
"""Kiosk config MQTT bridge.

Exposes the settings that used to require re-running the local setup wizard
(dashboard URL, screensaver URL, screensaver timeout) as MQTT command/state
topics, so they can be changed live from Home Assistant without a reboot.
Also publishes a small retained "identity" payload used by the ha_kiosk_panel
HACS integration for auto-discovery, and an availability (LWT) topic.

Follows the same ini-driven, one-script-per-concern convention as the other
kiosk_*_mqtt bridges in this fleet.
"""
import configparser
import json
import socket
import subprocess
import time
from pathlib import Path

import paho.mqtt.client as mqtt

CONFIG_PATH = Path("/home/kiosk/kiosk_config.ini")
XSCREENSAVER_RC = Path("/home/kiosk/.xscreensaver")

SW_VERSION = "0.1.0"
MPD_PORT = 6600


def load_config():
    cfg = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Config file not found: {CONFIG_PATH}")
    cfg.read(CONFIG_PATH)

    if not cfg.has_section("mqtt"):
        raise RuntimeError("Missing [mqtt] section in kiosk_config.ini")

    m = cfg["mqtt"]
    base = m.get("base_topic", "kiosk").rstrip("/")
    return {
        "host": m.get("host"),
        "port": m.getint("port", fallback=1883),
        "user": m.get("username", fallback=None),
        "pass": m.get("password", fallback=None),
        "base_topic": base,
        "panel_name": cfg.get("kiosk", "panel_name", fallback="kiosk"),
    }


def local_ip():
    # Doesn't actually send traffic - just asks the kernel which local
    # address it would route through to reach the outside world, which is
    # a reliable way to find the LAN IP without depending on a specific
    # interface name.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        s.close()


def get_ini(section, key, fallback=""):
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg.get(section, key, fallback=fallback) if cfg.has_section(section) else fallback


def set_ini(section, key, value):
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg.set(section, key, value)
    with open(CONFIG_PATH, "w") as f:
        cfg.write(f)


def restart_kiosk_service():
    subprocess.run(["sudo", "-n", "systemctl", "restart", "kiosk.service"], timeout=15)


def apply_screensaver_timeout(seconds):
    """Rewrites the xscreensaver 'timeout:' line to H:MM:SS and asks the
    running xscreensaver daemon to reload it immediately - no restart of any
    systemd unit needed, xscreensaver has its own live-reload command."""
    try:
        seconds = max(10, int(seconds))
    except (TypeError, ValueError):
        return
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    timeout_str = f"{hours}:{minutes:02d}:{secs:02d}"

    lines = XSCREENSAVER_RC.read_text().splitlines() if XSCREENSAVER_RC.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("timeout:"):
            lines[i] = f"timeout:\t{timeout_str}"
            found = True
            break
    if not found:
        lines.append(f"timeout:\t{timeout_str}")
    XSCREENSAVER_RC.write_text("\n".join(lines) + "\n")

    subprocess.run(
        ["env", "DISPLAY=:0", "xscreensaver-command", "-restart"],
        timeout=10, capture_output=True,
    )


def main():
    cfg = load_config()
    base = cfg["base_topic"]

    availability_topic = f"{base}/availability"
    panel_topic = f"{base}/panel/state"

    topics = {
        "dashboard_url": (f"{base}/dashboard_url/set", f"{base}/dashboard_url/state", "kiosk", "url"),
        "screensaver_url": (f"{base}/screensaver_url/set", f"{base}/screensaver_url/state", "screensaver", "url"),
        "screensaver_timeout": (f"{base}/screensaver_timeout/set", f"{base}/screensaver_timeout/state", "screensaver", "timeout_seconds"),
    }

    client = mqtt.Client(client_id=f"kiosk_config_{cfg['panel_name']}")
    if cfg["user"]:
        client.username_pw_set(cfg["user"], cfg["pass"])
    client.will_set(availability_topic, payload="offline", qos=1, retain=True)

    def publish_current_state():
        for _cmd_topic, state_topic, section, key in topics.values():
            value = get_ini(section, key)
            client.publish(state_topic, value, qos=1, retain=True)

    def publish_identity():
        payload = json.dumps({
            "name": cfg["panel_name"],
            "ip": local_ip(),
            "mpd_port": MPD_PORT,
            "sw_version": SW_VERSION,
        })
        client.publish(panel_topic, payload, qos=1, retain=True)
        client.publish(availability_topic, "online", qos=1, retain=True)

    def on_connect(c, userdata, flags, rc):
        for cmd_topic, *_rest in topics.values():
            c.subscribe(cmd_topic, qos=1)
        publish_identity()
        publish_current_state()

    def on_message(c, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="ignore").strip()
        for cmd_topic, state_topic, section, key in topics.values():
            if msg.topic != cmd_topic:
                continue
            if key == "timeout_seconds":
                set_ini(section, key, payload)
                apply_screensaver_timeout(payload)
            elif key == "url" and section == "kiosk":
                set_ini(section, key, payload)
                restart_kiosk_service()
            else:
                # screensaver url: webscreensaver-wrapper.sh re-reads the ini
                # on every screensaver activation, so no restart is needed.
                set_ini(section, key, payload)
            c.publish(state_topic, get_ini(section, key), qos=1, retain=True)
            break

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg["host"], cfg["port"], keepalive=60)

    # Re-announce identity periodically so the integration's discovery/
    # availability stays fresh even if a retained message ever gets lost.
    client.loop_start()
    try:
        while True:
            time.sleep(300)
            publish_identity()
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(availability_topic, "offline", qos=1, retain=True)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
