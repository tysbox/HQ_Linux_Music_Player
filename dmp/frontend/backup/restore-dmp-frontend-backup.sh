#!/bin/bash
set -e
BASE="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$BASE/.." && pwd)"

echo "Restoring DMP frontend backup..."
cp "$PROJECT_ROOT/backup/next.config.js.bak" "$PROJECT_ROOT/next.config.js"
cp "$PROJECT_ROOT/backup/dmp-frontend.service.bak" "$PROJECT_ROOT/dmp-frontend.service"
sudo cp /etc/systemd/system/dmp-frontend.service.bak /etc/systemd/system/dmp-frontend.service
sudo systemctl daemon-reload
sudo systemctl restart dmp-frontend.service
sudo systemctl status dmp-frontend.service --no-pager | head -40

echo "Restore complete. If you want, rebuild with the previous config using:"
echo "  cd $PROJECT_ROOT && /home/tysbox/.local/nodejs/bin/npm run build"
