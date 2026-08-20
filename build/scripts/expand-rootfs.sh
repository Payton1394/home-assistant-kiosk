#!/bin/bash
# Expands the root partition + filesystem to fill whatever SD card this image
# was flashed to. Runs once at first boot (see rootfs-expand.service), then
# marks itself done via /etc/.rootfs-expanded.
set -euo pipefail

MARKER="/etc/.rootfs-expanded"
LOG="/var/log/rootfs-expand.log"
exec >>"$LOG" 2>&1
echo "----- $(date) -----"

if [ -f "$MARKER" ]; then
  echo "Already expanded, nothing to do."
  exit 0
fi

ROOT_SRC="$(findmnt -no SOURCE /)"
echo "Root device: $ROOT_SRC"

# Split into parent disk + partition number - handles both /dev/mmcblk0p2
# (numbered-disk) and /dev/sda2 (lettered-disk) naming styles.
if [[ "$ROOT_SRC" =~ ^(/dev/.*[0-9])p([0-9]+)$ ]]; then
  DISK="${BASH_REMATCH[1]}"
  PARTNUM="${BASH_REMATCH[2]}"
elif [[ "$ROOT_SRC" =~ ^(/dev/[a-zA-Z]+)([0-9]+)$ ]]; then
  DISK="${BASH_REMATCH[1]}"
  PARTNUM="${BASH_REMATCH[2]}"
else
  echo "Could not parse root device '$ROOT_SRC'; skipping expand."
  touch "$MARKER"
  exit 0
fi

echo "Disk: $DISK  Partition: $PARTNUM"

growpart "$DISK" "$PARTNUM" || echo "growpart: nothing to grow (already at max size, or an error - see above)."
resize2fs "$ROOT_SRC" || echo "resize2fs: nothing to resize (already at max size, or an error - see above)."

touch "$MARKER"
echo "Done."
