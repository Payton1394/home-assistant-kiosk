#!/usr/bin/env python3
"""Home Assistant Kiosk - apply a setup file made with the web setup wizard.

The wizard (https://payton1394.github.io/home-assistant-kiosk/wizard/) runs in
the browser and downloads kiosk-setup.json. Copy that file onto the SD card's
boot partition (the drive called "bootfs") after flashing; on the next boot this
script applies it exactly as the on-screen first-boot wizard would (it reuses
setup_wizard/server.py), deletes the file because it holds passwords, writes a
password-free kiosk-setup-result.txt next to where it was, and reboots into the
dashboard. Dropping a new file later re-configures the kiosk the same way.

If something fails (bad file, Wi-Fi won't join) nothing is marked provisioned,
the file is left for the next boot, and the on-screen wizard still works.
Runs as root from kiosk-import-setup.service.
"""
import importlib.util
import json
import os
import pwd
import shutil
import sys
import time
from pathlib import Path

BOOT = Path("/boot/firmware")
SETUP = BOOT / "kiosk-setup.json"
RESULT = BOOT / "kiosk-setup-result.txt"
WIZARD = Path("/home/kiosk/setup_wizard/server.py")
FORMAT = "ha-kiosk-setup"
ROTATIONS = {"normal", "right", "left", "inverted"}


def load_wizard():
    spec = importlib.util.spec_from_file_location("kiosk_setup_wizard", WIZARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)   # server.py only defines things; main() is guarded
    return mod


def result(lines):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        RESULT.write_text(f"Home Assistant Kiosk setup - {stamp}\n" + "\n".join(lines) + "\n")
    except OSError:
        pass


def validate(d):
    errors = []
    if d.get("format") != FORMAT:
        errors.append(f'Not a kiosk setup file (expected "format": "{FORMAT}").')
    if not (d.get("device_name") or "").strip():
        errors.append("Device name is required.")
    if not (d.get("dashboard_url") or "").strip().startswith(("http://", "https://")):
        errors.append("Dashboard URL must start with http:// or https://.")
    if (d.get("rotation") or "normal") not in ROTATIONS:
        errors.append("Rotation must be normal, right, left or inverted.")
    pw = d.get("terminal_password") or ""
    if pw and len(pw) < 8:
        errors.append("New terminal password must be at least 8 characters.")
    if not d.get("skip_wifi") and not (d.get("wifi_ssid") or "").strip():
        errors.append("Wi-Fi network name is missing (or set skip_wifi for Ethernet).")
    return errors


def join_wifi(w, d):
    """Join the network, retrying while the radio finishes its first scan after boot."""
    ssid = d["wifi_ssid"].strip()
    password = d.get("wifi_password") or ""
    country = (d.get("wifi_country") or "").strip().upper()
    if len(country) == 2 and shutil.which("raspi-config"):
        w.run(["raspi-config", "nonint", "do_wifi_country", country], timeout=30)
    w.run(["nmcli", "radio", "wifi", "on"], timeout=15)
    msg = "not tried"
    for attempt in range(8):
        w.run(["nmcli", "device", "wifi", "rescan"], timeout=15)
        time.sleep(3)
        ok, msg = w.connect_wifi(ssid, password, hidden=bool(d.get("wifi_hidden")))
        if ok:
            return True, msg
        time.sleep(10)
    return False, msg


def chown_kiosk(*paths):
    """Files the wizard code writes must belong to the kiosk user (this script runs as root)."""
    pw = pwd.getpwnam("kiosk")
    for p in map(Path, paths):
        if not p.exists():
            continue
        os.chown(p, pw.pw_uid, pw.pw_gid)
        if p.is_dir():
            for root, dirs, files in os.walk(p):
                for name in dirs + files:
                    os.chown(os.path.join(root, name), pw.pw_uid, pw.pw_gid)


def shred(path):
    try:
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(b"\0" * size)
            f.flush()
            os.fsync(f.fileno())
        path.unlink()
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass


def main():
    if not SETUP.exists():
        return 0
    try:
        data = json.loads(SETUP.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        result([f"FAILED: kiosk-setup.json could not be read ({e}).", "Make a new file with the web wizard."])
        return 1
    errors = validate(data)
    if errors:
        result(["FAILED: the setup file has problems:"] + [f"- {e}" for e in errors])
        return 1

    w = load_wizard()
    lines = []
    if data.get("skip_wifi"):
        lines.append("Network: Ethernet (Wi-Fi skipped).")
    else:
        ok, msg = join_wifi(w, data)
        if not ok:
            result([f"FAILED: could not join Wi-Fi '{data['wifi_ssid']}': {msg}",
                    "Check the network name and password, or use the on-screen wizard.",
                    "The setup file was left on the card and will be tried again at the next boot."])
            return 1
        lines.append(f"Wi-Fi: joined '{data['wifi_ssid']}'.")

    # xscreensaver is not in the image: install it only when the built-in screensaver was ticked.
    if data.get("xscreensaver"):
        ok, msg = w.ensure_xscreensaver(True)
        if ok:
            lines.append("Screensaver: built-in screensaver (xscreensaver) installed and on.")
        else:
            data["xscreensaver"] = False
            lines.append(f"Screensaver: xscreensaver could not be installed ({msg}); screensaver left off.")
    else:
        lines.append("Screensaver: off (xscreensaver not installed).")

    mqtt_enabled, sensors, slug = w.write_config(data)
    w.apply_service_state(mqtt_enabled, sensors, bool(data.get("xscreensaver")))
    w.apply_boot_rotation(data.get("rotation") or "normal")
    w.add_ssh_key(data.get("ssh_pubkey"))
    w.set_terminal_password(data.get("terminal_password") or "")
    chown_kiosk(w.CONFIG_PATH, w.HOME / ".ssh", w.LOG_PATH)

    lines += [f"Device: {data['device_name'].strip()} (hostname {slug}, MQTT topic kiosk/{slug}).",
              f"Dashboard: {data['dashboard_url'].strip()}",
              f"MQTT: {'on' if mqtt_enabled else 'off'}; sensors: " + (", ".join(k for k, v in (sensors or {}).items() if v) or "none"),
              f"Rotation: {data.get('rotation') or 'normal'}",
              "SSH key: " + ("added" if (data.get("ssh_pubkey") or "").strip() else "none"),
              "Terminal password: " + ("changed" if data.get("terminal_password") else "unchanged (default)"),
              "OK: the setup file was applied and deleted. The kiosk restarted into the dashboard."]
    result(lines)
    shred(SETUP)
    # Same finish as the on-screen wizard (finish_and_reboot), with the marker owned by the kiosk user.
    w.set_hostname(slug)
    w.PROVISIONED_MARKER.touch()
    chown_kiosk(w.PROVISIONED_MARKER)
    w.log(f"Applied {SETUP} (web setup wizard) for {slug}; rebooting.")
    w.run(["systemctl", "reboot"], timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
