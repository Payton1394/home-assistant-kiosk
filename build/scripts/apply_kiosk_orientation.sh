#!/usr/bin/env bash

CONFIG="/home/kiosk/kiosk_config.ini"
LOG="/home/kiosk/kiosk_orientation.log"
SECTION="display"

exec >>"$LOG" 2>&1
echo "----- $(date) -----"
echo "Starting orientation helper..."

export DISPLAY=:0
export XAUTHORITY=/home/kiosk/.Xauthority

sleep 3

ini_get() {
    local section="$1" key="$2"
    local in_section=0 line k v

    while IFS= read -r line; do
        case "$line" in
            \[*\])
                if [ "$line" = "[$section]" ]; then
                    in_section=1
                else
                    in_section=0
                fi
                ;;
            *)
                [ "$in_section" -eq 0 ] && continue
                case "$line" in
                    ''|\;*|\#*) continue ;;
                esac
                k="${line%%=*}"
                v="${line#*=}"
                k="${k%"${k##*[![:space:]]}"}"
                k="${k##[[:space:]]}"
                v="${v%"${v##*[![:space:]]}"}"
                v="${v##[[:space:]]}"
                v="${v%%;*}"
                v="${v%%#*}"
                v="${v%"${v##*[![:space:]]}"}"
                v="${v##[[:space:]]}"
                [ "$k" = "$key" ] && { echo "$v"; return 0; }
                ;;
        esac
    done < "$CONFIG"
}

ROTATION="$(ini_get "$SECTION" rotation)"
TOUCH_DEV="$(ini_get "$SECTION" touch_device)"

echo "ROTATION from ini: '$ROTATION'"
echo "TOUCH_DEV from ini: '$TOUCH_DEV'"

[ -z "$ROTATION" ] && ROTATION="normal"

echo "Running xrandr with rotation '$ROTATION'..."
xrandr --output HDMI-1 --mode 1920x1080 --rate 60 --rotate "$ROTATION"

if [ -z "$TOUCH_DEV" ]; then
  # Nobody types an exact xinput device name/id into the wizard in practice -
  # auto-detect instead. Matching on the device NAME isn't reliable (the same
  # physical panel has been observed reporting "Waveshare  Waveshare" one
  # boot and "Waveshare  Waveshare  Touchscreen" another - no "touch" match
  # at all in the first case). Instead, use xinput's own capability
  # classification: a real touch device reports XITouchClass. Skip the
  # aggregate "Virtual core pointer" master (which mirrors XITouchClass from
  # whatever slave feeds it) and only match actual slave pointer devices.
  current_id="" current_is_slave_pointer=0
  while IFS= read -r xi_line; do
    if [[ "$xi_line" =~ id=([0-9]+) ]]; then
      current_id="${BASH_REMATCH[1]}"
      if [[ "$xi_line" =~ slave[[:space:]]+pointer ]]; then
        current_is_slave_pointer=1
      else
        current_is_slave_pointer=0
      fi
    elif [[ $current_is_slave_pointer -eq 1 ]] && [[ "$xi_line" == *"XITouchClass"* ]]; then
      TOUCH_DEV="$current_id"
      break
    fi
  done < <(xinput list --long 2>/dev/null)
  echo "Auto-detected touch device: '$TOUCH_DEV'"
fi

[ -z "$TOUCH_DEV" ] && { echo "No touch device found (ini override and auto-detect both empty); exiting."; exit 0; }

# Touch matrices matching rotation and your X setup
case "$ROTATION" in
  normal)
    MATRIX="1 0 0 0 1 0 0 0 1"
    ;;
  right)
    MATRIX="0 1 0 -1 0 1 0 0 1"
    ;;
  left)
    MATRIX="0 -1 1 1 0 0 0 0 1"
    ;;
  inverted)
    MATRIX="-1 0 1 0 -1 1 0 0 1"
    ;;
  *)
    echo "Unknown rotation '$ROTATION', using normal."
    MATRIX="1 0 0 0 1 0 0 0 1"
    ;;
esac

echo "Applying touch matrix: $MATRIX to '$TOUCH_DEV'"

DEV="$TOUCH_DEV"  # id or name both work here

xinput set-prop "$DEV" \
  "Coordinate Transformation Matrix" $MATRIX || echo "xinput failed"
