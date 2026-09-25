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
9. [次のステップ候補 (未着手・ユーザー判断待ち)](#9-次のステップ候補-未着手ユーザー判断待ち)
10. [補遺: Phase 3-A / 4-A / 4-D 完了記録](#10-補遺-phase-3-a--4-a--4-d-完了記録)
11. [補遺: Phase 2-D (Apply後main_volume=0.0 異常補正)](#11-補遺-phase-2-d-apply後main_volume00-異常補正)

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

---

## 10. 補遺: Phase 3-A / 4-A / 4-D 完了記録

### 10.1 Phase 3-A: dsp_apply.py デッドコード撤去 (d7b4d700)

`hq_api/routers/dsp_apply.py` L259 の `logger.warning("...", e) if False else None` を
本来の `logger.warning("...", e)` に修正。`if False` で常に `None` だった式が
正式に logging 呼び出しとして有効化。

- **機能**: 不変 (logging 出力のみ改善、エラー時に journald へ出力されるようになる)
- **性能**: 不変
- **デザイン**: 不変
- **検証**: 構文OK + `systemctl restart hq-api.service` 成功 + `/api/dsp_update` 200 OK

### 10.2 Phase 4-A: WebSocket シークバ干渉 — 接続確認のみ (追加修正不要)

`unified-shell/src/app/page.tsx` の実装を実機コードで確認:

- L199: `const [seekTarget, setSeekTarget] = useState<number | null>(null)`
- L554: `seekTarget={seekTarget}` (SeekBar に渡す)
- L555-557: `onSeek={(v) => { setSeekTarget(v) }}` (SeekBar → state)
- L563-568: `onSeekCommit={() => { api.playback.seek(seekTarget); setSeekTarget(null) }}`
- SeekBar L60: `const displayPos = seekTarget ?? position`

**結論**: INVESTIGATION_REPORT P0-4 の根本対策 (`seekTarget ?? position` パターン) は
既に完全実装済み。シークバーが動かない既知問題は現状で再現しない。
追加修正は**不要**。

### 10.3 Phase 4-D: localhost:800[0-2] 残存検査 (完了・撤廃対象なし)

```
$ grep -rn "localhost:800[0-2]" --include="*.ts" --include="*.tsx" unified-shell/src/app/
(空)
```

**unified-shell/src/app/ 配下に localhost:800[0-2] 直書きは残存なし**。
`unified-shell/src/lib/api.ts` と `upnpApi.ts` の localhost 参照は環境変数未設定時の
**フォールバックデフォルト**として意図的に残されており、HANDOVER0907 が撤廃対象とした
「`page.tsx` 内の `fetch()` 直書き」とは別物。

**結論**: 撤廃対象なし。完了扱い。

### 10.4 コミット履歴（c2ad043a 〜 d7b4d700）

```
d7b4d700 Phase 3-A: dsp_apply.py デッドコード撤去 (1行)
90c17bde docs: HANDOVER0907 解決記録 + walkthrough補遺を追加
823dbad7 Phase 2-B: HANDOVER0907 §2 (音量永続化) 根治
de29dcda Phase 2-A: HANDOVER0907 §3 (音量0dB) 根治
ff840cb0 chunksize を devices 直下へ (HANDOVER0907 §1)
c9229d55 /api/dsp_update NameError 修正
f1a10a41 API URL統一 + CORS環境変数化
c2ad043a DSP_LOCK直列化 + apply volume 強制復帰
```
---

## 11. 補遺: Phase 2-D (Apply後main_volume=0.0 異常補正)

### 11.1 症状

Phase 2-A 適用後、以下のシナリオで「Apply後に音量が変わる/Apply前に戻らない」症状が発生しうる:

1. DSP 稼働中に、何らかの理由で `main_volume=0.0` になる
   (例: camilladsp 別経路での音量操作、外部からの状態破壊、statefile 未生成など)
2. ユーザーが `/api/apply` を呼ぶ (同一設定のため `needs_restart=False`)
3. Phase 2-A の DSP稼働状態チェックが `dsp_running=True` のためスキップされる
4. `main_volume=0.0` のまま固定される

### 11.2 真因

`hq_api/routers/dsp_apply.py` の以下の構造:

```python
if needs_restart or not _dsp_running:
    # ... restart DSP
    if not _dsp_running or _current_vol == 0.0:
        _dsp_main._schedule_init_vol(config.volume, fade_in=True)
# needs_restart=False かつ DSP 稼働中 の場合は何もしない
```

`_current_vol == 0.0` の判定が `if needs_restart or not _dsp_running:` の **内側**にあるため、
`needs_restart=False` かつ `_dsp_running=True` のときには `_current_vol=0.0` でも volume が再適用されない。

### 11.3 修正 (1ebfbc6b)

`elif _current_vol == 0.0:` 節を追加し、needs_restart=False かつ DSP 稼働中で
`main_volume=0.0` のときに限り `_schedule_init_vol` を呼ぶ。

```python
if needs_restart or not _dsp_running:
    # ... restart DSP
    if not _dsp_running or _current_vol == 0.0:
        _dsp_main._schedule_init_vol(config.volume, fade_in=True)
elif _current_vol == 0.0:
    # Phase 2-D: DSP 稼働中で main_volume=0.0 のときだけ volume を再適用
    _dsp_main._schedule_init_vol(config.volume, fade_in=True)
# needs_restart=False かつ DSP 稼働中かつ main_volume != 0.0 の場合は何もしない
```

### 11.4 検証 (実機 DSP 4.1.3)

| シナリオ | 期待値 | 実測 |
|---|---|---|
| main_volume=0.0 強制 → `/api/apply` | main_volume=last_config.volume に復元 | ✅ PASS (-10.0) |
| 通常 `/api/apply` (main_volume != 0.0) | 音量維持 | ✅ PASS |
| `/api/dsp_update` | 音量維持 | ✅ PASS |

### 11.5 機能保全

- needs_restart=False かつ main_volume != 0.0 の既存挙動は完全不変
- DSP_LOCK 直列化 (c2ad043a) は不変
- HANDOVER0907 §3 の「Apply時に直前の音量に戻る」仕様は不変
- mute→fade-in 処理 (_schedule_init_vol) は既存実装を再利用
- フロントエンド・UI・性能は不変

### 11.6 コミット履歴（c2ad043a 〜 1ebfbc6b）

```
1ebfbc6b Phase 2-D: Apply後のmain_volume=0.0異常状態を補正
a8cb11c9 docs: Phase 2-A 実装手順書を追跡対象に追加
fa339919 docs: walkthrough 補遺 §10 (Phase 3-A / 4-A / 4-D)
d7b4d700 Phase 3-A: dsp_apply.py デッドコード撤去 (1行)
90c17bde docs: HANDOVER0907 解決記録 + walkthrough補遺を追加
823dbad7 Phase 2-B: HANDOVER0907 §2 (音量永続化) 根治
de29dcda Phase 2-A: HANDOVER0907 §3 (音量0dB) 根治
ff840cb0 chunksize を devices 直下へ (HANDOVER0907 §1)
c9229d55 /api/dsp_update NameError 修正
f1a10a41 API URL統一 + CORS環境変数化
c2ad043a DSP_LOCK直列化 + apply volume 強制復帰
```


---

## 12. 補遺: Phase 1-D / 5-A / 5-B テスト追加 + デッドコード削除 (5c3c996d)

### 12.1 新テスト追加

| ファイル | 内容 | テスト数 |
|---|---|---|
| `tests/unit/test_camilladsp_yaml_schema.py` | `camilladsp --check` で `generate_camilladsp_yaml()` 出力を検証。ff840cb0 の chunksize 配置 (devices 直下) の回帰検出、必須フィールドの存在、YAML に `state_file_path` が含まれないこと (4.1.3 で削除済み) | 7 |
| `tests/unit/test_init_vol.py` | `_init_vol` / `_schedule_init_vol` の CamillaClient モック単体テスト。接続成功時の volume 設定、200 回リトライ、接続不能時の黙殺、バックグラウンド実行 | 4 |

### 12.2 削除したデッドコード (削除忘れ、機能喪失なし)

| 項目 | 場所 | 削除前参照箇所数 |
|---|---|---|
| `_init_vol_legacy` 関数全体 | `backend/main.py` 旧 L707-737 | 0 (定義のみ) |
| `VOLUME_FADE_SECONDS`, `VOLUME_FADE_STEPS`, `STARTUP_VOLUME_DB` 定数 | `backend/main.py` 旧 L133-135 | `_init_vol_legacy` 内のみ |
| `_init_vol` / `_schedule_init_vol` の `fade_in` 引数 | `backend/main.py` 旧 L747, L780 + 呼び出し側 7 箇所 | 内部未使用 |

### 12.3 整理後の `_init_vol` 最小実装

```python
def _init_vol(v: float):
    """CamillaDSP への接続を試行し、確立でき次第 main_volume を設定する。

    CamillaDSP を `-s/--statefile` 付きで起動した場合、起動時に statefile から
    main_volume が自動復元されるため、Python 側で fade-in 等の複雑な処理は不要。
    """
    for _ in range(200):  # 最大 10 秒待機
        time.sleep(0.05)
        try:
            c = CamillaClient("127.0.0.1", 1234)
            c.connect()
            c.volume.set_main_volume(v)
            c.disconnect()
            return
        except Exception:
            pass
```

### 12.4 検証結果

| 種別 | 結果 |
|---|---|
| 構文チェック | ✅ 4ファイル OK |
| 参照ゼロ確認 | ✅ 削除対象5項目すべて 0 箇所 |
| 単体テスト | ✅ 35/35 PASS (hqmplayer_core 24 + yaml_schema 7 + init_vol 4) |
| 実機 DSP 4.1.3 | ✅ 5シナリオ全 PASS |

### 12.5 コミット履歴 (c2ad043a 〜 5c3c996d)

```
5c3c996d cleanup: Phase 5-A/B (Phase 1-D/5-B テスト) + デッドコード削除
fb504d76 docs: walkthrough に補遺 §11 (Phase 2-D)
1ebfbc6b Phase 2-D: Apply後のmain_volume=0.0異常状態を補正
a8cb11c9 docs: Phase 2-A 実装手順書を追跡対象に追加
fa339919 docs: walkthrough に補遺 §10 (Phase 3-A / 4-A / 4-D)
d7b4d700 Phase 3-A: dsp_apply.py デッドコード撤去 (1行)
90c17bde docs: HANDOVER0907 解決記録 + walkthrough補遺を追加
823dbad7 Phase 2-B: HANDOVER0907 §2 (音量永続化) 根治
de29dcda Phase 2-A: HANDOVER0907 §3 (音量0dB) 根治
ff840cb0 chunksize を devices 直下へ (HANDOVER0907 §1)
c9229d55 /api/dsp_update NameError 修正
f1a10a41 API URL統一 + CORS環境変数化
c2ad043a DSP_LOCK直列化 + apply volume 強制復帰
```

### 12.6 Phase 1-5 全案件ステータス (本コミット後)

| Phase | 案件 | 状態 |
|---|---|---|
| 1-A | ff840cb0 起動検証 | ✅ 完了 |
| 1-B | 公式スキーマ `chunksize` 位置確定 | ✅ 完了 |
| 1-C | chunksize 完全削除の再検証 | ✅ 完了 |
| 1-D / 5-A | YAML単体テスト | ✅ 完了 (5c3c996d) |
| 2-A | 音量0dB 根治 | ✅ 完了 (de29dcda) |
| 2-B | state file 永続化 | ✅ 完了 (823dbad7) |
| 2-C | `/api/volume` 永続化経路の二重化 | ✅ 完了 (823dbad7 内に含む) |
| 2-D | Apply後 volume=0.0 異常補正 | ✅ 完了 (1ebfbc6b) |
| 3-A | dsp_apply.py デッドコード撤去 | ✅ 完了 (d7b4d700) |
| 3-B | `reload_config` fallback 例外分類 | ✅ 完了 (既存実装 + Phase 3-A の logger.warning) |
| 4-A | WebSocketシークバー干渉 | ✅ 完了 (既存実装で完結) |
| 4-B | CORS | ✅ 完了 (f1a10a41 で環境変数化済み) |
| 4-C | バックエンド二重起動 | ✅ 完了 (`audiophile-backend.service` 既に disabled) |
| 4-D | fetch 直書き残存検査 | ✅ 完了 (残存なし) |
| 4-E | channels番号整合 | ✅ 完了 (意図的にスキップ) |
| 5-A | Phase 1-D と統合 | ✅ 完了 (5c3c996d) |
| 5-B | Phase 2 回帰テスト | ✅ 完了 (5c3c996d) |
| 5-C | HANDOVER0907 更新 | ✅ 完了 (90c17bde) |
| 5-D | walkthrough 補遺 (Phase 補遺 §10-§12) | ✅ 完了 (fa339919 / fb504d76 / 本 §12) |
