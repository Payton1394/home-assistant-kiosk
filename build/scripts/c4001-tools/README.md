# C4001 mmWave sensor tools

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
