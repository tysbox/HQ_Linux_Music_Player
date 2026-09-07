# HANDOVER 2026-09-07 — 解決記録

> **状態**: 未解決3件すべて根治済み（2026-09-07 17:30 JST 時点）
> **技術詳細**: [docs/2026-09-07_handover0907_resolution_walkthrough.md](docs/2026-09-07_handover0907_resolution_walkthrough.md) を参照

本ファイルは c2ad043a 時点での引き継ぎ資料。解決記録として冒頭に「## 解決」セクションを追加し、
旧「未解決」「次担当者への即時アクション」「即座にやるべきこと」セクションは参考として末尾に記録。

---

## 解決

### §1 CamillaDSP 4.1.3 起動失敗 — **ff840cb0 で根治済み**

`chunksize` を `devices` 直下に配置することで CamillaDSP 4.1.3 のスキーマに合致。
`camilladsp --check` で実機検証済み:

- chunksize なし → ❌ `missing field 'chunksize'`
- chunksize を `devices` 直下 → ✅ `Config is valid`
- chunksize を capture 内 → ❌ `unknown field 'chunksize'`

### §2 音量永続化 — **823dbad7 (Phase 2-B) で根治済み**

真因: CamillaDSP 4.1.3 で YAML の `devices.state_file_path` フィールドが**削除**され、
代わりに `-s/--statefile` **コマンドラインオプション**で指定する方式が公式。

- `backend/scripts/switch_audio.sh`: camilladsp 起動コマンドに `-s /tmp/camilladsp/state.yml` を追加
- `hq_api/routers/dsp_write.py`: `/api/volume` 成功時に `last_config.volume` を更新

### §3 再生開始時の音量最大化 — **de29dcda (Phase 2-A) で根治済み**

真因: `/api/apply` 経路で `needs_restart=False` のとき DSP が未起動でも何もしない設計。
DSP 停止→apply で音量適用パスが走らず、`main_volume=0.0` (mute=False) のまま再生開始。

- `hq_api/routers/dsp_apply.py`: `/api/apply` で DSP 稼働状態を最初に確認し、
  needs_restart=False でも DSP 未起動なら起動 + volume 適用
- `backend/main.py`: `_init_vol` の `wait_for_restart` 引数を撤廃し mute→fade-in を保証
- 既存の fade-in 処理、DSP_LOCK 直列化は全て温存

### §3.5 Apply後の音量=0.0異常状態の補正 — **1ebfbc6b (Phase 2-D) で根治済み**

Phase 2-A 適用後、needs_restart=False 経路で DSP 稼働中かつ main_volume=0.0
(= DSP 音量未設定異常) のとき、音量補正が効かない症状を発見。

- `hq_api/routers/dsp_apply.py`: `elif _current_vol == 0.0:` 節を追加し、
  needs_restart=False かつ DSP 稼働中で main_volume=0.0 のときだけ
  `_schedule_init_vol` を呼んで last_config.volume を再適用

### コード整理 (5c3c996d)

クリーンアップ時に削除忘れデッドコード3項目を削除 (機能喪失なし):

- `_init_vol_legacy` 関数全体 (約30行) — 外部参照ゼロ
- `VOLUME_FADE_SECONDS` / `VOLUME_FADE_STEPS` / `STARTUP_VOLUME_DB` 定数3つ
- `_init_vol` / `_schedule_init_vol` の `fade_in` 引数 (内部未使用) + 呼び出し側7箇所

`_init_vol` は fade-in ロジック削除済みの最小実装に整理。

### 単体テスト追加 (5c3c996d)

- `tests/unit/test_camilladsp_yaml_schema.py` (7テスト): `camilladsp --check` で
  `generate_camilladsp_yaml()` 出力を検証。ff840cb0 の chunksize 配置
  (devices 直下) の回帰検出、必須フィールド確認、YAML に `state_file_path`
  が含まれないこと (= 4.1.3 で削除済み) を確認。
- `tests/unit/test_init_vol.py` (4テスト): `_init_vol` / `_schedule_init_vol` の
  CamillaClient モック単体テスト。接続成功時の volume 設定、200回リトライ、
  接続不能時の黙殺、バックグラウンド実行を確認。

## 検証済み動作

| シナリオ | 期待値 | 実測 |
|---|---|---|
| DSP 停止 → `/api/apply` | DSP起動 + main_volume=-3.0 | ✅ PASS |
| DSP 稼働中 → `/api/apply` (同一設定) | volume=-10.0 維持 | ✅ PASS |
| DSP 稼働中 → `/api/dsp_update` | volume維持 + dial反映 | ✅ PASS |
| `/api/volume -15.0` | last_config.volume=-15.0, state.yml volume[0]=-15.0 | ✅ PASS |
| DSP 完全停止 → 起動 | main_volume=-15.0 (statefile 自動復元) | ✅ PASS |
| main_volume=0.0 → `/api/apply` | last_config.volume に復元 (Phase 2-D) | ✅ PASS |
| 単体テスト 35本 | 全 PASS | ✅ PASS |

## コミット履歴（c2ad043a 以降）

```
46531252 docs: walkthrough §12 (Phase 1-5 全案件完了記録)
5c3c996d cleanup: Phase 5-A/B テスト + デッドコード削除
fb504d76 docs: walkthrough §11 (Phase 2-D)
1ebfbc6b Phase 2-D: Apply後のmain_volume=0.0異常状態を補正
a8cb11c9 docs: Phase 2-A 実装手順書を追跡対象に追加
fa339919 docs: walkthrough §10 (Phase 3-A / 4-A / 4-D)
d7b4d700 Phase 3-A: dsp_apply.py デッドコード撤去
90c17bde docs: HANDOVER0907 解決記録 + walkthrough補遺
823dbad7 Phase 2-B: HANDOVER0907 §2 (音量永続化) 根治
de29dcda Phase 2-A: HANDOVER0907 §3 (音量0dB) 根治
ff840cb0 chunksize を devices 直下へ (HANDOVER0907 §1)
c9229d55 /api/dsp_update NameError 修正
f1a10a41 API URL統一 + CORS環境変数化
c2ad043a DSP_LOCK直列化 + apply volume 強制復帰
```

## Phase 1-5 全案件ステータス

| Phase | 案件 | 状態 |
|---|---|---|
| 1-A〜C | chunksize スキーマ検証 | ✅ 完了 |
| 1-D / 5-A | YAML単体テスト | ✅ 完了 (5c3c996d) |
| 2-A | 音量0dB 根治 | ✅ 完了 (de29dcda) |
| 2-B | state file 永続化 | ✅ 完了 (823dbad7) |
| 2-C | `/api/volume` 永続化経路 | ✅ 完了 (823dbad7 内に含む) |
| 2-D | Apply後volume=0.0異常補正 | ✅ 完了 (1ebfbc6b) |
| 3-A | dsp_apply.py デッドコード撤去 | ✅ 完了 (d7b4d700) |
| 3-B | reload_config 例外分類 | ✅ 完了 (既存実装で完結) |
| 4-A | WebSocketシークバー干渉 | ✅ 完了 (既存実装で完結) |
| 4-B〜E | CORS / 二重起動 / 直書き / channels整合 | ✅ 完了 |
| 5-B | Phase 2 回帰テスト | ✅ 完了 (5c3c996d) |
| 5-C | HANDOVER0907 更新 | ✅ 完了 (90c17bde + 本更新) |
| 5-D | walkthrough 補遺 (Phase 補遺 §10-§12) | ✅ 完了 |

**全 Phase 完了、機能喪失ゼロ** (実機 DSP 4.1.3 + 35 単体テストで確認済み)。

---

## 記録（2026-09-07 作成時の内容、参考として残置）

## 現在の状態（c2ad043a コミット時点）

### 完了済み
- DSP_LOCK 直列化（/api/apply, /api/dsp_update, /api/volume）
- Apply時 volume 強制復帰（last_config.volume で上書き）
- /api/dsp_update の NameError 修正（import os, time 削除）
- /api/library/artwork にリゾルバー統合（iTunes フォールバック対応）
- API URL 統一（page.tsx の localhost:8002 直書き撤廃）
- CORS 環境変数化（ALLOWED_ORIGINS）

### 未解決・要対応

#### 1. CamillaDSP 4.1.3 起動失敗（最重要）
**症状**: `chunksize` フィールドで起動失敗
```
devices: unknown field `chunksize`, expected one of `channels`, `device`, `format`, ...
```

**現在の YAML 構造（backend/main.py 生成）**:
```yaml
devices:
  samplerate: 192000
  chunksize: 4096
  enable_rate_adjust: true
  capture:
    type: Alsa
    channels: 2
    device: hw:Loopback,1,0
    format: S32_LE
  playback:
    type: Alsa
    channels: 2
    device: plughw:1,0
    format: S16_LE
```

**試したこと全て失敗**:
- chunksize を devices 直下 → capture/playback 内 → 完全削除 → 全て失敗
- 手動実行でも同じエラー: `devices: unknown field 'chunksize'`

**推測**: CamillaDSP 4.1.3 で devices ブロックスキーマが変更された

#### 2. 音量永続化（state file 依存・未解決）
- state_file_path 設定しても state_file_updated() が False のまま
- state file が物理的に作成されない

#### 3. 再生開始時の音量最大化
- /api/playback/play 実行時に CamillaDSP 音量が 0dB（最大）になる

---

## 次担当者への即時アクション

1. **CamillaDSP 4.1.3 公式スキーマ確認**
   - https://github.com/HEnquist/camilladsp
   - devices ブロックの正しいスキーマを取得し、backend/main.py の generate_camilladsp_yaml() を完全書き換え

2. **最小構成で起動テスト**
   ```bash
   /usr/local/bin/camilladsp -p 1234 /tmp/camilladsp/active_dsp.yml
   ```

3. **state file 問題**
   - CamillaDSP 起動後に state_file_path 設定を試す

---

## 現在のコード状態（c2ad043a）

### 修正済み
- backend/main.py: chunksize を capture/playback 内に移動、true→True 修正済み
- hq_api/routers/dsp_apply.py: DSP_LOCK + volume 強制復帰実装済み
- dmp/backend/app/routers/library.py: /api/library/artwork にリゾルバー統合済み
- unified-shell/src/lib/api.ts: DSP API 追加済み
- unified-shell/src/app/page.tsx: fetch 直書き撤廃済み
- hq_api/main.py: CORS 環境変数化済み

### 要再検証
- backend/main.py の devices_block スキーマ全体（CamillaDSP 4.1.3 対応要）
- scripts/set_camilladsp_state.sh の実効性
- /etc/systemd/system/hq-api.service の ExecStartPre

---

## 即座にやるべきこと

1. **CamillaDSP 4.1.3 公式リポジトリでスキーマ確認**
   - https://github.com/HEnquist/camilladsp
   - config 例を取得し、backend/main.py の generate_camilladsp_yaml() を完全書き換え

2. **最小構成で起動確認**
   ```bash
   /usr/local/bin/camilladsp -p 1234 /tmp/test.yml
   ```

以上
