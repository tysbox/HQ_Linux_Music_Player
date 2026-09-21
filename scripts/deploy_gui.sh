#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# GUI 再デプロイスクリプト（ポート3003 / Next.js standalone）
#
# 背景（2026-09-21 の障害）:
#  - `npm run build` は `.next/standalone` を再生成するため、稼働中インスタンスが
#    配信している `standalone/.next/static` が消える。
#    → ブラウザーは新しい JS/CSS を取得できず（404）、キャッシュを消しても
#      「画面が変わらない／壊れる」状態になる。
#  - systemd の ExecStartPre も同ディレクトリを rm -rf → cp するため、再起動が
#    中断されると静的アセットが消えたままになる。
#
# 本スクリプトは「ビルド → static/public を standalone へ原子的に反映 → 再起動」を
# 一括で行い、上記の取り違えを防ぐ。実行後は GUI に REV 表示が出る。
#
# 使い方:  ./scripts/deploy_gui.sh            （最後に sudo パスワードを聞かれます）
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/../new-gui"

echo "==> build"
npm run build

echo "==> copy static/public into standalone (atomic)"
mkdir -p .next/standalone/.next
rm -rf .next/standalone/.next/static.new .next/standalone/public.new
cp -r .next/static .next/standalone/.next/static.new
cp -r public .next/standalone/public.new
rm -rf .next/standalone/.next/static .next/standalone/public
mv .next/standalone/.next/static.new .next/standalone/.next/static
mv .next/standalone/public.new .next/standalone/public

echo "==> restart service (requires sudo password)"
sudo systemctl restart audiophile-new-gui.service
sleep 3
systemctl is-active audiophile-new-gui.service

echo "==> check"
curl -s -o /dev/null -w 'html=%{http_code}\n' http://localhost:3003
for f in $(ls .next/standalone/.next/static/chunks/*.js | head -3); do
  curl -s -o /dev/null -w "chunk(%{http_code}) " "http://localhost:3003/_next/static/chunks/$(basename "$f")"
done
echo
echo "OK — ブラウザーで http://<host>:3003 を再読み込みしてください（フッターに GUI REV 表示）。"
