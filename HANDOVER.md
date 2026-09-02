# HANDOVER — Phase 3 安全復帰ガイド

**作成日時**: 2026-09-02
**セーブポイント**: `3078fc6` (タグ: `phase3-stable-and-safe`, ブランチ: `phase3-safe-point`)

---

## 1. 現在の構成（3 プロセス並行稼働）

| サービス | ポート | 役割 | 状態 |
|---|---|---|---|
| `audiophile-backend.service` | 8000 | 旧 DSP backend | 稼働中（無傷） |
| `hq-dmp-backend.service` | 8001 | 旧 DMP backend | 稼働中（無傷） |
| `hq-api.service` | **8002** | **新統合バックエンド (Phase 3a/3b 完了)** | **稼働中（systemd 登録済）** |
| `audiophile-frontend.service` / `hq-dmp-frontend.service` | 3000/3001 | Next.js フロントエンド | 稼働中 |
| `unified-shell` | 3002 | 統合フロントエンド（手動起動） | 稼働中 |

### hq_api:8002 が提供する 43 ルート

- **DSP 由来** (3): `/api/devices`, `/api/now_playing`, `/api/dsp_status`
- **DMP 由来** (40): `/api/library/*` (8), `/api/playback/*` (10), `/api/queue/*` (6), `/api/playlists/*` (8), `/api/history/*` (2), `/api/upnp/*` (4), `/health`, `/`

### 検証済み互換性

| 比較対象 | 結果 |
|---|---|
| `hq_api:8002 /api/devices` vs `DSP:8000` | **IDENTICAL** |
| `hq_api:8002 /api/now_playing` vs `DSP:8000` | **IDENTICAL** |
| `hq_api:8002 /api/dsp_status` vs `DSP:8000` | **IDENTICAL** |
| `hq_api:8002 /api/library/artists` vs `DMP:8001` | **IDENTICAL** |
| `hq_api:8002 /api/playback/status` vs `DMP:8001` | **IDENTICAL** |
| `hq_api:8002 /api/queue/` vs `DMP:8001` | **IDENTICAL** |
| `hq_api:8002 /api/history/` vs `DMP:8001` | **IDENTICAL** |
| `hq_api:8002 /api/upnp/servers` vs `DMP:8001` | **IDENTICAL** |

---

## 2. 緊急復帰手順（3 通り）

### 2.1 hq-api だけを止めたい場合（最も軽い）

```bash
sudo systemctl stop hq-api.service
sudo systemctl disable hq-api.service
sudo rm /etc/systemd/system/hq-api.service
sudo systemctl daemon-reload
```

→ 旧 DSP:8000 / DMP:8001 は引き続き稼働。フロントエンドは無影響。

### 2.2 hq-api を含めてコードも完全に取り消したい場合

```bash
cd /home/tysbox/HQ_Linux_Music_Player
git fetch origin
git checkout phase3-stable-and-safe
# または: git reset --hard phase3-stable-and-safe
```

→ `hq_api/` ディレクトリが消失し、`integ` ブランチが Phase 3 着手前の状態に戻る。

### 2.3 旧 backend も含めて全停止してしまった場合の最終手段

```bash
sudo systemctl restart audiophile-backend.service hq-dmp-backend.service
```

→ DSP:8000 / DMP:8001 だけが起動。フロントエンドも無影響。

---

## 3. トラブルシューティング早見表

| 症状 | 確認コマンド | 対処 |
|---|---|---|
| 8002 が応答しない | `sudo systemctl status hq-api.service` | `sudo systemctl restart hq-api.service` |
| 8002 が 503 を返す | `sudo journalctl -u hq-api.service -n 30` | ログに MPD エラーがあれば MPD 再起動 |
| hq_api 起動失敗 | `cat /tmp/hq_api.log` | import エラーならロールバック |
| フロントエンドが反応しない | `curl -sf http://localhost:3002` | shell プロセス再起動 |
| 全停止した | 上記 §2.3 実行 | 30 秒以内に復旧 |

---

## 4. コミット履歴（Phase 3 着手以降）

```
3078fc6 (HEAD -> integ, phase3-safe-point) feat(hq_api): Phase 3b systemd unit 作成・登録・有効化
569ecf2 feat(hq_api): Phase 3a-4 DMP ルータを re-import で統合
5079d3e feat(hq_api): /api/dsp_status を移植（CamillaDSP 状態）
25a5048 feat(hq_api): Phase 3a-2 DSP ルータ移植（/api/devices, /api/now_playing）
bc94262 chore: .gitignore 追加と __pycache__ の追跡除外
e5e1546 feat(hq_api): Phase 3a 最小構成（/health + / のみ）
3118abb docs: DEVELOPMENT_ROADMAP に Phase 3 着手前チェックリスト (§14) を追加
479f4b9 docs: Phase 3 着手前の ADR ドラフトを 5 件作成
e64fc4c test: Phase 3 着手前のエンドポイント応答スナップショット取得
512af77 docs: DEVELOPMENT_ROADMAP に Phase 3.5/4.5/5.5 と SLA 章を追加
```

---

## 5. 既知の未実装項目

| 項目 | 影響 | 対処 |
|---|---|---|
| `/ws/now_playing` (DSP WebSocket) | hq_api 未実装、shell は DSP:8000 を直接参照 | shell の `.env` を変更するまで無影響 |
| `/ws/status` (DMP WebSocket) | hq_api 未実装、shell は DMP:8001 を直接参照 | 同上 |
| `/api/config`, `/api/apply`, `/api/presets`, `/api/volume`, `/api/dsp_restart`, `/api/art` | DSP 機能残り。shell は DSP:8000 を直接参照 | shell の `.env` 変更まで無影響 |
| UPnP 設定の環境変数化 | ハードコードのまま | Phase 3.5-3 で対応 |
| 旧 backend の停止 | 未実施 | Phase 3c で対応（**未実施**） |

---

## 6. 連絡先・参照ドキュメント

| 資料 | パス |
|---|---|
| 統合の完全記録 | [docs/BACKEND_UNIFICATION_WALKTHROUGH.md](docs/BACKEND_UNIFICATION_WALKTHROUGH.md) |
| 開発ロードマップ | [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md) |
| Phase 3 設計判断 | [docs/adr/](docs/adr/) (ADR-001〜005) |
| 現状の応答スナップショット | [tests/snapshots/](tests/snapshots/) (17 ファイル) |

---

**最終更新**: 2026-09-02 17:15 JST
**次回作業前**: この HANDOVER.md と §2 の復帰手順を確認すること

---

## 7. Phase 3a-5 完了（2026-09-02 17:25）

### 追加された機能

| タスク | 内容 | エンドポイント |
|---|---|---|
| Task 1 | DSP 残り GET 移植 | `/api/config`, `/api/presets`, `/api/art` |
| Task 3 | エラーハンドリング統一（ADR-005） | `hq_api/errors.py` |
| Task 4 | Playwright E2E テスト | `unified-shell/e2e/hq-api-smoke.spec.ts` |

### 検証結果

- **Playwright: 7/7 passed (2.6s)**
- `/api/config`, `/api/presets`: DSP:8000 と IDENTICAL
- `/api/art`: SVG プレースホルダ返却（Phase 3c で iTunes 注入予定）
- 統一エラーフォーマット `{"error": {"code", "message", "details"}}` 稼働
- 既存サービス無傷（DSP:8000 / DMP:8001 / shell:3002）

### 追加されたファイル

```
hq_api/
├── errors.py                 ← Task 3
└── routers/
    └── dsp_readonly.py       ← Task 1

unified-shell/
├── playwright.config.ts      ← Task 4
├── e2e/
│   └── hq-api-smoke.spec.ts  ← Task 4
└── package.json (devDependencies 追加)
```

### テスト実行方法

```bash
# Python 標準 unittest のみ（追加インストール不要）
./backend/venv/bin/python3 -m unittest tests.e2e.test_hq_api_compat -v

# Playwright（要 @playwright/test）
cd unified-shell && ./node_modules/.bin/playwright test
```
