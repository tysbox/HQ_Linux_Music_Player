#!/bin/bash
# 参照不一致再発防止: 直書き検出
set -e
if grep -r "localhost:8002" unified-shell/src/ --include="*.ts" --include="*.tsx" --exclude-dir=node_modules; then
  echo "ERROR: localhost:8002 直書き検出"
  exit 1
fi
echo "OK: 直書きなし"
