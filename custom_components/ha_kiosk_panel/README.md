# Home Assistant Kiosk Panel

A HACS integration for [Home Assistant Kiosk](../../README.md) devices. Turns each kiosk's MQTT topics into real entities — no manual MQTT sensor/switch YAML required.

## Requirements

- An MQTT broker configured in Home Assistant (the core `mqtt` integration).
- A kiosk running `kiosk-config-mqtt.service` (ships with the image, enabled by the setup wizard whenever an MQTT broker is configured). This is what publishes the retained identity message auto-discovery relies on, and what listens for dashboard/screensaver-setting changes.
- MPD reachable from Home Assistant on the kiosk's IP, port 6600 by default (also ships with the image) — unless the media player plays through the dashboard page (see below).

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
| Media Player | media_player | MPD protocol, direct TCP (not MQTT) — or `media/set` / `media/state` with the *dashboard page* audio option |

Availability for every entity follows `<base_topic>/availability` (`online`/`offline`, published as an MQTT LWT so a kiosk going offline is reflected immediately).

## Media player: MPD or the dashboard page

*Configure* → **Audio player** picks what the Media Player entity drives:

- **MPD on the kiosk** (default): MPD's own protocol, straight to the kiosk's IP and MPD port.
- **The dashboard page**: for a kiosk running the Scarth Wall Panel dashboard (loaded with `?kiosk=<id>`) with MPD turned off.
  - Commands go out as JSON on `<base_topic>/media/set`: `play` (with a `url` and an optional `title`), `pause`, `resume`, `stop`, `volume` (`level`, 0–1), `mute` (`muted`) and `seek` (`position`).
  - The add-on plays them in the page, on the kiosk's own speaker, and reports on `<base_topic>/media/state`. That is retained JSON: `page`, `state`, `volume`, `muted`, `title`, `duration`, `position` and `at`.
  - Media-source items and TTS go out as Home Assistant paths (`/media/local/…`, `/api/…`), not as absolute URLs. The add-on serves the media folder itself and fetches `/api` through the Supervisor, so nothing leaves the host.
  - The entity is unavailable while the kiosk is offline, or while no dashboard page for it is connected.
  - Its **volume is the room's volume** and its **mute is the room's Do Not Disturb**. Both cover everything the panel plays, and the panel's Sound button changes the same settings.
  - Do Not Disturb keeps chimes, the doorbell and announcements quiet. Alarms, intercom calls made to that room and doorbell Talk still come through.
  - `play_media` also takes `extra: {alarm: true}`, which plays through Do Not Disturb at full volume, and `extra: {volume: 0.8}`, which gives that one sound its own level instead of the room's.
  - Media browsing (audio only) works from the entity's card.

It is the same entity either way, so automations don't change when a kiosk switches.

Not every kiosk has every sensor wired up (lux, presence) — those entities will simply stay `unknown` if the corresponding hardware/service isn't enabled on that kiosk.
