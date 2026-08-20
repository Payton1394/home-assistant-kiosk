# Home Assistant Kiosk Panel

A HACS integration for [Home Assistant Kiosk](../../README.md) devices. Turns each kiosk's MQTT topics into real entities — no manual MQTT sensor/switch YAML required.

## Requirements

- An MQTT broker configured in Home Assistant (the core `mqtt` integration).
- A kiosk running `kiosk-config-mqtt.service` (ships with the image, enabled by the setup wizard whenever an MQTT broker is configured). This is what publishes the retained identity message auto-discovery relies on, and what listens for dashboard/screensaver-setting changes.
- MPD reachable from Home Assistant on the kiosk's IP, port 6600 by default (also ships with the image).

## Adding a kiosk

- **Automatic**: once a kiosk is online with a broker configured, Home Assistant will show a "Kiosk Panel discovered" notification. Confirm it, optionally correcting the IP address.
- **Manual**: *Settings → Devices & Services → Add Integration → Home Assistant Kiosk Panel*. You'll need the kiosk's MQTT base topic (shown in its setup wizard, e.g. `kiosk/kitchen`) and its IP address.

If the kiosk's IP changes later (e.g. a DHCP lease renewal), fix it via the integration's *Configure* option rather than re-adding it.

## Entities

| Entity | Type | MQTT topic(s) (under `<base_topic>/`) |
|---|---|---|
| CPU Temperature | sensor | `cpu_temp` |
| Ambient Light | sensor | `lux/state` |
| Presence Distance *(disabled by default)* | sensor | `presence/distance` |
| Presence | binary_sensor | `presence/state` or `presence` |
| Brightness | number | `brightness/set` / `brightness/state` |
| Screensaver Timeout | number | `screensaver_timeout/set` / `screensaver_timeout/state` |
| Display Power | switch | `dpms/set` / `dpms/state` |
| Screensaver Active | switch | `screensaver/set` / `screensaver/state` |
| Reboot | button | `reboot/set` |
| Dashboard URL | text | `dashboard_url/set` / `dashboard_url/state` |
| Screensaver URL | text | `screensaver_url/set` / `screensaver_url/state` |
| Media Player | media_player | MPD protocol, direct TCP (not MQTT) |

Availability for every entity follows `<base_topic>/availability` (`online`/`offline`, published as an MQTT LWT so a kiosk going offline is reflected immediately).

Not every kiosk has every sensor wired up (lux, presence) — those entities will simply stay `unknown` if the corresponding hardware/service isn't enabled on that kiosk.
