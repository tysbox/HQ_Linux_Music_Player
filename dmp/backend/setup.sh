#!/bin/bash
# DMP バックエンド セットアップスクリプト
# 実行: bash setup.sh

set -e

INSTALL_DIR="/home/tysbox/HQ_Linux_Music_Player/dmp/backend"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== DMP バックエンド セットアップ ==="

# 1. インストールディレクトリ作成
echo "[1/5] ディレクトリ作成..."
mkdir -p "$INSTALL_DIR"

# 2. ファイルをインストール先にコピー
echo "[2/5] ファイルコピー..."
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR"/

# 3. Python仮想環境作成
echo "[3/5] Python仮想環境作成..."
cd "$INSTALL_DIR"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
./venv/bin/python3 - <<'PY'
import importlib

for module_name in ("requests", "fastapi", "mpd", "aiohttp", "app.main"):
	importlib.import_module(module_name)

print("DMP backend import check: OK")
PY

# 4. 設定ディレクトリ作成
echo "[4/5] 設定ディレクトリ作成..."
mkdir -p ~/.config/audiophile-dmp

# 5. systemdサービス登録
echo "[5/5] systemdサービス登録..."
sudo cp dmp-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dmp-backend.service

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "起動コマンド:"
echo "  sudo systemctl start dmp-backend"
echo ""
echo "ステータス確認:"
echo "  sudo systemctl status dmp-backend"
echo ""
echo "ログ確認:"
echo "  journalctl -u dmp-backend -f"
echo ""
echo "API確認:"
echo "  curl http://localhost:8001/health"
