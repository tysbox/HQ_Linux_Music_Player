#!/bin/bash
# 運用強化: 現行構成（統合API 8002 / 新GUI 3003）を監視
set -e
for svc in hq-api.service audiophile-new-gui.service; do
  if ! systemctl is-active --quiet "$svc"; then
    echo "ALERT: $svc is not active ($(date -Iseconds))"
    systemctl restart "$svc"
    echo "RECOVERED: $svc restarted"
  else
    echo "OK: $svc active"
  fi
done
