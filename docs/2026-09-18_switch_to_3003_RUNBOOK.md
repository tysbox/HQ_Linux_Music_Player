# 3003デフォルト化 切替手順書（実行用）

作成日: 2026-09-18
前提: `docs/2026-09-17_8002-3003_migration_review.md` H章の実施手順

## 現状（切替前・実機確認済み）

```
enabled: hq-api / unified-shell / audiophile-new-gui（3つとも enabled）
active:  hq-api(active) / unified-shell(active) / audiophile-new-gui(inactive)
LISTEN:  0.0.0.0:8002 / 0.0.0.0:3002（3003なし）
```

## 手順（ターミナルで実行）

> AI側からはsudoパスワードが必要なため自動実行できません。
> 下記をターミナルに貼り付けて実行してください。

```bash
sudo systemctl disable unified-shell.service
sudo systemctl daemon-reload
sudo systemctl stop unified-shell.service
sudo systemctl start audiophile-new-gui.service
sleep 3
systemctl is-active hq-api.service audiophile-new-gui.service unified-shell.service
ss -ltn | grep -E ':8002|:3002|:3003'
curl -sf http://localhost:8002/health && echo "8002 OK"
curl -sI http://localhost:3003/ | head -3
```

### 期待される結果

```
hq-api.service: active
audiophile-new-gui.service: active
unified-shell.service: inactive
LISTEN 0.0.0.0:8002
LISTEN 0.0.0.0:3003
(3002なし)
8002 OK
HTTP/1.1 200 OK
```

## 比較のため3002に戻す手順

```bash
sudo systemctl stop audiophile-new-gui.service
sudo systemctl start unified-shell.service
curl -sI http://localhost:3002/ | head -3
```

## 3003に戻す手順

```bash
sudo systemctl stop unified-shell.service
sudo systemctl start audiophile-new-gui.service
curl -sI http://localhost:3003/ | head -3
```

> 注意：`start`だけでは並列起動できない（`Conflicts=`が双方向）。
> 必ず **stop→start の順**で切り替えること。
