#!/usr/bin/env python3
"""Home Assistant Kiosk - first-boot setup wizard.

Stdlib-only on purpose: this runs before Wi-Fi exists, so it can't depend on
anything installed via pip/apt. Binds to 127.0.0.1 only - it's shown fullscreen
in the kiosk's own Chromium on the kiosk's own screen, never exposed to the
network.
"""
import configparser
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOME = Path("/home/kiosk")
CONFIG_PATH = HOME / "kiosk_config.ini"
EXAMPLE_PATH = HOME / "kiosk_config.ini.example"
PROVISIONED_MARKER = HOME / ".provisioned"
STATIC_DIR = Path(__file__).resolve().parent / "static"
LOG_PATH = HOME / "wizard_setup.log"

# Always tied to the overall MQTT enable/disable toggle - these don't need
# any extra sensor hardware, just an MQTT broker to talk to.
CORE_MQTT_SERVICES = [
    "kiosk_brightness_mqtt.service",
    "kiosk-dpms-mqtt.service",
    "kiosk-reboot-mqtt.service",
    "rpi-temp-mqtt.service",
    "kiosk-config-mqtt.service",
]

# Tied to their own "I have this sensor" checkbox (and still gated by the
# overall MQTT toggle, since none of them have anywhere to report without a
# broker).
SENSOR_SERVICES = {
    "lux": "kiosk-lux-mqtt.service",
    "c4001": "c4001_presence.service",
    "rcwl": "rcwl-presence.service",
}


# Screensaver on/off over MQTT drives xscreensaver, which is opt-in: the image
# ships without it and ensure_xscreensaver() installs it when the user ticks
# "Use the built-in screensaver" (on-screen or web setup wizard).
XSCREENSAVER_MQTT_SERVICE = "kiosk-screensaver-mqtt.service"
INSTALL_XSCREENSAVER = "/usr/local/sbin/kiosk-install-xscreensaver.sh"
SET_HOSTNAME = "/usr/local/sbin/kiosk-set-hostname"


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Private (600): the log records every command the wizard runs.
        with os.fdopen(os.open(LOG_PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def slugify(name):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "kiosk"


SECRET_ARGS = {"password", "wifi-sec.psk"}


def redact(cmd):
    """Command line for the log, without the Wi-Fi password (the value after "password" / "wifi-sec.psk")."""
    return " ".join("***" if i and cmd[i - 1] in SECRET_ARGS else c for i, c in enumerate(cmd))


def run(cmd, timeout=60, input=None):
    log("run: " + redact(cmd) + (" <with stdin input>" if input else ""))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
        log(f"  rc={p.returncode} stdout={p.stdout.strip()[:500]!r} stderr={p.stderr.strip()[:500]!r}")
        return p.returncode, p.stdout, p.stderr
    except (subprocess.TimeoutExpired, OSError) as e:
        log(f"  FAILED: {e}")
        return 1, "", str(e)


def scan_wifi():
    run(["sudo", "-n", "nmcli", "device", "wifi", "rescan"], timeout=15)
    time.sleep(2)
    rc, out, err = run(["sudo", "-n", "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"])
    seen = {}
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3 or not parts[0]:
            continue
        ssid, signal, security = parts[0], parts[1], ":".join(parts[2:])
        try:
            signal = int(signal)
        except ValueError:
            signal = 0
        if ssid not in seen or signal > seen[ssid]["signal"]:
            seen[ssid] = {"ssid": ssid, "signal": signal, "secure": bool(security.strip())}
    return sorted(seen.values(), key=lambda x: -x["signal"])


def wifi_device():
    rc, out, err = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"], timeout=10)
    for line in out.splitlines():
        dev, _, kind = line.partition(":")
        if kind == "wifi":
            return dev
    return "wlan0"


def connect_wifi(ssid, password, hidden=False):
    """Saves a NetworkManager profile named after the network, then brings it up.
    The profile is written explicitly (key-mgmt wpa-psk) because NetworkManager
    1.50+ fails "nmcli device wifi connect <ssid> password <pw>" with
    "802-11-wireless-security.key-mgmt: property is missing"."""
    if not ssid:
        return False, "No network selected"
    nm = ["sudo", "-n", "nmcli"]
    rc, out, err = run(nm + ["-g", "connection.type", "connection", "show", "id", ssid], timeout=10)
    exists = rc == 0 and out.strip() == "802-11-wireless"
    settings = ["802-11-wireless.ssid", ssid, "802-11-wireless.hidden", "yes" if hidden else "no",
                "connection.autoconnect", "yes"]
    if password:
        settings += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
    if exists:
        if not password:
            run(nm + ["connection", "modify", "id", ssid, "remove", "802-11-wireless-security"], timeout=15)
        rc, out, err = run(nm + ["connection", "modify", "id", ssid] + settings, timeout=15)
    else:
        rc, out, err = run(nm + ["connection", "add", "type", "wifi", "ifname", wifi_device(), "con-name", ssid] + settings,
                           timeout=15)
    if rc != 0:
        return False, err.strip() or out.strip() or "Could not save the Wi-Fi settings"
    rc, out, err = run(nm + ["--wait", "45", "connection", "up", "id", ssid], timeout=60)
    return rc == 0, (err.strip() or out.strip() or ("Connected" if rc == 0 else "Unknown error"))


def is_service_enabled(svc):
    rc, out, err = run(["systemctl", "is-enabled", svc], timeout=10)
    return out.strip() == "enabled"


def wifi_connected():
    rc, out, err = run(["nmcli", "-t", "-f", "TYPE,STATE", "device"], timeout=10)
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == "wifi" and parts[1] == "connected":
            return True
    return False


def active_wifi_ssid():
    rc, out, err = run(["nmcli", "-t", "-f", "active,ssid", "device", "wifi"], timeout=10)
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == "yes":
            return parts[1]
    return ""


def read_current_config():
    """Best-effort read of the live config, for pre-filling the wizard when
    it's reopened via kiosk-reconfigure (see build/scripts/kiosk-reconfigure.sh).
    Never includes the Wi-Fi password - that's handled separately by the
    "keep current Wi-Fi" checkbox instead of being read back."""
    result = {
        "device_name": "",
        "dashboard_url": "",
        "screensaver_url": "",
        "xscreensaver": False,
        "rotation": "normal",
        "touch_device": "",
        "brightness_min": 10,
        "brightness_max": 100,
        "screensaver_timeout": 300,
        "dpms_timeout": 600,
        "mqtt": {"host": "", "port": 1883, "username": "", "password": ""},
        "sensors": {"lux": False, "c4001": False, "rcwl": False},
        "wifi_connected": wifi_connected(),
        "wifi_ssid": active_wifi_ssid(),
        "has_existing_config": CONFIG_PATH.exists(),
    }
    if not CONFIG_PATH.exists():
        return result

    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)

    def get(section, key, fallback=""):
        return cfg.get(section, key, fallback=fallback) if cfg.has_section(section) else fallback

    result["device_name"] = get("kiosk", "panel_name")
    result["dashboard_url"] = get("kiosk", "url")
    result["brightness_min"] = get("kiosk", "brightness_min", "10")
    result["brightness_max"] = get("kiosk", "brightness_max", "100")
    result["screensaver_url"] = get("screensaver", "url")
    result["xscreensaver"] = get("screensaver", "xscreensaver", "false").lower() == "true"
    result["screensaver_timeout"] = get("screensaver", "timeout_seconds", "300")
    result["dpms_timeout"] = get("screensaver", "dpms_off_seconds", "0")
    result["rotation"] = get("display", "rotation", "normal")
    result["touch_device"] = get("display", "touch_device")
    result["mqtt"] = {
        "host": get("mqtt", "host"),
        "port": get("mqtt", "port", "1883"),
        "username": get("mqtt", "username"),
        "password": get("mqtt", "password"),
    }
    result["sensors"] = {
        "lux": is_service_enabled(SENSOR_SERVICES["lux"]),
        "c4001": is_service_enabled(SENSOR_SERVICES["c4001"]),
        "rcwl": is_service_enabled(SENSOR_SERVICES["rcwl"]),
    }
    return result


def write_config(data):
    cfg = configparser.ConfigParser()
    if EXAMPLE_PATH.exists():
        cfg.read(EXAMPLE_PATH)
    elif CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)

    device_name = (data.get("device_name") or "").strip() or "Kiosk"
    slug = slugify(device_name)

    mqtt = data.get("mqtt") or {}
    mqtt_host = (mqtt.get("host") or "").strip()
    mqtt_enabled = bool(mqtt_host)

    for section in ("mqtt", "kiosk", "screensaver", "dpms", "brightness", "reboot", "c4001", "display"):
        if not cfg.has_section(section):
            cfg.add_section(section)

    cfg.set("mqtt", "host", mqtt_host)
    cfg.set("mqtt", "port", str(mqtt.get("port") or 1883))
    cfg.set("mqtt", "username", (mqtt.get("username") or "").strip())
    cfg.set("mqtt", "password", (mqtt.get("password") or "").strip())
    cfg.set("mqtt", "base_topic", f"kiosk/{slug}")

    cfg.set("kiosk", "url", (data.get("dashboard_url") or "").strip())
    cfg.set("kiosk", "panel_name", slug)
    cfg.set("kiosk", "brightness_min", str(data.get("brightness_min") or 10))
    cfg.set("kiosk", "brightness_max", str(data.get("brightness_max") or 100))

    ss_url = (data.get("screensaver_url") or "").strip()
    xss = bool(data.get("xscreensaver"))
    cfg.set("screensaver", "xscreensaver", "true" if xss else "false")
    cfg.set("screensaver", "timeout_seconds", str(data.get("screensaver_timeout") or 300))
    # 0 (default) = X never powers the screen down by itself; Home Assistant switches it over MQTT.
    dpms_off = str(data.get("dpms_timeout", "")).strip()
    cfg.set("screensaver", "dpms_off_seconds", dpms_off if dpms_off.isdigit() else "0")
    cfg.set("screensaver", "command_topic", "screensaver/set")
    cfg.set("screensaver", "state_topic", "screensaver/state")
    cfg.set("screensaver", "enabled", "true" if (xss and ss_url) else "false")
    cfg.set("screensaver", "url", ss_url)

    cfg.set("dpms", "command_topic", "dpms/set")
    cfg.set("dpms", "state_topic", "dpms/state")

    cfg.set("brightness", "command_topic", "brightness/set")
    cfg.set("brightness", "state_topic", "brightness/state")
    cfg.set("brightness", "min", "0")
    cfg.set("brightness", "max", "100")
    cfg.set("brightness", "display", "1")

    cfg.set("reboot", "command_topic", "reboot/set")

    cfg.set("c4001", "uart_device", "/dev/ttyAMA1")
    cfg.set("c4001", "baud", "9600")
    cfg.set("c4001", "hold_seconds", "20")
    cfg.set("c4001", "topic", "presence/state")
    cfg.set("c4001", "distance_topic", "presence/distance")

    cfg.set("display", "rotation", data.get("rotation") or "normal")
    cfg.set("display", "touch_device", str(data.get("touch_device") or ""))

    with open(CONFIG_PATH, "w") as f:
        cfg.write(f)
    CONFIG_PATH.chmod(0o600)

    sensors = data.get("sensors") or {}
    return mqtt_enabled, sensors, slug


# xrandr rotation name -> fbcon=rotate:N value (0=normal,1=90CW,2=180,3=270CW/90CCW)
FBCON_ROTATE = {"normal": "0", "right": "1", "inverted": "2", "left": "3"}


def apply_boot_rotation(rotation):
    """Keeps the text console / boot splash orientation in sync with the
    X/touch rotation - takes effect on the reboot that already happens after
    save."""
    value = FBCON_ROTATE.get(rotation, "0")
    run(["sudo", "-n", "/usr/local/sbin/set-boot-rotation.py", value], timeout=10)


SSH_KEY_RE = re.compile(r"^(ssh-(ed25519|rsa|dss)|ecdsa-sha2-\S+)\s+\S+")


def add_ssh_key(pubkey):
    pubkey = (pubkey or "").strip()
    if not pubkey:
        return
    if not SSH_KEY_RE.match(pubkey):
        log(f"Ignoring ssh_pubkey - doesn't look like a valid public key: {pubkey[:50]!r}")
        return
    ssh_dir = HOME / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    auth_keys = ssh_dir / "authorized_keys"
    existing = auth_keys.read_text() if auth_keys.exists() else ""
    if pubkey in existing:
        return
    with open(auth_keys, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(pubkey + "\n")
    auth_keys.chmod(0o600)
    log("Added SSH public key from wizard.")


def set_terminal_password(password):
    """Replaces the shipped default terminal/SSH password for the kiosk user.
    Piped via stdin to chpasswd, never as a command-line argument or logged -
    see run()'s input= handling."""
    password = password or ""
    if not password:
        return
    rc, out, err = run(["sudo", "-n", "chpasswd"], timeout=15, input=f"kiosk:{password}\n")
    if rc == 0:
        log("Terminal password changed from wizard.")
    else:
        log("Failed to change terminal password (see rc/stderr above).")


def xscreensaver_installed():
    return Path("/usr/bin/xscreensaver").exists()


def ensure_xscreensaver(wanted):
    """Installs xscreensaver when the user asked for the built-in screensaver and
    the image doesn't have it (it ships without). Needs internet. Returns
    (ok, message); never removes it again."""
    if not wanted or xscreensaver_installed():
        return True, "not needed" if not wanted else "already installed"
    rc, out, err = run(["sudo", "-n", INSTALL_XSCREENSAVER], timeout=900)
    ok = rc == 0 and xscreensaver_installed()
    log(f"xscreensaver install: rc={rc} {(err or out).strip()[:200]}")
    return ok, (out.strip() or err.strip() or ("installed" if ok else "install failed"))


def apply_service_state(mqtt_enabled, sensors, xscreensaver=False):
    for svc in CORE_MQTT_SERVICES:
        action = "enable" if mqtt_enabled else "disable"
        run(["sudo", "-n", "systemctl", action, "--now", svc], timeout=20)
    on = mqtt_enabled and xscreensaver and xscreensaver_installed()
    run(["sudo", "-n", "systemctl", "enable" if on else "disable", "--now", XSCREENSAVER_MQTT_SERVICE], timeout=20)

    for key, svc in SENSOR_SERVICES.items():
        on = mqtt_enabled and bool(sensors.get(key))
        run(["sudo", "-n", "systemctl", "enable" if on else "disable", "--now", svc], timeout=20)


def set_hostname(slug):
    """Hostname that survives reboots (cloud-init re-applies the boot partition's user-data each boot)."""
    name = slug[:63].strip("-") or "kiosk"
    rc, out, err = run(["sudo", "-n", SET_HOSTNAME, name], timeout=15)
    return rc == 0


def finish_and_reboot(slug):
    set_hostname(slug)
    PROVISIONED_MARKER.touch()
    log("Provisioning complete, rebooting.")
    run(["sudo", "-n", "systemctl", "reboot"], timeout=10)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log("http: " + (fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/":
                self._file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            elif path == "/style.css":
                self._file(STATIC_DIR / "style.css", "text/css; charset=utf-8")
            elif path == "/app.js":
                self._file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            elif path == "/api/wifi/scan":
                self._json({"networks": scan_wifi()})
            elif path == "/api/current":
                self._json(read_current_config())
            else:
                self.send_error(404)
        except Exception as e:
            log(f"GET {path} error: {e}")
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/wifi/connect":
                data = self._body_json()
                ok, msg = connect_wifi(data.get("ssid", ""), data.get("password", ""))
                self._json({"ok": ok, "message": msg})
            elif path == "/api/save":
                data = self._body_json()
                errors = []
                if not (data.get("device_name") or "").strip():
                    errors.append("Device name is required.")
                if not (data.get("dashboard_url") or "").strip():
                    errors.append("Dashboard URL is required.")
                new_password = data.get("terminal_password") or ""
                if new_password and len(new_password) < 8:
                    errors.append("New terminal password must be at least 8 characters.")
                if errors:
                    self._json({"ok": False, "errors": errors}, 400)
                    return

                if not data.get("skip_wifi"):
                    ssid = (data.get("wifi_ssid") or "").strip()
                    if not ssid:
                        self._json({"ok": False, "errors": [
                            "Choose a Wi-Fi network, or check 'Already connected (Ethernet)'."
                        ]}, 400)
                        return
                    ok, msg = connect_wifi(ssid, data.get("wifi_password", ""))
                    if not ok:
                        self._json({"ok": False, "errors": [f"Could not join '{ssid}': {msg}"]}, 400)
                        return

                if data.get("xscreensaver"):
                    ok, msg = ensure_xscreensaver(True)
                    if not ok:
                        # Not fatal: save everything else, leave the screensaver off.
                        log(f"Built-in screensaver requested but xscreensaver could not be installed: {msg}")
                        data["xscreensaver"] = False
                mqtt_enabled, sensors, slug = write_config(data)
                apply_service_state(mqtt_enabled, sensors, bool(data.get("xscreensaver")))
                apply_boot_rotation(data.get("rotation") or "normal")
                add_ssh_key(data.get("ssh_pubkey"))
                set_terminal_password(new_password)

                self._json({"ok": True})
                threading.Timer(2.0, finish_and_reboot, args=[slug]).start()
            else:
                self.send_error(404)
        except Exception as e:
            log(f"POST {path} error: {e}")
            self._json({"ok": False, "errors": [f"Internal error: {e}"]}, 500)


def main():
    if PROVISIONED_MARKER.exists():
        log("Already provisioned; wizard should not have started. Exiting.")
        sys.exit(0)
    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
    log("Wizard listening on 127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
