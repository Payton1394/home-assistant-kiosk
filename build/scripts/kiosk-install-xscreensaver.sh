#!/bin/bash
# Installs xscreensaver on demand. The image ships without it; the setup wizard
# (on-screen or web) runs this only when "Use the built-in screensaver" is ticked.
# Needs internet. Installed to /usr/local/sbin, allowed for the kiosk user in
# sudoers.d/kiosk-wizard so the on-screen wizard can call it with sudo -n.
set -euo pipefail
if command -v xscreensaver >/dev/null 2>&1; then echo "xscreensaver already installed"; exit 0; fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends xscreensaver >/dev/null
echo "xscreensaver installed"
