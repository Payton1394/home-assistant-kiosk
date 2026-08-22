#!/usr/bin/env python3
import time
import serial

# ========= USER CONFIG (TWEAK HERE) =========================================

PORT = "/dev/ttyAMA1"      # UART port for C4001 (e.g. /dev/ttyAMA1, /dev/serial0, /dev/ttyUSB0)
BAUD = 9600                # Current baud rate you talk to the sensor with

# --- Presence / range settings ---------------------------------------------

# Detection range (cm) – set your working zone
MIN_CM   = 50              # minimum detection distance (e.g. 50 cm)
MAX_CM   = 300             # maximum detection distance (e.g. 600 cm = 6 m)
TRIG_CM  = 300             # trigger distance (usually same as MAX_CM)

# Sensitivities 0–9 (higher = more sensitive)
TRIG_SENS = 3              # how easily it fires when something appears
KEEP_SENS = 3              # how easily it stays occupied once triggered

# Timing
TRIG_DELAY_01S = 30        # trigger delay: 30 * 0.01s = 0.30 s
KEEP_TIME_05S  = 20     # keep time: 120 * 0.5s = 60 s

# --- Working mode / sensor mode --------------------------------------------

# Working app: 0 = presence app, 1 = speed & distance app
RUN_APP_MODE = 1

# Sensor mode string (mapped to internal enums in examples)
# "exist" = presence (exist) mode, "speed" = speed mode
SENSOR_MODE = "speed"

# --- UART reconfiguration on the module itself -----------------------------

# If True, send setUart and save/reset so the module changes its baud.
# NOTE: After running this ONCE, you must change BAUD above to NEW_UART_BAUD.
CHANGE_UART   = False
NEW_UART_BAUD = 19200      # 4800–115200 allowed; default is 9600

# --- Advanced threshold / fretting (mainly for speed/distance use) ---------

# Use raw detection threshold config
USE_DETECT_THRES  = False
THRES_MIN_CM      = 30     # threshold min range (cm)
THRES_MAX_CM      = 100   # threshold max range (cm)
THRES_VALUE_01    = 50    # threshold in 0.1 units (100 -> 10.0)

# Fretting detection: enable extra filter for small motions
FRETTING_DETECT_ON = False

# --- Global flow toggles ---------------------------------------------------

DO_SAVE_CONFIG = True      # saveConfig at the end so values persist
DO_RESET       = True      # resetSystem 0 so new config takes effect
DO_START       = True      # start detection after config
DO_FACTORY_RESET = False   # if True, perform resetCfg first (factory defaults)

# ============================================================================
# BELOW HERE IS "PLUMBING" – NORMALLY NO NEED TO EDIT
# ============================================================================

ser = serial.Serial(PORT, BAUD, timeout=1)
print(f"Opened {PORT} at {BAUD} baud")

def send_cmd(cmd: str, wait: float = 0.2):
    """
    Fire-and-forget command sender: write only, no reads.
    Safe across reset/system start/stop transitions.
    """
    line = (cmd + "\r\n").encode("ascii")
    print(f"--> {cmd!r}")
    ser.write(line)
    ser.flush()
    time.sleep(wait)


# ---- basic helpers ---------------------------------------------------------

def sensor_stop():
    send_cmd("sensorStop", wait=0.5)          # stop detection to apply config

def sensor_start():
    send_cmd("sensorStart", wait=0.5)         # start detection

def save_config():
    send_cmd("saveConfig", wait=0.5)          # persist to flash

def reset_system():
    print("--> 'resetSystem 0'")
    ser.write(b"resetSystem 0\r\n")
    ser.flush()
    time.sleep(1.5)   # allow reboot

def reset_factory():
    """Factory reset: restore defaults (range, sens, baud, etc.)."""
    send_cmd("resetCfg", wait=0.5)
    reset_system()


# ---- configuration setters -------------------------------------------------

def set_detection_range(min_cm: int, max_cm: int, trig_cm: int):
    send_cmd(f"setDetectionRange {min_cm} {max_cm} {trig_cm}", wait=0.5)  # cm

def set_trig_sensitivity(level: int):
    send_cmd(f"setTrigSensitivity {level}", wait=0.5)     # 0–9

def set_keep_sensitivity(level: int):
    send_cmd(f"setKeepSensitivity {level}", wait=0.5)     # 0–9

def set_delay(trig_delay_01s: int, keep_time_05s: int):
    send_cmd(f"setDelay {trig_delay_01s} {keep_time_05s}", wait=0.5)      # 0.01s, 0.5s units

def set_run_app(mode: int):
    """
    Set working app: 0 = presence app, 1 = speed & distance app.
    """
    send_cmd(f"setRunApp {mode}", wait=0.5)

def set_sensor_mode(mode: str):
    """
    Presence vs speed mode inside the app ("exist" vs "speed").
    Implementation uses example text commands (may vary by firmware).
    """
    mode = mode.lower()
    if mode == "exist":
        # Example mapping found in docs/libs: presence (existence) mode
        send_cmd("setSensorMode 0", wait=0.5)
    elif mode == "speed":
        # Speed mode (speed/range emphasis)
        send_cmd("setSensorMode 1", wait=0.5)
    else:
        print(f"Unknown SENSOR_MODE {mode!r}, skipping setSensorMode")

def set_uart_baud(new_baud: int):
    """
    Change the module's UART baud rate.
    After running this once, you must change BAUD at the top to match.
    """
    send_cmd(f"setUart {new_baud}", wait=0.5)

def set_detect_thres(min_cm: int, max_cm: int, thres_01: int):
    """
    Advanced detection threshold (mainly speed/distance app).
    thres_01 is threshold *10 (0.1 units), e.g. 100 -> 10.0.
    """
    send_cmd(f"setDetectThres {min_cm} {max_cm} {thres_01}", wait=0.5)

def set_fretting_detection(on: bool):
    """
    Enable/disable fretting detection filter for small motions.
    """
    val = "1" if on else "0"
    send_cmd(f"setFrettingDetection {val}", wait=0.5)


# ---- main flow -------------------------------------------------------------

if __name__ == "__main__":
    if DO_FACTORY_RESET:
        print("Performing factory reset (resetCfg)...")
        reset_factory()

    print("Stopping sensor to apply configuration...")
    sensor_stop()

    # Optional: change UART on the module itself
    if CHANGE_UART:
        print(f"\nChanging module UART baud to {NEW_UART_BAUD}...")
        set_uart_baud(NEW_UART_BAUD)
        if DO_SAVE_CONFIG:
            save_config()
        if DO_RESET:
            reset_system()
        print("UART changed on module; update BAUD at top and re-run.")
        # After baud change, further commands in this run may not be reliable.
        # Exit to avoid confusion.
        raise SystemExit(0)

    # Working app
    print(f"\nSetting working app (RUN_APP_MODE={RUN_APP_MODE})...")
    set_run_app(RUN_APP_MODE)

    # Sensor mode (within app)
    print(f"Setting sensor mode (SENSOR_MODE={SENSOR_MODE})...")
    set_sensor_mode(SENSOR_MODE)

    # Presence / range tuning
    print("\nSetting detection range:")
    print(f"  MIN_CM={MIN_CM}, MAX_CM={MAX_CM}, TRIG_CM={TRIG_CM}")
    set_detection_range(MIN_CM, MAX_CM, TRIG_CM)

    print("\nSetting sensitivities:")
    print(f"  TRIG_SENS={TRIG_SENS}, KEEP_SENS={KEEP_SENS}")
    set_trig_sensitivity(TRIG_SENS)
    set_keep_sensitivity(KEEP_SENS)

    print("\nSetting timing:")
    print(f"  TRIG_DELAY_01S={TRIG_DELAY_01S} (0.01s units)")
    print(f"  KEEP_TIME_05S={KEEP_TIME_05S} (0.5s units)")
    set_delay(TRIG_DELAY_01S, KEEP_TIME_05S)

    # Advanced threshold / fretting (mainly speed/distance usage)
    if USE_DETECT_THRES:
        print("\nSetting advanced detect threshold:")
        print(f"  THRES_MIN_CM={THRES_MIN_CM}, THRES_MAX_CM={THRES_MAX_CM}, THRES_VALUE_01={THRES_VALUE_01}")
        set_detect_thres(THRES_MIN_CM, THRES_MAX_CM, THRES_VALUE_01)

    print(f"\nSetting fretting detection = {FRETTING_DETECT_ON}...")
    set_fretting_detection(FRETTING_DETECT_ON)

    # Save / reset / start
    if DO_SAVE_CONFIG:
        print("\nSaving configuration to flash...")
        save_config()

    if DO_RESET:
        print("Resetting sensor so new config takes effect...")
        reset_system()

    if DO_START:
        print("Starting detection...")
        sensor_start()

    print("\nDone.")
