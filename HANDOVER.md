# HANDOVER — 残案件引き継ぎ（2026-09-15 時点）

**作成日時**: 2026-09-15
**ブランチ**: `refactor/dsp-modules` (HEAD: `38028ef2`)
**ベースライン**: `rev20260907` (タグ: `rev20260907`, `safety-net-20260911`)

---

## 現在の構成（2 プロセス稼働）

| サービス | ポート | 役割 | 状態 |
|---|---|---|---|
| `hq-api.service` | **8002** | **統合バックエンド (DSP+DMP)** | **稼働中** |
| `unified-shell.service` | **3002** | **統合フロントエンド** | **稼働中** |

> **旧サービス停止済み**: `audiophile-backend` (8000), `audiophile-frontend` (3000), `hq-dmp-backend` (8001), `hq-dmp-frontend` (3001) → `/etc/systemd/system/archive/` にアーカイブ済み

---

## 残案件（優先度順）

### 1. mainブランチへのマージ（優先度: 高）
**内容**: `refactor/dsp-modules` → `main` マージ
**ブロッカー**: ユーザー承認待ち
**ベースライン**: `rev20260907` 保護済み
**関連**: `D_task_management.md` Phase D-4

### 2. Crossfeed / Crosstalk cancellation 再実装（優先度: 低）
**内容**: デジタルクロスフィード（Delay + Gain + Conv）とクロストーク打ち消し（逆位相混合）の実装
**経緯**: `docs/HANDOVER0910.md` に実装経過記録あり（`CROSSTALK_CANCEL_PARAMS`、逆位相混合 `inverted: True`、角度ベースパラメータ統一、`distanceRatio` 等）。`git reset --hard 9a372234` でリセット済み。
**現状**: `backend/dsp/apply_logic.py` はスタブ状態、`unified-shell/src/app/page.tsx` は元の `none`/`light`/`standard` のまま。
**必要作業**: 
- `backend/dsp/apply_logic.py` にデジタルクロスフィード実装（Delay + Gain + Conv）
- `CROSSTALK_CANCEL_PARAMS` 実装（逆位相混合 `inverted: True`）
- `unified-shell/src/app/page.tsx` の UI 変更（`Preset` ダイヤル廃止、角度ベース `crossfeed` + `distanceRatio` 追加）

### 3. 旧フロントエンド削除（優先度: 低）
**内容**: `frontend/` ディレクトリ削除
**理由**: 統合 UI (`unified-shell`) 完成済み、ビルド・デプロイ簡素化
**前提**: 統合 UI 完成確認済み

---

## 現在の構成（2 プロセス稼働）

| サービス | ポート | 役割 | 状態 |
|---|---|---|---|
| `hq-api.service` | **8002** | **統合バックエンド (DSP+DMP)** | **稼働中** |
| `unified-shell.service` | **3002** | **統合フロントエンド** | **稼働中** |

> **旧サービス停止済み**: 全て `/etc/systemd/system/archive/` にアーカイブ済み

---

## 主要エンドポイント (hq_api:8002)

| カテゴリ | エンドポイント |
|---|---|
| DSP | `/api/devices`, `/api/volume`, `/api/dsp_status`, `/api/dsp_restart`, `/api/config`, `/api/apply`, `/api/now_playing`, `/api/presets*`, `/api/dsp_update`, `/ws/now_playing`, `/api/art` |
| DMP | `/api/library/*`, `/api/playback/*`, `/api/queue/*`, `/api/playlists/*`, `/api/history/*`, `/api/upnp/*` |
| 共通 | `/health`, `/` |

---

## 緊急復帰手順

```bash
# hq-api 再起動
sudo systemctl restart hq-api.service

# unified-shell 再起動
sudo systemctl restart unified-shell.service

# 全再起動
sudo systemctl restart hq-api.service unified-shell.service
```

---

## 完了済み主要項目（参考）

| 項目 | コミット | 状態 |
|---|---|---|
| Phase 0〜2 共有モジュール統合 | `9a372234` まで | ✅ 完了 |
| D-2 分離モジュール完成 | `1ae5d27a`/`aaa69850`/`8ed155f4` | ✅ 完了 |
| Phase 3 FastAPI ルータ統合 | `6582d0cf` | ✅ 完了 |
| Phase 4 旧サービス停止 | 運用コマンド | ✅ 完了 |
| Phase 5 systemd unit 統合 | 運用コマンド | ✅ 完了 |
| シークバー修正 | `c6d71736` | ✅ 完了 |
| ボリューム API 422 対策 | `9486ba4a` | ✅ 完了 |
| WebSocket push 化 | `2b348358` | ✅ 完了 |
| アルバムアート遅延対策 | `38028ef2` | ✅ 完了 |
| E2Eテスト追加 | `hq-api-integration.spec.ts` | ✅ 完了 |
| ドキュメント整理 | `WALKTHROUGH_INTEGRATED.md` | ✅ 完了 |

---

## 既知の制限事項

| 項目 | 状態 | 対応予定 |
|---|---|---|
| mainマージ未了 | 承認待ち | ユーザー承認後実施 |
| Crossfeed/Crosstalk 未実装 | 再実装待ち | 低優先度 |
| 旧フロントエンド残存 | `frontend/` 存在 | 統合完了後に削除予定 |

---

## 緊急復帰手順

```bash
# hq-api 再起動
sudo systemctl restart hq-api.service

# unified-shell 再起動
sudo systemctl restart unified-shell.service

# 全再起動
sudo systemctl restart hq-api.service unified-shell.service
```

---

## 完了済み主要項目（参考）

| 項目 | コミット | 状態 |
|---|---|---|
| Phase 0〜2 共有モジュール統合 | `9a372234` まで | ✅ 完了 |
| D-2 分離モジュール完成 | `1ae5d27a`/`aaa69850`/`8ed155f4` | ✅ 完了 |
| Phase 3 FastAPI ルータ統合 | `6582d0cf` | ✅ 完了 |
| Phase 4 旧サービス停止 | 運用コマンド | ✅ 完了 |
| Phase 5 systemd unit 統合 | 運用コマンド | ✅ 完了 |
| シークバー修正 | `c6d71736` | ✅ 完了 |
| ボリューム API 422 対策 | `9486ba4a` | ✅ 完了 |
| WebSocket push 化 | `2b348358` | ✅ 完了 |
| アルバムアート遅延対策 | `38028ef2` | ✅ 完了 |
| E2Eテスト追加 | `hq-api-integration.spec.ts` | ✅ 完了 |
| ドキュメント整理 | `WALKTHROUGH_INTEGRATED.md` | ✅ 完了 |

---

## 既知の制限事項

| 項目 | 状態 | 対応予定 |
|---|---|---|
| mainマージ未了 | 承認待ち | ユーザー承認後実施 |
| Crossfeed/Crosstalk 未実装 | 再実装待ち | 低優先度 |
| 旧フロントエンド残存 | `frontend/` 存在 | 統合完了後に削除予定 |

---

## 緊急復帰手順

```bash
# hq-api 再起動
sudo systemctl restart hq-api.service

# unified-shell 再起動
sudo systemctl restart unified-shell.service

# 全再起動
sudo systemctl restart hq-api.service unified-shell.service
```

---

## 完了済み主要項目（参考）

| 項目 | コミット | 状態 |
|---|---|---|
| Phase 0〜2 共有モジュール統合 | `9a372234` まで | ✅ 完了 |
| D-2 分離モジュール完成 | `1ae5d27a`/`aaa69850`/`8ed155f4` | ✅ 完了 |
| Phase 3 FastAPI ルータ統合 | `6582d0cf` | ✅ 完了 |
| Phase 4 旧サービス停止 | 運用コマンド | ✅ 完了 |
| Phase 5 systemd unit 統合 | 運用コマンド | ✅ 完了 |
| シークバー修正 | `c6d71736` | ✅ 完了 |
| ボリューム API 422 対策 | `9486ba4a` | ✅ 完了 |
| WebSocket push 化 | `2b348358` | ✅ 完了 |
| アルバムアート遅延対策 | `38028ef2` | ✅ 完了 |
| E2Eテスト追加 | `hq-api-integration.spec.ts` | ✅ 完了 |
| ドキュメント整理 | `WALKTHROUGH_INTEGRATED.md` | ✅ 完了 |

---

## 既知の制限事項

| 項目 | 状態 | 対応予定 |
|---|---|---|
| mainマージ未了 | 承認待ち | ユーザー承認後実施 |
| Crossfeed/Crosstalk 未実装 | 再実装待ち | 低優先度 |
| 旧フロントエンド残存 | `frontend/` 存在 | 統合完了後に削除予定 |

---

## 緊急復帰手順

```bash
# hq-api 再起動
sudo systemctl restart hq-api.service

# unified-shell 再起動
sudo systemctl restart unified-shell.service

# 全再起動
sudo systemctl restart hq-api.service unified-shell.service
```

---

## 完了済み主要項目（参考）

| 項目 | コミット | 状態 |
|---|---|---|
| Phase 0〜2 共有モジュール統合 | `9a372234` まで | ✅ 完了 |
| D-2 分離モジュール完成 | `1ae5d27a`/`aaa69850`/`8ed155f4` | ✅ 完了 |
| Phase 3 FastAPI ルータ統合 | `6582d0cf` | ✅ 完了 |
| Phase 4 旧サービス停止 | 運用コマンド | ✅ 完了 |
| Phase 5 systemd unit 統合 | 運用コマンド | ✅ 完了 |
| シークバー修正 | `c6d71736` | ✅ 完了 |
| ボリューム API 422 対策 | `9486ba4a` | ✅ 完了 |
| WebSocket push 化 | `2b348358` | ✅ 完了 |
| アルバムアート遅延対策 | `38028ef2` | ✅ 完了 |
| E2Eテスト追加 | `hq-api-integration.spec.ts` | ✅ 完了 |
| ドキュメント整理 | `WALKTHROUGH_INTEGRATED.md` | ✅ 完了 |

---

## 既知の制限事項

| 項目 | 状態 | 対応予定 |
|---|---|---|
| mainマージ未了 | 承認待ち | ユーザー承認後実施 |
| Crossfeed/Crosstalk 未実装 | 再実装待ち | 低優先度 |
| 旧フロントエンド残存 | `frontend/` 存在 | 統合完了後に削除予定 |

---

## 緊急復帰手順

```bash
# hq-api 再起動
sudo systemctl restart hq-api.service

# unified-shell 再起動
sudo systemctl restart unified-shell.service

# 全再起動
sudo systemctl restart hq-api.service unified-shell.service
```

---

## 連絡先・参照ドキュメント

| 資料 | パス |
|---|---|
| 統合の完全記録 | [docs/BACKEND_UNIFICATION_WALKTHROUGH.md](docs/BACKEND_UNIFICATION_WALKTHROUGH.md) |
| 開発ロードマップ | [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md) |
| Phase 3 設計判断 | [docs/adr/](docs/adr/) (ADR-001〜005) |
| 統合記録統合版 | [docs/WALKTHROUGH_INTEGRATED.md](docs/WALKTHROUGH_INTEGRATED.md) |
| アーカイブ済みドキュメント | [docs/archive/](docs/archive/) |

---

**最終更新**: 2026-09-15
**ブランチ**: `refactor/dsp-modules` (HEAD: `38028ef2`)
**ベースライン**: `rev20260907` (タグ: `rev20260907`, `safety-net-20260911`)