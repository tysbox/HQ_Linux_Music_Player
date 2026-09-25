#!/bin/bash
# 静的検査: 現行GUIのソース中存在を保証し、旧構成の直接参照を拒否する。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -d new-gui/src && ! -d new-gui/app ]]; then
  echo "ERROR: new-gui source directory not found" >&2
  exit 1
fi

if grep -rE '(localhost|127\.0\.0\.1|0\.0\.0\.0):(3000|3001|3002|8000|8001)|unified-shell' \
    new-gui/src new-gui/app \
    --include='*.ts' --include='*.tsx' --exclude-dir=node_modules; then
  echo "ERROR: 現行GUIに旧構成への参照があります" >&2
  exit 1
fi

if grep -rE 'NEXT_PUBLIC_API_URL|window\.location\.hostname.*8002' \
    new-gui/src --include='*.ts' --include='*.tsx' --exclude-dir=node_modules >/dev/null; then
  echo "OK: 現行GUIは共通API host設定を使用"
else
  echo "ERROR: 共通API host設定が見つかりません" >&2
  exit 1
fi

echo "OK: 現行GUIは3003 -> 8002構成"
