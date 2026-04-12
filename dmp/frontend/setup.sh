#!/bin/bash
# DMP フロントエンド セットアップスクリプト
# 実行: bash setup.sh

set -e

INSTALL_DIR="/home/tysbox/HQ_Linux_Music_Player/dmp/frontend"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== DMP フロントエンド セットアップ ==="

# 1. インストールディレクトリ作成・コピー
echo "[1/5] ファイルコピー..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR"/

# 2. .env.local 作成
echo "[2/5] 環境変数設定..."
cd "$INSTALL_DIR"
if [ ! -f .env.local ]; then
  cp .env.local.example .env.local
  echo "  → .env.local を作成しました"
  echo "  → 必要に応じて NEXT_PUBLIC_API_URL を編集してください"
  echo "  → 例: http://192.168.x.x:8001（LAN内他端末からアクセスする場合）"
fi

# 3. npm install
echo "[3/5] npm install..."
npm install

# 4. ビルド
echo "[4/5] Next.js ビルド..."
npm run build

# 5. systemdサービス登録
echo "[5/5] systemdサービス登録..."

# ExecStartのパスをnode_modulesの実際のパスに合わせて修正
sed -i "s|ExecStart=.*|ExecStart=$INSTALL_DIR/node_modules/.bin/next start -p 3001|" dmp-frontend.service
sudo cp dmp-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dmp-frontend.service

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "起動コマンド:"
echo "  sudo systemctl start dmp-frontend"
echo ""
echo "ステータス確認:"
echo "  sudo systemctl status dmp-frontend"
echo ""
echo "ブラウザでアクセス:"
echo "  http://localhost:3001"
echo "  http://[LinuxマシンIP]:3001"
