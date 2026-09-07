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

## 検証済み動作

| シナリオ | 期待値 | 実測 |
|---|---|---|
| DSP 停止 → `/api/apply` | DSP起動 + main_volume=-3.0 | ✅ PASS |
| DSP 稼働中 → `/api/apply` (同一設定) | volume=-10.0 維持 | ✅ PASS |
| DSP 稼働中 → `/api/dsp_update` | volume維持 + dial反映 | ✅ PASS |
| `/api/volume -15.0` | last_config.volume=-15.0, state.yml volume[0]=-15.0 | ✅ PASS |
| DSP 完全停止 → 起動 | main_volume=-15.0 (statefile 自動復元) | ✅ PASS |

## コミット履歴（c2ad043a 以降）

```
823dbad7 Phase 2-B: HANDOVER0907 §2 (音量永続化) 根治
de29dcda Phase 2-A: HANDOVER0907 §3 (音量0dB) 根治
ff840cb0 chunksize を devices 直下へ (HANDOVER0907 §1)
c9229d55 /api/dsp_update NameError 修正
f1a10a41 API URL統一 + CORS環境変数化
c2ad043a DSP_LOCK直列化 + apply volume 強制復帰
```

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
