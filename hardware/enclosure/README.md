# Kiosk frames

3D-printable wall frames for the two displays this project uses. These are the versions printed for the kiosks in the [README photos](../../README.md).

| Display | Frame | Overall size (mm) |
|---|---|---|
| Waveshare 15.6HP-CAPQLED | `15in_kiosk_frame_v30.stl` | 399.1 x 290.6 x 19.0 |
| [Waveshare 8DP-CAPLCD](https://www.waveshare.com/8dp-caplcd.htm) | `8in_kiosk_frame_v12.stl` | 219.2 x 170.7 x 12.0 |

**Printing:** printed in JLC3DP 9600 resin. Clamps were left unpainted.

**Mounting:** the frame sits flush in a drywall cutout, with magnets holding the screen. The Pi is taped to the back of the display. No electrical box is used. Follow your local electrical rules, and check for wiring and studs before cutting.

**The designs are specific to these parts.** They have openings for the sensors and audio hardware fitted to these kiosks: a C4001 mmWave sensor, a VEML7700 light sensor, a USB board, a speaker, and a ReSpeaker microphone. Check them against your own hardware and measure your display before printing.

## Clamps

Clamps hold the boards inside the frame, as shown in [clamp-guide.png](clamp-guide.png), viewed from the wall side. The guide was drawn for 15.6" frame v29, one version before the frame included here, so check it against v30 before assembly.

| Frame | Print | Holds | Screws |
|---|---|---|---|
| 15.6" | `15in_clamp_c4001_upper`, `_lower`: 1 each | C4001 | M2.6 x 10, 6 in total for the 15.6" clamps |
| 15.6" | `15in_clamp_rsl_top`, `_bottom`: 2 each | ReSpeaker Lite | |
| 8" | `8in_clamp_c4001_upper`, `_lower`: 1 each | C4001 | M2.6 x 6, 8 in total for the 8" clamps |
| 8" | `8in_clamp_mic`: 2 | Microphone | |
| 8" | `8in_clamp_usb_a`, `_b`: 2 each | USB board | |

Put a pad of about 1 mm foam tape under each foot of the USB and C4001 clamps.

**15.6" USB board:** 4 x M3 x 5 machine screws into 4 x M3 x 4 x 3 threaded inserts in the frame.

**VEML7700 on either frame:** 4 x M2 x 6 screws straight into the frame, with no clamp.
