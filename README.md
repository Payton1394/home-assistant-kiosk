# Home Assistant Kiosk

A deployable Raspberry Pi image for a touchscreen Home Assistant kiosk. Flash it, boot it, walk through a first-boot setup wizard on the screen itself, and it's running your dashboard — no SSH required for basic setup.

Originally built as a one-off for a kitchen wall display; this project genericizes that build into something anyone can flash and configure for their own home.

## Features

- Fullscreen Chromium kiosk pointed at any Home Assistant dashboard URL
- First-boot **setup wizard** (runs on the kiosk's own screen) for device name, Wi-Fi, dashboard URL, screen orientation, MQTT broker, screensaver, and sensors
- **On-screen keyboard** in the setup wizard (a dashboard-wide version was tried via a Chromium extension but caused a touchscreen-input regression in testing and has been reverted — see Known issues)
- Optional MQTT bridge services: brightness control, DPMS (screen on/off), screensaver control, reboot-on-command, temperature reporting, and live (no-reboot) control of dashboard URL / screensaver URL / screensaver timeout
- Optional sensor support: light/lux sensor, C4001 mmWave presence sensor (UART), RCWL-0516 presence sensor (GPIO) — each independently toggled in the wizard; see [HARDWARE.md](HARDWARE.md) for exact wiring/pinouts
- **[Home Assistant Kiosk Panel](custom_components/ha_kiosk_panel/)** — a companion HACS integration that auto-discovers kiosks over MQTT and exposes all of the above as entities (sensors, switches, an MPD media player, and text/number controls for the dashboard/screensaver settings) without hand-writing any MQTT YAML
- **Reconfigure without reflashing**: run `kiosk-reconfigure` over SSH or the local terminal, or press "Rearm Setup Wizard" in the `ha_kiosk_panel` integration, to drop back into the setup wizard and change any setting
- **Animated boot splash** that covers the entire boot sequence (kernel/systemd console output suppressed via `cmdline.txt`) so nothing but the logo and a spinner is ever visible, correctly centered and oriented for whichever screen rotation is configured
- Wi-Fi watchdog (auto-recovers a dropped connection) and network logging
- Auto-expands to fill whatever size SD card it's flashed to (image ships shrunk small for a fast download)

## Quick start

1. Flash `ha-kiosk-generic.img` (or the `.img.xz` release) to an SD card.
2. Boot the Pi with a display (and touchscreen, if you have one) attached.
3. The setup wizard appears automatically. Fill in:
   - **Device name** (e.g. "Kitchen")
   - **Wi-Fi** (scans nearby networks; skip if using Ethernet or already connected)
   - **Dashboard URL** (your Home Assistant dashboard)
   - Optional: screensaver URL, MQTT broker + credentials, sensors you have wired up (see [HARDWARE.md](HARDWARE.md) for wiring before enabling these), an SSH public key for remote access
4. Save — the Pi reboots into your dashboard.

To change settings later, SSH in (if you added a key in step 3) or use a local terminal and run:

```bash
kiosk-reconfigure
```

This drops it back into the wizard (pre-filled with your current settings) on next reboot — no reflashing needed.

## What's inside

Not a Home Assistant install — this is a kiosk *client* (Chromium fullscreen) plus a set of small MQTT-bridge services that expose the physical display and any attached sensors as MQTT topics, so Home Assistant (or anything else) can read/control them. See [ANALYSIS.md](ANALYSIS.md) for the full architecture breakdown of the original prototype this was built from.

## Home Assistant integration (HACS)

`custom_components/ha_kiosk_panel/` is a companion integration that turns each kiosk's MQTT topics into real entities instead of hand-written MQTT YAML. Once installed via HACS (as a custom repository pointing at this repo, until it's submitted to the default HACS store):

- Kiosks with `kiosk-config-mqtt.service` running are **auto-discovered** — HA will prompt to add them once they publish their retained identity message.
- Each kiosk becomes one HA device with: CPU temperature, ambient lux, and presence-distance sensors; a presence binary sensor; brightness and screensaver-timeout numbers; display-power and screensaver-active switches; a reboot button; live-editable dashboard-URL and screensaver-URL text fields; and an MPD media player.

See the [integration README](custom_components/ha_kiosk_panel/README.md) for the full entity list and the exact MQTT topic contract it expects from the image.

## Repository layout

```
build/
  build-image.sh          - strips personal data, installs the wizard, patches kiosk.sh
  kiosk_config.ini.example - generic config template (wizard fills this in)
  setup_wizard/            - the first-boot wizard (Python stdlib server + HTML/CSS/JS)
  keyboard_extension/      - Chromium extension: on-screen keyboard on every page (wizard + dashboard)
  systemd/                 - new unit files (wizard, rootfs auto-expand, SSH host key regen, config MQTT bridge)
  scripts/                 - kiosk.sh (patched), expand-rootfs.sh, kiosk-reconfigure.sh, shrink-image.sh, kiosk_config_mqtt.py
  sudoers.d/                - narrowly-scoped passwordless sudo for the wizard and the config MQTT bridge
custom_components/
  ha_kiosk_panel/          - companion HACS integration (see above)
ANALYSIS.md                - full teardown of the original prototype image
HARDWARE.md                 - optional sensor wiring/pinouts (lux, C4001, RCWL-0516)
README.md                  - this file
```

## Security notes

- **Default login**: the `kiosk` user ships with the password `ChangeMe-Kiosk1!` for local terminal/SSH access — set your own during first-boot setup (wizard step 7, "Remote access") or later via `kiosk-reconfigure`. Change this before the device touches any network you care about.
- No SSH keys, Wi-Fi passwords, or MQTT credentials are baked into the image — everything is entered fresh through the wizard on first boot.
- The wizard's local HTTP server binds to `127.0.0.1` only; it's reachable exclusively from the kiosk's own Chromium on the kiosk's own screen, never over the network.
- SSH access is opt-in: paste a public key into the wizard's "Remote access" section, or manage `~/.ssh/authorized_keys` yourself.
- The `kiosk` user has a narrowly-scoped `sudoers.d` rule (Wi-Fi, hostname, specific systemd units, reboot, changing the terminal password) rather than blanket sudo — see `build/sudoers.d/kiosk-wizard` for the exact rule and rationale.

## Known issues

- None currently tracked — the dashboard-wide keyboard extension was re-enabled after root-causing the earlier touchscreen regression to an unrelated hardware power issue (see Status below and [ANALYSIS.md](ANALYSIS.md)).

## Status

- [x] Full SD card image captured
- [x] Image analysis — [ANALYSIS.md](ANALYSIS.md)
- [x] Setup wizard built (Wi-Fi, MQTT, sensors, SSH key, reconfigure-without-reflash)
- [x] Config genericization script written and run — `ha-kiosk-generic.img`
- [x] On-screen keyboard everywhere — the wizard's own built-in keyboard, plus a Chromium extension (`build/keyboard_extension/`) injecting the same keyboard into the live Home Assistant dashboard (excluded from the wizard's own page to avoid a double-keyboard conflict)
- [x] Image shrunk (29.8GB &rarr; ~8.1GB) with auto-expand-on-first-boot, verified clean via `e2fsck` plus a full personal-data grep sweep
- [x] First real-hardware test pass — found and fixed: `iwd`'s separate saved-Wi-Fi store, on-screen keyboard sizing/missing symbols, no keyboard on the live dashboard, and the prototype's real login password still present in `/etc/shadow`
- [x] Second real-hardware test pass — found a severe regression: touchscreen input stopped responding entirely. Initially misattributed to the dashboard keyboard's Chromium extension flags (reverted) and a real-but-unrelated screensaver-script bug (fixed: `webscreensaver-wrapper.sh` no longer exits early, avoiding an xscreensaver crash-loop). Touch was still broken after both — true root cause found via SSH diagnostics: the touchscreen (Waveshare 8" capacitive, needs 5V/3A) was browning out over USB, a hardware power issue with no software fix. The Chromium extension was likely never at fault; re-enabled.
- [x] Same-day follow-up — with the physical connection resolved, found and fixed a second real bug: rotating the display in the wizard didn't rotate touch input (blank `touch_device` silently skipped the coordinate-transform matrix) — now auto-detects the touch device via `xinput`. Also added: console/TTY rotation (`fbcon=rotate:N` set dynamically in `cmdline.txt`) and boot-splash rotation (4 pre-rotated image variants picked at boot) so every layer — touch, console, splash, and the dashboard — rotates together.
- [ ] **Another real-hardware test pass** to confirm touch alignment, console/splash rotation, and the dashboard keyboard all work together
- [ ] Packaging for GitHub release

## Future ideas

### Remote/OTA updates for already-deployed kiosks

Not implemented. Notes for whoever picks this up:

**Why it's not just "flash over SSH"**: a kiosk is booted from and actively running on the same SD card you'd be updating - `dd`-ing a new image onto that disk out from under the live, mounted root filesystem corrupts it. Real OTA needs one of:

- **A/B partition scheme** (Chrome OS/many embedded systems' approach): two root partitions, the update writes to the currently-inactive one, a bootloader flag flips to it on next boot, with rollback if the new one fails to boot. Most robust, but a genuine re-architecture — partition layout, boot flow, updater tooling — not a small addition.
- **In-place file-sync updates**: most of what actually changes release-to-release in this project is application-layer (wizard, MQTT bridge scripts, splash assets, systemd units) rather than the base OS/kernel. A lighter mechanism - a new MQTT command topic (`<base>/update/set`, matching the existing `reboot`/`refresh`/`rearm_wizard` pattern already in `kiosk_config_mqtt.py`) that pulls a versioned bundle from a GitHub release and applies it - would cover the common case without needing full A/B partitioning. Doesn't help if a future change needs a different base OS/kernel/partition layout.
- **Hybrid**: file-sync for routine updates, full reflash (physical) reserved for changes that touch the base OS itself.

Either approach needs: a way to know what version a kiosk is running (`kiosk_config_mqtt.py`'s existing `SW_VERSION` constant, already published in its identity payload, is the natural anchor), integrity/signature verification if pulling from anywhere over the network, and a rollback/backup story if an update leaves a kiosk half-updated. Also worth accounting for: kiosks drift from the shipped baseline over time (wizard-entered config, any live SSH patching like this session did on the test kiosk) - an updater needs to touch only its own known-managed files, not stomp on that.

This session's four production kiosks (kitchen, Lulu's room, playroom, family room) predate this whole generic-image project and are running a meaningfully different, older setup - not something either update path above could safely reach today regardless. They'd need the manual reflash-in-hand treatment until/unless brought onto a shared baseline first.
