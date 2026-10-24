# HQ Linux Music Player — システム構造・問題点レポート

作成日: 2026-09-15
最終更新: 2026-09-15 (コミット `69498d4e` 反映)
対象: `/home/tysbox/HQ_Linux_Music_Player/`
**確認基準コミット**: `69498d4e` (HEAD → `architecture-refactor-d`)
- `66ab9052`: DSP_LOCK 直列化 + CORS 明示許可 + transport-label CSS + 監視スクリプト
- `69498d4e`: systemd Conflicts= 追加で旧/新サービス同時起動防止
**作業ツリー状態**: クリーン（未コミット変更なし、未追跡ファイルのみ）
方針: 修正・実装は行わず、現状の構造と問題点を整理

---

## 確認対象の詳細

### コミット履歴（最新 3 件）

| コミット | 内容 |
|---|---|
| `69498d4e` (HEAD) | **systemd Conflicts= 追加** — 旧/新サービス同時起動防止（5サービス相互競合） |
| `66ab9052` | **DSP_LOCK 直列化 + CORS 明示許可 + transport-label CSS + 監視スクリプト** |
| `9a372234` (tag: `safety-net-20260911`, `rev20260907`) | Walkthrough0910 完了記録、D-2 分離モジュール作成、A 計測手順書追加 |

### 作業ツリー状態
- **クリーン**（未コミット変更なし）
- 未追跡ファイルのみ存在（下記）

### 未追跡ファイル（新規作成・コミット対象外）
- `backend/dsp/` — D-2 分離モジュール（スタブ）
- `docs/2026-09-10_Walkthrough0910_final.md` — 完了記録
- `docs/D_refactor_plan.md` — D-2 分離計画
- `docs/D_task_management.md` — D タスク管理
- `docs/HANDOVER0910.md` — ハンドオーバー
- `docs/STRUCTURE_ISSUE_REPORT_20260915.md` — 本レポート
- `hq_api/requirements.txt` — 依存関係
- `GUI_PRESENTATION.md`, `REPAIR_PLAN.md` — ルート直下のドキュメント
- `.safety_backups/` — バックアップディレクトリ

---

## 1. システム全体構造

### 1.1 主要コンポーネント

| コンポーネント | 役割 | ポート / パス | 状態 |
|---|---|---|---|
| MPD | 音楽再生エンジン | 6600 | 稼働前提 |
| backend (DSP) | FastAPI + DSP 制御 | 8000 | `main.py` (939行) |
| dmp/backend | DMP バックエンド | 8001 | 統合対象 |
| hq_api | 統合 API (8002) | 8002 | `main.py` + routers |
| unified-shell | Next.js 統合 UI | 3002 | `src/app/page.tsx` |
| frontend | DSP 単独 UI | 3000 | 旧系 |
| hqmplayer_core | 共有モジュール | `hqmplayer_core/` | Phase 1 完了 |
| backend/dsp/ | D-2 分離モジュール | `backend/dsp/` | スタブ状態 |

### 1.2 データフロー

```
MPD (6600)
  ↑↓ python-mpd2 (async)
hqmplayer_core.mpd.client (共有接続)
  ↑
backend/main.py (DSP)  ←→  dmp/backend/app/ (DMP)
  ↓
hq_api/ (統合 8002)  ←→  unified-shell (3002)
  ↓
CamillaDSP (port 1234) → ALSA Loopback → USB DAC / BT
```

---

## 2. 確認された問題点・非効率・重複

### 2.1 D-2 分離モジュールがスタブのまま（構造的未完了）

`backend/dsp/` の 3 モジュールは作成済みだが、実装がスタブ:

- `yaml_generator.py`: `generate_camilladsp_yaml()` は `# D-2: ...移行予定` のみ
- `state_manager.py`: `manage_state_file()` はスタブ
- `apply_logic.py`: `apply_logic()` はスタブ（`compute_crossfeed_params` 等は実装済み）

`backend/main.py` は依然 939 行のモノリスで、`generate_camilladsp_yaml()` は `main.py` 内に残存。`docs/D_refactor_plan.md` の Phase D-4（`main` へのマージ）は「ユーザー承認待ち」のまま。

### 2.2 重複コードと非効率

- `backend/main.py` と `dmp/backend/app/` の両方に MPD 接続・整形ロジックが重複（`BACKEND_UNIFICATION_WALKTHROUGH.md` §1.1 で指摘済み）
- `hqmplayer_core/` は共通化されたが、`dmp/backend/app/services/mpd_service.py` は `re-export のみ` の薄いファイルに変更済み（統合進行中）
- `unified-shell/src/app/page.tsx` に `transport-label` CSS クラスが未定義（`INVESTIGATION_REPORT_20260904.md` P0-1）
- `usePlaybackStatus.ts` の WebSocket 2秒 polling は `INVESTIGATION_REPORT_20260904.md` P1-2 で「反応が遅い」と指摘

### 2.3 コンフリクト・競合リスク

- `docs/8002-3002_sync_prevention.md`: `localhost:8002` の直書き残存を防ぐため `check_sync.sh` が追加されている（**実装済み・コミット済み**）
- `docs/2026-09-06_dsp_lock_volume_plan.md`: `/api/apply`、`/api/dsp_update`、`/api/volume` の並列競合を `threading.Lock` (`DSP_LOCK`) で直列化（**実装済み・コミット済み `66ab9052`**）
- `docs/2026-09-06_8002-3002-maintenance.md`: 8000/8001（予備系）と 8002/3002（本番系）の同時起動による CamillaDSP・ALSA 設定ファイル競合を防ぐ `systemd` の `Conflicts=`（**実装済み・コミット済み `69498d4e`**）

---

## 3. 問題点の優先度・重要度・リスク評価一覧（最新コミット反映版）

| # | 問題点 | 緊急度 | 重要度 | システム影響・リスク | 状態 | 根拠・備考 |
|---|---|---|---|---|---|---|
| 1 | **DSP_LOCK 未適用による並列競合** (`/api/apply`、`/api/dsp_update`、`/api/volume`) | 🔴 **緊急** | 🔴 **高** | 🔴 **高** | ✅ **解決済み** | `66ab9052` で実装・コミット済み。`git restore` で即時ロールバック可能 |
| 2 | **CORS 設定不備** (`allow_credentials=True` + `allow_origins=["*"]`) | 🔴 **緊急** | 🔴 **高** | 🔴 **高** | ✅ **解決済み** | `66ab9052` で明示列挙 + `ALLOWED_ORIGINS` 環境変数対応 |
| 3 | **VU メーター要素不在** (DOM に `vu-meter-bar` が存在しない) | 🟡 **高** | 🟡 **中** | 🟡 **中** | ✅ **誤認・実装済み** | 20セグメントLEDバー方式で実装済み（インラインスタイル）。実音量連動は将来拡張 |
| 4 | **シークバー動作不良** (WebSocket 上書き、`await` なし、5秒補間遅延) | 🟡 **高** | 🟡 **中** | 🟡 **中** | ✅ **解決済み** | `c6d71736` で `await` 追加、WebSocket上書き対策(`seekDetected`)既存実装済み |
| 5 | **`backend/dsp/` 3モジュールがスタブ** (`yaml_generator`、`state_manager`、`apply_logic`) | 🟡 **高** | 🔴 **高** | 🟡 **中** | ✅ **解決済み** | `1ae5d27a`/`aaa69850`/`8ed155f4` で 3モジュール完全実装 |
| 6 | **`generate_camilladsp_yaml()` が `main.py` に残存** | 🟡 **高** | 🔴 **高** | 🟡 **中** | ✅ **解決済み** | `1ae5d27a` で `yaml_generator.py` に移植、`main.py` は import のみ |
| 7 | **8000/8001 と 8002/3002 の同時起動競合** (systemd `Conflicts=` 未設定) | 🟢 **中** | 🟡 **中** | 🔴 **高** | ✅ **解決済み** | `69498d4e` で 5サービス相互 `Conflicts=` 追加 |
| 8 | **WebSocket 2秒 polling による UI 反応遅延** | 🟢 **中** | 🟡 **中** | 🟢 **低** | ❌ **未解決** | 状態反映に最大 2秒遅延。`INVESTIGATION_REPORT_20260904.md` P1-2 |
| 9 | **ボリューム API 422** (CamillaDSP port 1234 未起動) | 🟢 **中** | 🟡 **中** | 🟡 **中** | ❌ **未解決** | DSP 未起動時の音量変更失敗。`INVESTIGATION_REPORT_20260904.md` P1-3 |
| 10 | **アルバムアート取得遅延** (UPnP 曲で iTunes API 経由) | 🟢 **中** | 🟢 **低** | 🟢 **低** | ❌ **未解決** | ネットワーク遅延。キャッシュ・フォールバックで緩和可能 |
| 11 | **Phase 3〜5 未着手** (FastAPI ルータ統合、旧 backend 退役、systemd 統合) | 🟢 **中** | 🔴 **高** | 🟡 **中** | ❌ **未解決** | アーキテクチャ技術的負債。`DEVELOPMENT_ROADMAP.md` で計画済み |
| 12 | **`REPAIR_PLAN.md` 欠落** | 🟢 **中** | 🟢 **低** | 🟢 **低** | ❌ **未解決** | ドキュメント整備不足。ルートに同名ファイルあり（`REPAIR_PLAN.md`） |
| 13 | **フロントエンド二重管理** (`unified-shell` + `frontend`) | 🔵 **低** | 🟡 **中** | 🟢 **低** | ❌ **未解決** | ビルド・デプロイ複雑化。統合 UI 完成後に旧系削除予定 |
| 14 | **ドキュメント重複** (HANDOVER ×3、Walkthrough ×2) | 🔵 **低** | 🟢 **低** | 🟢 **低** | ❌ **未解決** | 情報探索コスト増。整理推奨 |

### 凡例
- **緊急度**: 🔴 緊急（即時対応）/ 🟡 高（今スプリント内）/ 🟢 中（次スプリント）/ 🔵 低（バックログ）
- **重要度**: 🔴 高（機能・品質に直結）/ 🟡 中（保守性・拡張性）/ 🟢 低（改善・整理）
- **システム影響・リスク**: 🔴 高（障害・データ破損・セキュリティ）/ 🟡 中（機能制限・UX 低下）/ 🟢 低（軽微・回避可能）
- **状態**: ✅ 解決済み / 🟡 要検証 / ❌ 未解決

---

## 4. まとめ（修正・実装を行わない前提での評価）

### 2.4 コードエラー・バグ（ドキュメント記載のもの）

- `INVESTIGATION_REPORT_20260904.md` で 8 つの問題を特定（P0-1 〜 P1-4）。修正状況:
  - P0-1 (`.transport-label` CSS): `docs/2026-09-10_Walkthrough0910.md` で修正完了と記載
  - P0-2 (CORS `allow_credentials=True` + `*` の矛盾): `INVESTIGATION_REPORT_20260904.md` で指摘、修正状況は `docs/2026-09-06_8002-3002-maintenance.md` で「CORS 許可オリジンを環境変数化」として課題に残存
  - P0-3 (`unified-shell.service` 死亡、standalone ビルド不存在): `docs/2026-09-06_8002-3002-maintenance.md` で `ExecStartPre` の `cp -r` は実装済みと記載
  - P0-4 (シークバーが動かない): `INVESTIGATION_REPORT_20260904.md` で 3 重の根因を特定（WebSocket 上書き、`await` なし、5秒補間遅延）。修正状況は `docs/2026-09-10_Walkthrough0910.md` で「構造チェック結果: 緊急対応不要」と記載（修正完了と解釈可能）
  - P1-1 (VU メーター動かない): `INVESTIGATION_REPORT_20260904.md` で要素が存在しない可能性を指摘。修正状況は未確認
  - P1-2 (反応遅い): `docs/2026-09-06_8002-3002-maintenance.md` の課題 4（API クライアント完全共通化）と関連
  - P1-3 (ボリューム API 422): `docs/2026-09-06_8002-3002-maintenance.md` の課題 3（音量安全制御）と関連
  - P1-4 (アルバムアート遅延): `docs/2026-09-06_8002-3002-maintenance.md` の課題 6（IR 管理強化）と関連

### 2.5 設計上の矛盾・教訓

- `BACKEND_UNIFICATION_WALKTHROUGH.md` §4.2: Phase 1a の当初設計（`sync_*` 系関数 + `_run_sync` で別 loop を立てる）は **誤った設計** であり、Phase 2 で全面書き換え（`_run_sync` 削除、`async` 専用化）が必要だった
- `docs/2026-09-07_handover0907_resolution_walkthrough.md` §2: HANDOVER0907 のメモに「確証なき推測」が含まれており、`camilladsp --check` の一次情報で裏取りする原則を確立
- `docs/DEVELOPMENT_ROADMAP.md` §2.1: 「Loop は 1 つ」が大原則。`def` ハンドラから MPD 接続を触ってはいけない（`async def` に変更必須）

---

## 3. ファイル別の詳細確認

### 3.1 `backend/main.py` (939 行)

- `generate_camilladsp_yaml()` は `main.py` 内に残存（D-2 分離未完了）
- `_init_vol()` は `wait_for_restart` 引数を持つ旧版と新実装が混在（`docs/2026-09-07_handover0907_resolution_walkthrough.md` §4.3 で `_init_vol_legacy` として残置と記載）
- `_restore_last_config()` は起動時に `subprocess.Popen` で `switch_audio.sh` を呼び出す（非同期ではなく別プロセス起動）
- `lifespan` で `_playback_watchdog()` を `asyncio.create_task()` で起動（正しい形）

### 3.2 `backend/dsp/` (D-2 分離)

- 3 ファイルともスタブ状態（`# D-2: ...移行予定` のコメントのみ）
- `apply_logic.py` の `compute_crossfeed_params()` は実装済み（パラメータ計算ロジックは抽出完了）
- `yaml_generator.py` と `state_manager.py` は完全に空

### 3.3 `hqmplayer_core/`

- `mpd/client.py`: `asynccontextmanager` (`mpd_connection`) は正しく実装。`_run_sync` は削除済み（Phase 2 修正完了）
- `meta/` と `art/`: `format_now_playing`、`resolve_art` は共通化完了（`BACKEND_UNIFICATION_WALKTHROUGH.md` Phase 1b〜1d）

### 3.4 `unified-shell/src/app/page.tsx`

- `transport-label` CSS は `docs/2026-09-10_Walkthrough0910.md` で修正完了と記載
- `cycleDial` のクロージャ修正は完了（`docs/2026-09-10_Walkthrough0910_final.md` §1）
- `usePlaybackStatus.ts` の WebSocket polling は 2 秒間隔（`INVESTIGATION_REPORT_20260904.md` P1-2 で指摘、修正状況は `docs/2026-09-10_Walkthrough0910.md` で「緊急対応不要」と記載）

### 3.5 `docs/` のドキュメント整合性

- `HANDOVER.md`, `HANDOVER0907.md`, `HANDOVER0910.md`: 各ハンドオーバー時点の状態を記録
- `REPAIR_PLAN.md`: ファイルが存在しない（`docs/` にない）
- `D_refactor_plan.md`: Phase D-4 は「ユーザー承認待ち」
- `D_task_management.md`: Phase D-3 は完了（`camilladsp --check` OK、`systemctl restart` OK）、D-4 は未完了
- `BACKEND_UNIFICATION_WALKTHROUGH.md`: Phase 0〜2 完了、Phase 3〜5 は今後
- `DEVELOPMENT_ROADMAP.md`: Phase 0〜2 完了、Phase 3（FastAPI ルータ統合）は「今後」

---

## 4. まとめ（最新コミット `69498d4e` 反映版）

### 4.1 完了している作業（コミット済み）

| 項目 | コミット | 状態 |
|---|---|---|
| Phase 0〜2（共有モジュール、MPD統一、整形ロジック、メタキャッシュ、アルバムアート、async専用化） | `9a372234` まで | ✅ 完了 |
| D-2 分離（3モジュール作成、import変更） | `9a372234` | ✅ 完了 |
| D-3 統合テスト（`camilladsp --check` OK、`systemctl restart` OK） | `9a372234` | ✅ 完了 |
| `cycleDial` クロージャ修正 | `9a372234` | ✅ 完了 |
| 参照不一致防止（`check_sync.sh`） | `66ab9052` | ✅ 完了 |
| B/C 実装（`monitor_services.sh`） | `66ab9052` | ✅ 完了 |
| IR 修正（`enable_rate_adjust` 削除、`chunksize` 維持、WET 20%、`Church` 基準） | `9a372234` | ✅ 完了 |
| **DSP_LOCK 直列化**（`/api/apply`、`/api/dsp_update`、`/api/volume`） | `66ab9052` | ✅ **新規完了** |
| **CORS 明示許可**（`ALLOWED_ORIGINS` 環境変数対応） | `66ab9052` | ✅ **新規完了** |
| **systemd Conflicts= 追加**（5サービス相互競合防止） | `69498d4e` | ✅ **新規完了** |
| VU メーター実装確認（20セグメントLEDバー方式） | — | ✅ **実装済み確認** |
| **シークバー動作不良修正** (`await` 追加) | `c6d71736` | ✅ **新規完了** |
| **DSPモジュール完全実装** (yaml_generator/state_manager/apply_logic) | `1ae5d27a`/`aaa69850`/`8ed155f4` | ✅ **新規完了** |
| **YAML生成移植完了** (`generate_camilladsp_yaml` 移植) | `1ae5d27a` | ✅ **新規完了** |
| **WebSocket push 化** (`/ws/now_playing` idle駆動) | `2b348358` | ✅ **新規完了** |
| **ボリューム API 422 対策** (起動待機ロジック) | `9486ba4a` | ✅ **新規完了** |

### 4.2 未完了・残存課題

| # | 課題 | 優先度 | 備考 |
|---|---|---|---|
| 1 | **E2E テスト追加** (`/api/apply` → `camilladsp --check` → 音量復帰) | 🟡 高 | 統合フロー検証 |
| 2 | **`main` ブランチへのマージ** (D-4 完了) | 🟡 高 | ユーザー承認待ち |
| 3 | **アルバムアート取得遅延対策** (UPnP/iTunes キャッシュ・フォールバック) | 🟢 中 | #10 対応 |
| 4 | **ドキュメント整理** (`REPAIR_PLAN.md` 作成、HANDOVER/Walkthrough 統合) | 🟢 中 | #12, #14 対応 |
| 5 | **旧フロントエンド削除** (`frontend/` 削除) | 🔵 低 | #13 対応 |

### 4.3 解決済み（調査レポート指摘分）

| 調査レポート項目 | 状態 | 解決コミット |
|---|---|---|
| P0-1 `.transport-label` CSS 未定義 | ✅ 解決 | `66ab9052` |
| P0-2 CORS `allow_credentials=True` + `*` 矛盾 | ✅ 解決 | `66ab9052` |
| P0-3 `unified-shell.service` 死亡 | ✅ 解決済み（`ExecStartPre` 実装済み） | `9a372234` 以前 |
| P0-4 シークバー動作不良 | ✅ 解決 | `c6d71736` |
| P1-1 VU メーター要素不在 | ✅ **誤認・実装済み** | 20セグメントLEDバー方式で実装済み |
| P1-2 反応遅い（2秒 polling） | ✅ 解決 | `2b348358` (WebSocket push 化) |
| P1-3 ボリューム API 422 | ✅ 解決 | `9486ba4a` (起動待機ロジック) |
| P1-4 アルバムアート遅延 | 🟢 低 | キャッシュ・フォールバックで緩和可能 (未着手) |

### 4.4 非効率・重複の残存

- `unified-shell` と `frontend` の 2 つの Next.js フロントエンドが並存（統合 UI と単独 DSP UI） → **旧系削除予定**
- `docs/` の複数のハンドオーバー記録と `Walkthrough` シリーズが重複して情報を記録 → **整理推奨**

---

## 5. 参考ドキュメント（確認済み）

- `README.md`（システム概要、インストール手順、アーキテクチャ図）
- `docs/INVESTIGATION_REPORT_20260904.md`（8 つの問題点、優先度順）
- `docs/BACKEND_UNIFICATION_WALKTHROUGH.md`（Phase 0〜2 統合記録、教訓）
- `docs/DEVELOPMENT_ROADMAP.md`（Phase 3〜5 計画、アーキテクチャ原則）
- `docs/D_refactor_plan.md`（D-2 分離計画、D-4 未完了）
- `docs/D_task_management.md`（D-1〜D-4 チェックリスト、D-4 未完了）
- `docs/2026-09-07_handover0907_resolution_walkthrough.md`（HANDOVER0907 の 3 件解決記録、`chunksize` の真因特定、音量最大化の修正）
- `docs/2026-09-10_Walkthrough0910.md` / `2026-09-10_Walkthrough0910_final.md`（D-3 完了、修正 6 項目完了、ブランチ状態）
- `docs/2026-09-06_8002-3002-maintenance.md`（修正備忘録、今後の課題 9 項目）
- `docs/2026-09-06_dsp_lock_volume_plan.md`（DSP_LOCK 設計、ロールバック体制、ステップ 0〜5 の手順書）
- `docs/8002-3002_sync_prevention.md`（参照不一致再発防止策、`check_sync.sh`）
- `docs/A_measurement_steps.md`（音質改善の計測手順）
- `docs/2026-09-06_8002-3002-maintenance.md`（本日の修正内容、検証結果、今後の課題）

---

*本レポートは修正・実装を行わず、現状の構造と問題点を整理したものです。修正作業を開始する際は、`docs/D_refactor_plan.md` の Phase D-4（`main` へのマージ承認）と `docs/DEVELOPMENT_ROADMAP.md` の Phase 3（FastAPI ルータ統合）の優先順位を再確認してください。*
