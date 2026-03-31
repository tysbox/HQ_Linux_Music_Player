#!/bin/bash
# Rollback helper — stop & disable watcher and restart run_sox_fifo to fallback
set -euo pipefail

echo "Stopping bt-connect-watcher.service (if running)..."
sudo systemctl stop bt-connect-watcher.service || true

echo "Disabling bt-connect-watcher.service..."
sudo systemctl disable bt-connect-watcher.service || true

echo "Restarting run_sox_fifo.service to ensure fallback (plug:default)..."
sudo systemctl restart run_sox_fifo.service || true

echo "Rollback complete. To re-enable watcher: sudo systemctl enable --now bt-connect-watcher.service"