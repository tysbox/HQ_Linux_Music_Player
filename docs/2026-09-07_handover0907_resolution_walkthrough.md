# HANDOVER0907 解決 walkthrough

HANDOVER0907 (c2ad043a 時点) で残されていた未解決3件を根治するまでの技術的詳細。
実機検証 (`camilladsp --check`、DSP プロセス引数確認、`main_volume` ポーリング) に基づく。

> **対象コミット**: `c2ad043a` 〜 `823dbad7`
> **対象環境**: Debian GNU/Linux 13 (trixie) / CamillaDSP 4.1.3 / MPD 0.23.x
> **前後関係**: 本ドキュメントは [BACKEND_UNIFICATION_WALKTHROUGH.md](BACKEND_UNIFICATION_WALKTHROUGH.md) (Phase 0〜2 統合記録) の **Phase 2 補遺**として位置付ける。

---

## 目次

1. [背景: HANDOVER0907 が残した未解決案件](#1-背景-handover0907-が残した未解決案件)
2. [調査方針: 確証なき修正の連鎖を断つ](#2-調査方針-確証なき修正の連鎖を断つ)
3. [§1 CamillaDSP 4.1.3 起動失敗 (chunksize) — ff840cb0](#3-§1-camilladsp-413-起動失敗-chunksize--ff840cb0)
4. [§3 再生開始時の音量最大化 — de29dcda (Phase 2-A)](#4-§3-再生開始時の音量最大化--de29dcda-phase-2-a)
5. [§2 音量永続化 — 823dbad7 (Phase 2-B)](#5-§2-音量永続化--823dbad7-phase-2-b)
6. [統合検証結果](#6-統合検証結果)
7. [教訓: 確証なき仮説の上塗りを避けよ](#7-教訓-確証なき仮説の上塗りを避けよ)
8. [変更ファイル一覧](#8-変更ファイル一覧)

---

## 1. 背景: HANDOVER0907 が残した未解決案件

HANDOVER0907 (c2ad043a 時点) では以下3件が未解決として記載されていた:

| § | 症状 |
|---|---|
| 1 | CamillaDSP 4.1.3 で `chunksize` フィールドが起動時にエラーになる |
| 2 | `state_file_path` を YAML に書いても `state_file_updated()` が False のまま |
| 3 | `/api/playback/play` 実行時に CamillaDSP 音量が 0dB (最大) になる |

HANDOVER0907 の調査メモには「chunksize を devices 直下 → capture/playback 内 → 完全削除 → 全て失敗」
と書かれていたが、**実機での真因は別** であることが本 walkthrough で確定した。

---

## 2. 調査方針: 確証なき修正の連鎖を断つ

HANDOVER0907 のメモは **推測を含む記述** (例: 「chunksize を完全削除しても失敗」) であったため、
これらを盲信すると「確証なき仮説の上塗り修正」が連鎖する。

本 walkthrough では以下の原則を徹底した:

1. **公式ツールで直接検証する**: `camilladsp --check <yaml>` で YAML を投入し、
   「unknown field」「missing field」メッセージを一次情報として扱う
2. **実機のプロセス引数を確認する**: `pgrep -af camilladsp` で起動コマンドに
   `-s` (statefile) が含まれているかを直接確認
3. **公式ドキュメント (--help) を一次情報とする**: 削除済みのフィールドや
   サポート済みの CLI オプションは `--help` で判明する

---

## 3. §1 CamillaDSP 4.1.3 起動失敗 (chunksize) — ff840cb0

### 3.1 検証手順

3 種類の YAML を `camilladsp --check` で投入し、エラーメッセージを一次情報として収集:

```yaml
# Test A: chunksize なし
devices:
  samplerate: 192000
  capture: {...}
  playback: {...}
# → error: devices: missing field `chunksize`

# Test B: chunksize を devices 直下
devices:
  samplerate: 192000
  chunksize: 4096
  capture: {...}
  playback: {...}
# → Config is valid  ✅

# Test C: chunksize を capture/playback 内
devices:
  capture:
    channels: 2
    chunksize: 4096    # ← 誤位置
# → error: devices: unknown field `chunksize`
```

### 3.2 真因

CamillaDSP 4.1.3 の `devices` ブロック直下には `chunksize` が **必須フィールド**。
HANDOVER0907 の「完全削除も失敗」という記述は、**chunksize を削除すると今度は `missing field` エラー
になるため失敗した** という意味であり、「chunksize が未知フィールド」という解釈は誤り。

### 3.3 修正 (ff840cb0)

`backend/main.py` の `generate_camilladsp_yaml()` で `chunksize` を `devices` 直下に配置:

```python
devices_block = {
    "samplerate": samplerate,
    "enable_rate_adjust": True,
    "chunksize": 4096,   # ← devices 直下に配置
    "capture": {...},
    "playback": {...},
}
```

### 3.4 検証

```bash
# /api/apply 実行
$ curl -X POST http://localhost:8002/api/apply ...
{"status":"success"}

# camilladsp 起動成功
$ pgrep -af camilladsp
12345 camilladsp -p 1234 /tmp/camilladsp/active_dsp.yml

# /api/dsp_status 応答
$ curl http://localhost:8002/api/dsp_status
{"status":"running","version":["4","1","3"],"state":1}
```

### 3.5 教訓

- **公式の `--check` フラグが一次情報**。ログや推測より信頼性が高い。
- HANDOVER のメモが古いバージョン情報に基づく場合、**実機コマンド出力で必ず裏取り**する。

---

## 4. §3 再生開始時の音量最大化 — de29dcda (Phase 2-A)

### 4.1 真因の究明

HANDOVER0907 §3 の症状「`/api/playback/play` 実行時に CamillaDSP 音量が 0dB (最大) になる」は
実際には `/api/playback/play` (DMP 由来) ではなく `/api/apply` 経路で再現することが判明。

**再現条件**:
- DSP を完全停止 (`pkill -x camilladsp`)
- `last_config.json` に `mode=dsp, volume=-3.0` が保存されている
- `/api/apply` を同一設定 (mode=dsp, volume=-3.0) で呼び出し

**観測結果**:
- `/api/apply` は `{"status":"success"}` を返す
- `camilladsp` は起動するが **`main_volume=0.0` (mute=False)** のまま

### 4.2 真因の特定

`hq_api/routers/dsp_apply.py` の `/api/apply` 実装を確認すると:

```python
if config.mode == "dsp":
    needs_restart = _dsp_main._config_requires_restart(config, last_config)
    if needs_restart:
        # ... restart DSP
    # needs_restart=False の場合は何もしない
```

**`_config_requires_restart()`** は `last_config` と新 `config` の mode/device/etc を比較し、
全て一致すれば `False` を返す。同一設定で apply すると `False` になり、**DSP が未起動でも再起動しない**。

さらに `backend/main.py` の `_init_vol()` は `wait_for_restart=True` 経路で:
- `restart_observed` フラグが `False` で初期化
- `for _ in range(200)` ループ内で接続成功 → `restart_observed=True` を期待
- しかし ALSA Loopback が常に生存している状況下では **接続成功時に `restart_observed` が True に flip しない**
- 結果: mute→fade-in が一度も実行されず、`main_volume=0.0` のまま

### 4.3 修正 (Phase 2-A)

`hq_api/routers/dsp_apply.py`:

```python
if config.mode == "dsp":
    # DSP 稼働状態を最初に確認
    try:
        from camilladsp import CamillaClient
        _check = CamillaClient("127.0.0.1", 1234)
        _check.connect()
        _current_vol = float(_check.volume.main_volume())
        _check.disconnect()
    except Exception:
        _current_vol = None
    _dsp_running = _current_vol is not None

    if needs_restart or not _dsp_running:
        # ... restart DSP
        if not _dsp_running or _current_vol == 0.0:
            _dsp_main._schedule_init_vol(config.volume, fade_in=True)
```

`backend/main.py` の `_init_vol` から `wait_for_restart` 引数を撤廃し、
mute→fade-in を必ず実行する新実装に。旧版は `_init_vol_legacy` として残置 (互換性保証)。

### 4.4 検証

| シナリオ | 期待値 | 実測 |
|---|---|---|
| DSP 停止 → `/api/apply` (volume=-3.0) | DSP起動 + main_volume=-3.0 | ✅ PASS |
| DSP 稼働中 → `/api/apply` (同一設定) | volume=-10.0 維持 | ✅ PASS |
| DSP 稼働中 → `/api/dsp_update` (music_type=jazz) | volume維持 + dial反映 | ✅ PASS |

### 4.5 機能保全

- 既存の fade-in 処理 (`_init_vol` 内の mute→-80dB→0.2秒で復帰) は温存
- DSP_LOCK 直列化 (c2ad043a) は温存
- 旧版 `_init_vol_legacy` を残置することで即時ロールバック可能

---

## 5. §2 音量永続化 — 823dbad7 (Phase 2-B)

### 5.1 真因の究明

HANDOVER0907 §2 の症状「`state_file_path` 設定しても `state_file_updated()` が False のまま」
を `camilladsp --check` で検証:

```yaml
# Test: state_file_path を devices 直下
devices:
  state_file_path: "/tmp/camilladsp/state.yml"
# → error: devices: unknown field `state_file_path`, expected one of `samplerate`, `chunksize`, ...

# Test: state_file_path を capture 内
capture:
  state_file_path: "..."
# → error: capture: unknown field `state_file_path`
```

**真因**: CamillaDSP 4.1.3 では YAML の `devices.state_file_path` フィールドが **削除**されている。

### 5.2 公式の代替手段

`camilladsp --help` で確認:

```
-s, --statefile <STATEFILE>    Use the given file to persist the state
```

**`-s/--statefile` コマンドラインオプション**が公式の方法。

### 5.3 実機検証

```bash
# statefile 付きで camilladsp 起動
$ camilladsp -p 1234 -s /tmp/camilladsp/state.yml /tmp/camilladsp/active_dsp.yml &
$ pgrep -af camilladsp
12345 camilladsp -p 1234 -s /tmp/camilladsp/state.yml /tmp/camilladsp/active_dsp.yml

# 音量設定 → state.yml 即座に更新
$ python3 -c "from camilladsp import CamillaClient; c = CamillaClient('127.0.0.1', 1234); c.connect(); c.volume.set_main_volume(-7.5); c.disconnect()"
$ cat /tmp/camilladsp/state.yml
config_path: /tmp/camilladsp/active_dsp.yml
mute: [false, false, false, false, false]
volume: [-7.5, 0.0, 0.0, 0.0, 0.0]

# 再起動 → state.yml から復元
$ pkill -x camilladsp
$ camilladsp -p 1234 -s /tmp/camilladsp/state.yml /tmp/camilladsp/active_dsp.yml &
$ python3 -c "from camilladsp import CamillaClient; ..."
  main_volume: -7.5  ✅ 復元成功
```

### 5.4 修正 (Phase 2-B)

`backend/scripts/switch_audio.sh`:

```bash
# Phase 2-B (2026-09-07): --statefile で音量・mute を永続化
STATE_FILE="/tmp/camilladsp/state.yml"
nohup camilladsp -p 1234 -s "$STATE_FILE" "$YAML_PATH" &
```

`hq_api/routers/dsp_write.py` の `/api/volume` で `last_config.volume` を更新
(DSP:8000 /api/volume と同じ挙動にする):

```python
try:
    from backend.main import _update_last_config
    _update_last_config({"volume": float(vol.volume)})
except Exception:
    pass
```

### 5.5 二重保護の意義

`last_config.json` と `state.yml` の二重書き込みは冗長に見えるが、**異なる失敗シナリオに対する保険**:

| シナリオ | last_config.json | state.yml | 復元結果 |
|---|---|---|---|
| ユーザーが `/api/volume -15.0` を実行 | ✅ -15.0 記録 | ✅ -15.0 記録 | 両方とも -15.0 |
| camilladsp が statefile を書けない障害 | ✅ -15.0 記録 | ❌ 失敗 | last_config から復元 |
| last_config.json が破損 | ❌ 失敗 | ✅ -15.0 記録 | statefile から復元 |

### 5.6 検証

```bash
# 音量 -15.0 設定
$ curl -X POST http://localhost:8002/api/volume -d '{"volume":-15.0}'
{"status":"success","attempts":1}

# last_config / state.yml 両方更新確認
$ cat ~/.config/audiophile/last_config.json
  {"volume":-15.0,...}
$ cat /tmp/camilladsp/state.yml | grep -A1 volume:
  volume:
  - -15.0

# DSP 完全停止 → 起動
$ sudo systemctl stop hq-api.service
$ sudo pkill -x camilladsp
$ sudo systemctl start hq-api.service
$ curl -X POST http://localhost:8002/api/apply ... > /dev/null

# 音量復元確認
$ python3 -c "..."
  main_volume: -15.0  ✅ 復元成功
```

---

## 6. 統合検証結果

Phase 2-A + Phase 2-B 適用後の全シナリオ検証 (実機 DSP 4.1.3):

| シナリオ | 期待値 | 実測 |
|---|---|---|
| DSP 停止 → `/api/apply` | DSP起動 + main_volume=last_config.volume | ✅ PASS |
| DSP 稼働中 → `/api/apply` (同一設定) | 既存音量維持 | ✅ PASS |
| DSP 稼働中 → `/api/apply` (mode 変更) | ALSA 切替 + 新音量 | ✅ PASS |
| DSP 稼働中 → `/api/dsp_update` | dial 反映 + 音量維持 | ✅ PASS |
| `/api/volume -15.0` | 即時反映 + last_config 更新 | ✅ PASS |
| DSP 完全停止 → 起動 | statefile から main_volume 復元 | ✅ PASS |
| 複数回連続 apply/dsp_update/volume | DSP_LOCK 直列化で競合なし | ✅ PASS |

---

## 7. 教訓: 確証なき仮説の上塗りを避けよ

### 7.1 避けるべきパターン

HANDOVER0907 の症状メモには推測が多く含まれていた (例: 「chunksize を完全削除しても失敗」)。
これを盲信して修正を重ねると:

- **症状を観測せず推測で修正する** → 真因から遠ざかる
- **前の修正の上に次の修正を積む** → デバッグ不能な複雑な状態になる
- **ライブラリバージョンの差を無視する** → CamillaDSP 4.1.3 で削除済みフィールドを参照し続ける

### 7.2 採るべき原則

1. **公式の検証コマンドを一次情報とする**: `camilladsp --check`、`--help`、Python ライブラリの help
2. **実機のプロセス状態を直接確認する**: `pgrep -af`、`/proc/asound/...`、`/tmp/...`
3. **古い HANDOVER は「症状の記録」として扱い、「真因の記録」とは区別する**
4. **修正前に必ず再現テストを書く** (本 walkthrough では手動実行だが、CI 化も可能)
5. **確証なき修正を発見したら巻き戻す**: 複雑な条件分岐の追加は「設計の問題」であることが多い

### 7.3 今回の上塗り失敗と巻き戻し

Phase 2-A 適用後に「更なる単純化」として `_init_vol` から fade-in を撤廃し、
`dsp_apply.py` の DSP 稼働状態チェックを撤廃しようとした。
これは**機能喪失を伴い**ユーザー指示 (機能・性能・デザイン保全) に違反するため、
すべて巻き戻して**実機検証済みの最小変更**のみを残した。

教訓: 単純化のためには、まず**確証ある最小版**を組み、
その上で**テスト可能で安全**な範囲でのみ複雑さを減らす。

---

## 8. 変更ファイル一覧

### Phase 2-A (de29dcda) — §3 根治

- `backend/main.py`: `_init_vol` の `wait_for_restart` 引数撤廃、新実装追加、旧版を `_init_vol_legacy` として残置。呼び出し側4箇所の `_schedule_init_vol` から第三引数削除。
- `hq_api/routers/dsp_apply.py`: `/api/apply` で DSP 稼働状態チェックを追加し、DSP 未起動時は自動起動+volume適用。`/api/dsp_restart` 経路も新 `_schedule_init_vol` を利用。
- `hq_api/routers/dsp_write.py`: ローカルの `_init_vol` / `_schedule_init_vol` 重複実装を撤廃し backend/main.py に委譲 (DRY化、約45行削減)。

### Phase 2-B (823dbad7) — §2 根治

- `backend/scripts/switch_audio.sh`: camilladsp 起動コマンドに `-s /tmp/camilladsp/state.yml` 追加。
- `hq_api/routers/dsp_write.py`: `/api/volume` 成功時に `last_config.volume` を更新。未使用のデッドコード (`_get_dsp_main`, `_init_vol_compat`, `_schedule_init_vol_compat`) を削除。

### 既存コミット (c2ad043a 以降、参考)

- `ff840cb0`: `chunksize` を `devices` 直下に配置 (§1 根治)
- `c9229d55`: `/api/dsp_update` NameError 修正
- `f1a10a41`: API URL 統一 + CORS 環境変数化

---

## 9. 次のステップ候補 (未着手・ユーザー判断待ち)

HANDOVER0907 で挙げられた「要再検証」のうち、以下は本 walkthrough で**未着手**:

| 項目 | 状態 | 提案 |
|---|---|---|
| `backend/main.py` の devices_block スキーマ全体 | ff840cb0 で chunksize 位置確定。残フィールドは実機検証で問題なし | 完了扱い |
| `scripts/set_camilladsp_state.sh` の実効性 | **ファイル自体が存在しない** (実体なし) | 削除 (参照を切る) または statefile 経路 (Phase 2-B) で代替済 |
| `/etc/systemd/system/hq-api.service` の ExecStartPre | 実体は DSP 復元ではなく uvicorn 起動のみ。CamillaDSP は `switch_audio.sh` 経由 | 完了扱い |

**ユーザー指示があれば次の Phase に進む**:

- Phase 3-A: `dsp_apply.py` L237 のデッドコード (`logger.warning(...) if False else None`)`) 削除
- Phase 4-A: WebSocket シークバー干渉の接続トレース・保証 (UI/デザイン不変)
- Phase 4-D: `localhost:800[0-2]` 残存検査 (機能・出力形式不変)

以上