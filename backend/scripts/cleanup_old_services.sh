#!/bin/bash
set -euo pipefail

cat <<'EOF'
This script removes legacy SoX/MPD service units left behind in /etc/systemd/system.
You must run it as a user with sudo privileges.
EOF

sudo rm -f /etc/systemd/system/run_sox_fifo.service \
            /etc/systemd/system/run_sox_fifo.service.bak \
            /etc/systemd/system/sox-mpd.service \
            /etc/systemd/system/mpd_watcher.service
sudo rm -rf /etc/systemd/system/run_sox_fifo.service.d
sudo systemctl daemon-reload
sudo systemctl disable --now run_sox_fifo.service sox-mpd.service mpd_watcher.service || true

echo "Legacy old audio services removed."
