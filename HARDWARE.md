# Optional sensor wiring

All three sensors are optional — the kiosk works fine with none of them. Each is independently toggled in the setup wizard (or later via `kiosk-reconfigure`), and each has its own MQTT bridge service that only runs if you enable it. The GPIO/I2C/UART overlays these need are already enabled in `config.txt` on the shipped image, so wiring is the only extra step.

Pin numbers below are **physical header pin numbers** (1–40), with the BCM GPIO number in parentheses, matching the standard 40-pin header.

## Ambient light sensor — VEML7700 (recommended) or BH1750

Either sensor works; `kiosk_lux_mqtt.py` uses whichever answers on I2C bus 1. Used for lux-based brightness automations.

- **VEML7700** (Adafruit #4162), address `0x10`. Reads down to about 0.004 lx, so it can tell a dim room from a dark one, and
  auto-ranges up to bright daylight. Recommended.
- **BH1750** (GY-302 breakout), address `0x23`. Bottoms out around 1 lx, so in a dim room it reads 0.

Both are wired the same way:

| Sensor pin | Connect to | Pi pin |
|---|---|---|
| VIN / VCC | 3.3V | Pin 1 |
| GND | Ground | Pin 6 (or any GND) |
| SDA | I2C1 SDA (GPIO2) | Pin 3 |
| SCL | I2C1 SCL (GPIO3) | Pin 5 |

`dtparam=i2c_arm=on` is already set in `config.txt`. After wiring, confirm the Pi sees it with `i2cdetect -y 1`: a device at
`0x10` (VEML7700) or `0x23` (BH1750). The light level is published to `<base_topic>/lux/state` when it changes by 3 % or
0.05 lx, and at least once a minute; `<base_topic>/lux/attributes` says which sensor it is.

## Presence — C4001 mmWave (UART, speed/distance-capable)

UART, `/dev/ttyAMA1` at 9600 baud (enabled via `dtoverlay=uart1-pi5` in `config.txt`, already present on the image). This is the sensor the presence-distance entity depends on — RCWL-0516 (below) reports on/off only, not distance.

| Sensor pin | Connect to | Pi pin |
|---|---|---|
| VCC | Check your module's rating (commonly 5V) | Pin 2 or 4 |
| GND | Ground | Pin 6 (or any GND) |
| TX | Pi RX1 — GPIO1 | Pin 28 |
| RX | Pi TX1 — GPIO0 | Pin 27 |

TX/RX are crossed: the sensor's TX goes to the Pi's RX and vice versa. `uart1-pi5` on the Pi 5 puts UART1 on GPIO0/1 (the pins usually reserved for HAT ID EEPROM — that's expected and fine here, this image doesn't use HAT ID detection).

Detection range/sensitivity is tunable per-device via `c4001_tune.py` (bundled on the image) — useful if a kiosk is in a small room and the default factory range triggers on motion from an adjacent room.

## Presence — RCWL-0516 (GPIO, on/off only)

Simple radar motion sensor, digital output, read via `/dev/gpiochip0` line offset 14 (which is BCM GPIO23 — the Pi 5's RP1 GPIO chip doesn't number lines 1:1 with BCM numbers, so "line 14" and "GPIO23" both correctly refer to the same physical pin, just from different tools).

| Sensor pin | Connect to | Pi pin |
|---|---|---|
| VIN | 5V | Pin 2 or 4 |
| GND | Ground | Pin 6 (or any GND) |
| OUT | GPIO23 | Pin 16 |

RCWL-0516's `OUT` is already 3.3V logic (safe to wire directly to the Pi's GPIO, no level shifting needed) despite VIN wanting 5V. It's electrically noisy and self-triggers briefly on power-up — the bridge script (`rcwl_presence.py`) debounces this (0.3s to confirm presence, 2s to confirm absence) so this is already handled, not something you need to account for in wiring.

**Pick C4001 or RCWL-0516, not both**, unless you specifically want both a distance-capable sensor and a cheaper backup — the setup wizard lets you enable either or both independently, and the `ha_kiosk_panel` integration's presence binary sensor listens for either one automatically.
