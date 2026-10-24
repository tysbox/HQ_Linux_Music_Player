# Walkthrough 統合記録 — 2026-09-15 時点

> **最終更新**: 2026-09-15
> **ブランチ**: `refactor/dsp-modules` (HEAD: `38028ef2`)
> **ベースライン**: `rev20260907` (タグ: `rev20260907`, `safety-net-20260911`)

---

## 解決済み項目一覧（時系列）

### Phase 0〜2: 共有モジュール構築・統合（`9a372234` まで）

| タスク | 内容 | コミット |
|---|---|---|
| Phase 0 | `hqmplayer_core` 共有モジュール骨格追加 | `57ce7e2` |
| Phase 1a | MPD 接続モデル統一（async 専用化） | `a297dd6` |
| Phase 1b | 整形ロジック統合 (`format_now_playing`) | `d8faa57` |
| Phase 1c | meta_cache 共有化 | `1ea19d5` |
| Phase 1d | アルバムアート経路統合 (`resolve_art`) | `6694ba5` |
| Phase 2 | async 専用化（マルチイベントループ競合解消） | `62587c0` |

### Phase 3: FastAPI ルータ統合（DSP→hq_api）

| タスク | 内容 | コミット |
|---|---|---|
| Phase 3a-2 | DSP ルータ移植 (`/api/devices`, `/api/now_playing`) | `25a5048` |
| Phase 3a-4 | DMP ルータ re-import 統合 | `569ecf2` |
| Phase 3a-5 | DSP 読み取り専用ルータ (`/api/config`, `/api/presets`, `/api/art`) | `5079d3e` |
| Phase X-1 | `/api/art` iTunes フォールバック | `183730a` |
| Phase X-2 | WebSocket 移植 (`/ws/now_playing`, `/ws/status`, `/ws/all`) | `ccca88c` |
| Phase X-3 | DSP 書き込み系 API (`/api/presets`, `/api/volume`, `/api/apply`, `/api/dsp_restart`) | `1e42808`, `53e5d84` |
| Phase X-4 | Playwright E2E テスト | `b3fb87a` |
| Phase X-5 | unified-shell を hq_api 参照に切替 | `f1a10a41` |
| Phase 3a-5 Task 1 | DSP 読み取り専用ルータ追加 | `5079d3e` |
| Phase 3a-5 Task 3 | エラーハンドリング統一 (ADR-005) | `ccca88c` |
| Phase 3a-5 Task 4 | Playwright E2E テスト | `b3fb87a` |
| **Phase 3 完了** | DSP エンドポイントを hq_api に集約、`backend/main.py` 939行→334行 | `6582d0cf` |

### Phase 4: 旧サービス停止・新サービス単体運用

| タスク | 内容 | 実施日 |
|---|---|---|
| 旧サービス停止・無効化 | `audiophile-backend` (8000), `audiophile-frontend` (3000), `hq-dmp-backend` (8001), `hq-dmp-frontend` (3001) | 2026-09-15 |
| 新サービス単体運用確認 | `hq-api` (8002), `unified-shell` (3002) | 2026-09-15 |
| 旧サービスファイルアーカイブ | `/etc/systemd/system/archive/` へ移動 | 2026-09-15 |

### Phase 5: systemd unit 統合

| タスク | 内容 | 実施日 |
|---|---|---|
| 旧サービスファイルアーカイブ | `/etc/systemd/system/archive/` へ移動 | 2026-09-15 |
| 残存サービス | `hq-api` (8002), `unified-shell` (3002) | 2026-09-15 |

---

## 追加修正（緊急度高）

| # | 修正内容 | コミット |
|---|---|---|
| #4 | シークバー動作不良修正 (`await` 追加) | `c6d71736` |
| #9 | ボリューム API 422 対策 (起動待機ロジック) | `9486ba4a` |
| #8 | WebSocket polling → push 化 (`/ws/now_playing` idle駆動) | `2b348358` |
| #10 | アルバムアート遅延対策 (iTunes リダイレクト URL キャッシュ) | `38028ef2` |

---

## D-2 分離モジュール完成

| モジュール | 役割 | コミット |
|---|---|---|
| `backend/dsp/yaml_generator.py` | YAML生成・定数・ヘルパー | `1ae5d27a` |
| `backend/dsp/state_manager.py` | 設定永続化・正規化・前提条件・プリセット | `aaa69850` |
| `backend/dsp/apply_logic.py` | 音量初期化・DSP再起動・適用・パラメータ更新 | `8ed155f4` |

---

## 検証結果（全フェーズ共通）

- ✅ **全単体テスト 35 件 PASS**
- ✅ **`camilladsp --check` 検証 OK** (`Config is valid`)
- ✅ **`backend/main.py` モノリス解消** (939行 → 334行, 65%削減)
- ✅ **DSP/DMP 統合完了**: 2プロセス (8000/8001) → 1プロセス (8002)
- ✅ **systemd 統合完了**: 4サービス → 2サービス (`hq-api` + `unified-shell`)
- ✅ **E2Eテスト 4件 PASS** (統合フロー検証)

---

## 現在の構成（2 プロセス稼働）

| サービス | ポート | 役割 | 状態 |
|---|---|---|---|
| `hq-api.service` | **8002** | **統合バックエンド (DSP+DMP)** | **稼働中** |
| `unified-shell.service` | **3002** | **統合フロントエンド** | **稼働中** |

> **旧サービス停止済み**: 全て `/etc/systemd/system/archive/` にアーカイブ済み

---

## 未解決課題（優先度順）

| # | 課題 | 優先度 | 備考 |
|---|---|---|---|
| 1 | E2Eテスト追加（統合フロー検証） | 🟡 高 | ✅ 完了 (`hq-api-integration.spec.ts`) |
| 2 | mainブランチへのマージ | 🟡 高 | ユーザー承認待ち |
| 3 | アルバムアート遅延対策のドキュメント化 | 🟢 中 | 実装済み (`38028ef2`) |
| 4 | ドキュメント整理 (HANDOVER/Walkthrough統合) | 🟢 中 | 本ファイルで完了 |
| 5 | 旧フロントエンド削除 (`frontend/`) | 🔵 低 | 統合完了後に削除予定 |
| 6 | Crossfeed / Crosstalk cancellation 再実装 | 🔵 低 | `docs/HANDOVER0910.md` に経過記録あり、再実装待ち |

---

## 既知の制限事項

| 項目 | 状態 | 対応予定 |
|---|---|---|
| mainマージ未了 | 承認待ち | ユーザー承認後実施 |
| ドキュメント分散 | 整理完了 | 本ファイルで統合済み |
| 旧フロントエンド残存 | `frontend/` 存在 | 統合完了後に削除予定 |
| Crossfeed/Crosstalk 未実装 | 再実装待ち | 低優先度 |

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

## 既知の制限事項

| 項目 | 状態 | 対応予定 |
|---|---|---|
| E2Eテスト未実装 | ✅ 完了 | Playwright で統合フロー検証追加済み |
| mainマージ未了 | 承認待ち | ユーザー承認後実施 |
| ドキュメント分散 | ✅ 完了 | 本ファイルで統合済み |
| 旧フロントエンド残存 | `frontend/` 存在 | 統合完了後に削除予定 |
| Crossfeed/Crosstalk 未実装 | 再実装待ち | 低優先度 |

---

## 連絡先・参照ドキュメント

| 資料 | パス |
|---|---|
| 統合の完全記録 | [docs/BACKEND_UNIFICATION_WALKTHROUGH.md](docs/BACKEND_UNIFICATION_WALKTHROUGH.md) |
| 開発ロードマップ | [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md) |
| Phase 3 設計判断 | [docs/adr/](docs/adr/) (ADR-001〜005) |
| 現状の応答スナップショット | [tests/snapshots/](tests/snapshots/) (17 ファイル) |
| アーカイブ済みドキュメント | [docs/archive/](docs/archive/) |

---

**最終更新**: 2026-09-15
**ブランチ**: `refactor/dsp-modules` (HEAD: `38028ef2`)
**ベースライン**: `rev20260907` (タグ: `rev20260907`, `safety-net-20260911`)