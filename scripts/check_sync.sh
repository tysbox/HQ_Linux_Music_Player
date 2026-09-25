#!/bin/bash
# 参照不一致再発防止: 現行GUIが旧3002や旧ポートへ依存していないか検査
set -e
if grep -rE 'localhost:(3000|3001|3002|8000|8001)|unified-shell' new-gui/src new-gui/app --include='*.ts' --include='*.tsx' --exclude-dir=node_modules; then
  echo "ERROR: 現行GUIに旧構成への参照があります"
  exit 1
fi
echo "OK: 現行GUIは3003 -> 8002構成"
