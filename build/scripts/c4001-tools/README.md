# C4001 mmWave sensor tools

**Tuning from Home Assistant (no tools needed):** since 2026-10-17 the sensor's presence-mode settings are Home Assistant number entities on each kiosk's device, from the `ha_kiosk_panel` integration (0.4.0+); without the integration, `[c4001] ha_discovery = true` makes `c4001_presence_mqtt.py` publish them by MQTT discovery instead (device "<Room> Kiosk Presence"; name from `[c4001] ha_name`, else the kiosk's `panel_name`): Detection distance, Trigger distance, Trigger sensitivity, Hold sensitivity, Confirmation delay, Clear after. A change arrives on `<base>/presence/tuning/<key>/set`; the service stops the sensor, sends the setting, `saveConfig`s it, reads every setting back and starts it again, then publishes them as JSON on `<base>/presence/tuning/state` (availability on `<base>/presence/tuning/available`). Commands follow DFRobot's C4001 manual: `setRange <min m> <max m>`, `setTrigRange <m>`, `setSensitivity <hold> <trigger>` (hold first; the DFRobot libraries' getters read them the other way round), `setLatency <confirm s> <clear s>`. `[c4001] tuning = false` turns it off. The tools below are still there for one-off work (they need the service stopped).

Manual command-line utilities for configuring/debugging a DFRobot C4001 mmWave presence sensor over its UART, separate from `c4001_presence_mqtt.py` (the actual always-on service that publishes readings to MQTT). None of these run automatically - copy the one you need onto a kiosk and run it directly, with `c4001_presence.service` stopped first since it holds the serial port open:

```bash
sudo systemctl stop c4001_presence.service
python3 c4001_tune_presence_mode.py
sudo systemctl start c4001_presence.service
```

- **c4001_dump.py** - prints every line the sensor sends, decoded as text. Start here to see raw sensor output.
- **c4001_read.py** - prints raw bytes (hex) instead of decoded lines. Use if `c4001_dump.py` shows garbage (wrong baud rate, framing issue).
- **c4001_config.py** - one-shot: switches the sensor into speed/distance-measurement mode (`$DFDMD` output) and restarts it.
- **c4001_tune.py** - one-shot: sets a specific detection range/sensitivity example (30-150cm). Treat as a worked example to copy and adjust, not a generic tool.
- **c4001_tune_presence_mode.py** - one-shot: switches the sensor into dedicated presence-detection mode (`$DFHPD` output, no distance value) with a ~20ft range tuned in. Use when you want reliable presence with no need for distance readings.
- **c4001_adjust.py** - the general-purpose one: every tunable (range, sensitivities, timing, mode, UART baud) is a constant at the top of the file. Edit the constants, then run it.
