# 8002/3002 参照不一致 再発防止策（推奨）

## 1. 単一参照元の徹底（コードレベル）
- `unified-shell/src/lib/api.ts` の `DEFAULT_API_URL` のみを唯一の参照元とする
- `page.tsx` や他コンポーネントでの `fetch('http://localhost:8002...')` 直書きを禁止
- CI で `grep -r "localhost:8002" unified-shell/src/` を実行し、直書きがあれば失敗

## 2. 環境変数の統一（ビルド時・実行時）
- `.env` / `systemd` `Environment=` / `next.config.js` の `NEXT_PUBLIC_API_URL` を同一値に固定
- `unified-shell.service` の `Environment=` に `NEXT_PUBLIC_API_URL=http://localhost:8002` を追加

## 3. systemd 依存の強化（起動順序）
- `unified-shell.service`: `Requires=hq-api.service` は既に設定済み
- 追加推奨: `ExecStartPre` に `curl -sf --max-time 5 http://localhost:8002/health || exit 1` を入れ、8002未起動時に3002起動を遅延

## 4. ビルド成果物の自動同期
- `ExecStartPre` の `cp -r` は既に実装済み（`.next/standalone` へコピー）
- 追加推奨: `unified-shell.service` の `ExecReload` または CI で `systemctl restart unified-shell` をビルド後に自動実行

## 5. 監視・検知
- `systemctl is-active hq-api.service unified-shell.service` を定期チェック（cron または監視スクリプト）
- `curl -sf http://localhost:3002/` と `curl -sf http://localhost:8002/health` の両方をヘルスチェックに含める
