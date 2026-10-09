#!/bin/bash
# kiosk-set-hostname <name>: give the kiosk a hostname that survives reboots.
# Raspberry Pi OS (trixie) runs cloud-init, which re-applies "hostname:" from the
# boot partition's user-data on every boot, so that line is changed too, along
# with /etc/hostname (hostnamectl) and the 127.0.1.1 line in /etc/hosts (so sudo
# can still resolve the name). Used by both setup wizards via sudo.
set -eu
name="${1:-}"
if ! [[ "$name" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
  echo "invalid hostname: '$name' (lowercase letters, digits and -, up to 63)" >&2
  exit 2
fi
userdata=/boot/firmware/user-data
if [ -f "$userdata" ] && grep -q '^hostname:' "$userdata"; then
  sed -i "s/^hostname:.*/hostname: $name/" "$userdata"
fi
hostnamectl set-hostname "$name"
if grep -q '^127\.0\.1\.1[[:space:]]' /etc/hosts; then
  sed -i "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t$name/" /etc/hosts
else
  printf '127.0.1.1\t%s\n' "$name" >> /etc/hosts
fi
