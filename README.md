# Home Assistant Kiosk

A deployable Raspberry Pi image for a touchscreen Home Assistant dashboard kiosk. Flash it, boot it, walk through a first-boot setup wizard **on the screen itself** — no SSH, no keyboard/mouse (beyond the touchscreen) required — and it's running your dashboard. An optional companion [Home Assistant integration](#home-assistant-integration-hacs) turns every kiosk into real HA entities instead of hand-written MQTT YAML.

Originally built as a one-off for a kitchen wall display; this project genericizes that build into something anyone can flash and configure for their own home.

## Features

- Fullscreen Chromium kiosk pointed at any Home Assistant dashboard URL
- First-boot **setup wizard** (runs on the kiosk's own screen, with an on-screen keyboard) for device name, Wi-Fi, dashboard URL, screen orientation, MQTT broker, screensaver, and sensors
- **Animated boot splash** covering the entire boot sequence (kernel/console text is suppressed) — correctly centered and oriented for whichever rotation you configure, and scaled to fit your screen's actual resolution without stretching, whatever its aspect ratio
- Optional MQTT bridge services: brightness control, DPMS (screen on/off), screensaver control, reboot/refresh-on-command, temperature reporting, and live (no-reboot) control of dashboard URL / screensaver URL / screensaver timeout
- Optional sensor support: ambient light, mmWave presence (with distance), and radar presence — see [Optional sensors](#optional-sensors) below
- **[Home Assistant Kiosk Panel](custom_components/ha_kiosk_panel/)**, a companion HACS integration: auto-discovers kiosks over MQTT and exposes everything above as real entities — sensors, switches, buttons, an MPD media player, and live text/number controls for the dashboard and screensaver settings
- **Reconfigure without reflashing**: run `kiosk-reconfigure` over SSH/local terminal, or press "Rearm Setup Wizard" in the HA integration, to drop back into the setup wizard (pre-filled with current settings) and change anything
- Auto-negotiates your display's native resolution (no hardcoded video mode) and auto-detects the touchscreen device, so rotation and touch alignment work correctly regardless of which panel you use
- Wi-Fi watchdog (auto-recovers a dropped connection)
- Auto-expands to fill whatever size SD card it's flashed to (the image itself ships shrunk down for a fast download)

## Which Raspberry Pi models work

**Confirmed / primary target: Raspberry Pi 5.** This is what the image is built and tested against. If you're buying new hardware for this, get a Pi 5.

**Likely fine, not fully tested: Raspberry Pi 4B.** The kiosk itself (Chromium, the setup wizard, the MQTT bridge scripts, MPD) is plain Python/bash with nothing Pi-5-specific, and the I2C-based lux sensor should work unchanged. However, two of the optional sensor integrations *are* Pi 5-specific as documented:
- The C4001 mmWave sensor's UART is enabled via a `uart1-pi5`-named `dtoverlay` in `cmdline.txt` — Pi 4 uses different overlay names (`uart2`/`uart3`/etc.), so this would need adjusting.
- The RCWL-0516 wiring in [HARDWARE.md](HARDWARE.md) references a GPIO-chip line-offset quirk specific to the Pi 5's RP1 southbridge — on a Pi 4 the line offset equals the BCM number directly, no lookup needed, but the script's hardcoded offset would need updating.

If you're on a Pi 4 and stick to the display + lux sensor (skip C4001/RCWL, or wire them up and adjust those two things yourself), it should work fine.

**Not recommended: Pi 3B/3B+, Pi Zero 2 W, or older.** Untested, and Chromium running a live dashboard plus MPD plus sensor polling is a real workload — expect it to struggle even if it technically boots.

## Hardware you'll need

- **A Raspberry Pi 5** (4GB or 8GB) and its **official 27W USB-C power supply**. Don't skimp on the power supply — an underpowered or non-PD supply causes real, hard-to-diagnose problems (this project's own hardware testing found a touchscreen intermittently brownout-disconnecting from USB purely due to insufficient power).
- **A microSD card**, 16GB minimum, 32GB+ recommended (the image auto-expands to fill whatever you use).
- **A touchscreen display.** Any HDMI display works for the dashboard itself (resolution is auto-negotiated, no hardcoding); for touch input you'll want a USB or DSI capacitive touchscreen. Two concrete options this project has direct experience with:
  - **[Waveshare 8DP-CAPLCD](https://www.waveshare.com/8dp-caplcd.htm)** — 8", 1280×800, HDMI + USB touch. This is what the current hardware testing was done against. Needs a solid 5V/3A+ power source for the panel itself, separate from the Pi's own supply — this is the exact panel that suffered the USB brownout issue mentioned above when underpowered.
  - **[Waveshare 15.6" HDMI LCD (H)](https://www.waveshare.com/15.6inch-hdmi-lcd.htm)** — 15.6", 1920×1080, HDMI + USB touch, wants its own 12V power adapter.
  - Waveshare also makes 10.1" and other in-between sizes if you want something different — any of them should work the same way (auto-negotiated resolution, no per-model config needed) as long as it's HDMI + USB (or DSI) capacitive touch.
- **Optional sensors** — see below.

### Optional sensors

Each is independently toggled in the setup wizard, and each just needs an MQTT broker to report to — no hardware sensor is required for the kiosk to work.

| Sensor | What it adds | Interface |
|---|---|---|
| BH1750 ambient light (GY-302 breakout) | Lux reading, for lux-based brightness automations | I2C |
| C4001 mmWave presence | Presence + distance | UART (Pi 5 only as shipped — see above) |
| RCWL-0516 radar presence | Presence (on/off only, no distance) | GPIO (Pi 5 line-offset as shipped — see above) |

Full wiring diagrams, physical pin numbers, and the exact `config.txt` overlays each one needs are in **[HARDWARE.md](HARDWARE.md)** — read that before wiring anything up, wrong pins can damage hardware.

## Step-by-step setup

### 1. Flash the image

1. Download `ha-kiosk-generic.img.xz` from this repo's [Releases](../../releases) page.
2. Flash it to your microSD card with [Raspberry Pi Imager](https://www.raspberrypi.com/software/) (**Choose OS → Use custom**, point it at the downloaded file) — this is the recommended tool; it verifies the write and handles `.xz` decompression automatically. Rufus and Win32DiskImager also work if you'd rather use something lighter than Etcher.
3. Insert the card into the Pi, connect your display (and touchscreen, if using one) and power, and boot.

### 2. Walk through the on-screen setup wizard

The wizard appears automatically on first boot — no SSH, no external keyboard/mouse needed, it has its own on-screen keyboard. It's eight steps, the last two collapsed by default:

1. **Device** — a name (e.g. "Kitchen"). This becomes the hostname and the MQTT topic prefix (`kiosk/kitchen`).
2. **Wi-Fi** — scans nearby networks, or check "already connected" if you're on Ethernet.
3. **Dashboard** — the URL of the Home Assistant dashboard you want shown fullscreen.
4. **Screen orientation** — normal/right/left/inverted; handles display rotation, touch alignment, console, and the boot splash together.
5. **Screensaver** *(optional)* — a URL to show when idle (e.g. a photo slideshow server).
6. **MQTT & smart features** *(optional — leave the broker field blank to run as a plain browser kiosk)* — broker host/port/credentials, plus checkboxes for whichever optional sensors you've actually wired up (see [Optional sensors](#optional-sensors)).
7. **Remote access** — set a real SSH/terminal password (the image ships with a documented default, `ChangeMe-Kiosk1!` for user `kiosk`, worth changing before this touches a network you care about) and/or paste an SSH public key for passwordless access.
8. **Advanced** *(optional)* — touch input device override (auto-detected normally, only needed if that fails), brightness min/max, screensaver/screen-off timeouts.

Save, and the Pi reboots straight into your dashboard.

### 3. (Optional) Install the Home Assistant integration

If you enabled MQTT in step 6, add the companion integration so every kiosk shows up as real entities in HA instead of raw MQTT topics:

1. In HACS: **⋮ → Custom repositories**, add this repo's URL as an **Integration**. (Once this repo is accepted into the default HACS store, this manual step won't be needed.)
2. Install **Home Assistant Kiosk Panel**, restart Home Assistant.
3. Within about a minute, HA will show a **"Kiosk Panel discovered"** notification for each kiosk on your network with MQTT enabled — confirm it (optionally correcting the auto-detected IP).

See the [integration's own README](custom_components/ha_kiosk_panel/README.md) for the full entity list and requirements.

### 4. Changing settings later

No need to reflash for any of this:

- **Any setting**: SSH in (if you added a key) or use a local terminal and run `kiosk-reconfigure` — drops you back into the same wizard, pre-filled with current settings, on next reboot. Or press **Rearm Setup Wizard** in the HA integration to do the same thing without SSH at all.
- **Dashboard URL, screensaver URL, or screensaver timeout specifically**: change these live, no reboot, via the integration's text/number entities, or by publishing to the kiosk's `dashboard_url/set` / `screensaver_url/set` / `screensaver_timeout/set` MQTT topics directly.

## Configuration reference

The wizard writes everything to `~/kiosk_config.ini` on the kiosk (`build/kiosk_config.ini.example` in this repo is the generic template it starts from). You generally shouldn't need to hand-edit this — the wizard covers every field — but for reference:

| Section | Key | Meaning |
|---|---|---|
| `[mqtt]` | `host`, `port`, `username`, `password` | Broker connection. Blank host = MQTT disabled entirely. |
| `[mqtt]` | `base_topic` | MQTT topic prefix, e.g. `kiosk/kitchen`. Auto-derived from the device name. |
| `[kiosk]` | `url` | The dashboard URL shown fullscreen. |
| `[kiosk]` | `panel_name` | Slugified device name (hostname, MQTT topic). |
| `[kiosk]` | `brightness_min` / `brightness_max` | Clamp range for the brightness MQTT control (uses `ddcutil`, requires a DDC/CI-capable monitor). |
| `[screensaver]` | `url` | Screensaver page URL; blank disables it. |
| `[screensaver]` | `timeout_seconds` / `dpms_off_seconds` | Idle time before screensaver / before the display powers off entirely. |
| `[c4001]` | `uart_device`, `baud`, `hold_seconds` | mmWave sensor UART settings and presence hold time. |
| `[display]` | `rotation` | `normal` / `right` / `left` / `inverted`. |
| `[display]` | `touch_device` | Touch input override; leave blank for auto-detection. |

MQTT topics for live control (dashboard URL, screensaver URL/timeout, refresh, reboot, rearm-wizard, identity/availability) are fixed rather than ini-configurable — see the comment block in `build/kiosk_config.ini.example` or the [integration README](custom_components/ha_kiosk_panel/README.md)'s entity table for the exact topic names.

## What's inside

Not a Home Assistant install — this is a kiosk *client* (Chromium fullscreen) plus a set of small MQTT-bridge services that expose the physical display and any attached sensors as MQTT topics, so Home Assistant (or anything else) can read/control them. See [ANALYSIS.md](ANALYSIS.md) for the full architecture breakdown of the original prototype this was built from.

## Home Assistant integration (HACS)

`custom_components/ha_kiosk_panel/` is a companion integration that turns each kiosk's MQTT topics into real entities instead of hand-written MQTT YAML. See [Step 3](#3-optional-install-the-home-assistant-integration) above for installation, and the [integration's own README](custom_components/ha_kiosk_panel/README.md) for the full entity list and MQTT topic contract.

## Repository layout

```
build/
  build-image.sh           - strips personal data, installs the wizard, patches kiosk.sh, builds the splash
  kiosk_config.ini.example - generic config template (wizard fills this in)
  setup_wizard/             - the first-boot wizard (Python stdlib server + HTML/CSS/JS)
  keyboard_extension/       - Chromium extension: on-screen keyboard on every page (wizard + dashboard)
  systemd/                  - unit files (wizard, rootfs auto-expand, SSH host key regen, splash, config MQTT bridge)
  scripts/                  - kiosk.sh, expand-rootfs.sh, kiosk-reconfigure.sh, kiosk_config_mqtt.py, generate_splash.py
  assets/                   - source logo + spinner animation the boot splash is built from
  sudoers.d/                - narrowly-scoped passwordless sudo for the wizard and the config MQTT bridge
custom_components/
  ha_kiosk_panel/           - companion HACS integration (see above)
ANALYSIS.md                 - full teardown of the original prototype image
HARDWARE.md                 - optional sensor wiring/pinouts (lux, C4001, RCWL-0516)
README.md                   - this file
```

## Security notes

- **Default login**: the `kiosk` user ships with the password `ChangeMe-Kiosk1!` for local terminal/SSH access — set your own during first-boot setup (wizard step 7, "Remote access") or later via `kiosk-reconfigure`. Change this before the device touches any network you care about.
- No SSH keys, Wi-Fi passwords, or MQTT credentials are baked into the image — everything is entered fresh through the wizard on first boot.
- The wizard's local HTTP server binds to `127.0.0.1` only; it's reachable exclusively from the kiosk's own Chromium on the kiosk's own screen, never over the network.
- SSH access is opt-in: paste a public key into the wizard's "Remote access" section, or manage `~/.ssh/authorized_keys` yourself.
- The `kiosk` user has a narrowly-scoped `sudoers.d` rule (Wi-Fi, hostname, specific systemd units, reboot, changing the terminal password) rather than blanket sudo — see `build/sudoers.d/kiosk-wizard` for the exact rule and rationale.

## Known issues

- None currently tracked.

## Status

- [x] Full SD card image captured, analyzed, and genericized — [ANALYSIS.md](ANALYSIS.md)
- [x] Setup wizard (Wi-Fi, MQTT, sensors, SSH key, reconfigure-without-reflash)
- [x] On-screen keyboard everywhere (wizard + live dashboard)
- [x] Multiple real-hardware test passes — touch alignment, display rotation (console/splash/touch/dashboard together), resolution auto-negotiation, boot splash animation, all confirmed working
- [x] Companion HACS integration (`ha_kiosk_panel`) with MQTT auto-discovery, ghost-kiosk-free live discovery, and a full entity set
- [x] Published to GitHub with a compressed release image

## Future ideas

### Remote/OTA updates for already-deployed kiosks

Not implemented. Notes for whoever picks this up:

**Why it's not just "flash over SSH"**: a kiosk is booted from and actively running on the same SD card you'd be updating - `dd`-ing a new image onto that disk out from under the live, mounted root filesystem corrupts it. A true A/B partition scheme (two root partitions, update writes to the inactive one, bootloader flag flips on next boot, rollback if it fails) would sidestep that, but it's a genuine re-architecture - partition layout, boot flow, updater tooling - not a small addition, and probably overkill for how this project actually changes over time.

**Current direction**: skip full image-level OTA. Instead, ship each feature update as a downloadable package (e.g. a GitHub release tarball) that a user SSHes in and applies via an `apply-update` style script - the script drops in whatever new/changed scripts and systemd service units the release needs (same pattern as `kiosk-reconfigure` already uses for dropping back into the wizard, just generalized to "install these files, enable these units, restart these services"). Manual-but-scripted, not automatic - the user still initiates it, but doesn't need to hand-copy files or remember what changed.

Two pieces that pattern needs:
- **A defined package format** - versioned bundle (files + a manifest listing what changes: new/updated scripts, new systemd units to enable, services to restart) and the `apply-update` script that reads that manifest and applies it idempotently. Should be safe to re-run and should touch only its own known-managed files, never user config - kiosks drift from the shipped baseline over time (wizard-entered config, ad-hoc live SSH patches) and an updater must not stomp on that.
- **Version visibility from Home Assistant, no SSH required** - already built: `kiosk_config_mqtt.py` publishes a `sw_version` field in its `panel/state` identity payload, and the integration's **Software Version** sensor surfaces it - so a future update-package mechanism already has a version-tracking anchor to report against.
