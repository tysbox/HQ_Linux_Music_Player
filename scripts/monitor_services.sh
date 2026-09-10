#!/bin/bash
# 運用強化: サービス監視（C対策）
set -e
for svc in hq-api.service unified-shell.service; do
  if ! systemctl is-active --quiet "$svc"; then
    echo "ALERT: $svc is not active ($(date -Iseconds))"
    systemctl restart "$svc"
    echo "RECOVERED: $svc restarted"
  else
    echo "OK: $svc active"
  fi
done
