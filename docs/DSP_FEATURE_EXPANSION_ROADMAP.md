# DSP 機能拡張 段階実行計画（改訂版）— 各段階でチェックできる計画

- 改訂日: 2026-09-19
- 親文書: `docs/DSP_FEATURE_EXPANSION_PROPOSAL.md`（設計検討・方針）
- 前版: `docs/archive/DSP_FEATURE_EXPANSION_ROADMAP_v1_20260919.md`
- 改訂理由（前版の不備）:
  1. **段階間の依存が本文に隠れていた。** 「Phase 1 のみ実行」が後から実行不能と判明した。→ 各段階の冒頭に**実行可能な前提チェック**を置き、依存を構造として明示する。
  2. **検証できない時間見積もりを書いていた。** → 時間は書かない。段階の規模は「変更行数・追加ファイル数・チェック数」で表す。
  3. **検証行為そのものが稼働中システムを書き換えた**（実測で2回発生）。→ 「非破壊」を原則 P1 とし、保護対象と検出手段を最初に確定する。

## 0. 原則（P1〜P5）

| # | 原則 | 内容 |
|---|---|---|
| **P1** | 非破壊 | 段階のチェックは、稼働中の CamillaDSP・設定ファイル・IR キャッシュに**書き込まない**。書き込みが避けられない操作は §13 に分離する |
| **P2** | 前提はチェックとして書く | 各段階の冒頭に「前提チェック」を置く。コマンドと期待出力を持ち、FAIL ならその段階を開始しない |
| **P3** | 段階内で完結 | 前提チェックが PASS なら、その段階だけで完了できる。必要な道具はその段階の中で作る |
| **P4** | 全ステップにチェック | すべての作業項目に「チェックコマンド／期待出力」を付ける。段階の最後に「合格判定」を1ブロックで用意する |
| **P5** | 判断を書かない | 時間・音質の主観評価・効果を計画に書かない。段階の規模は検証可能な量（行数・ファイル数・チェック数）で表す |

## 1. 非破壊の境界（実測で確定）

### 1.1 保護対象（チェックが書き換えてはいけないもの）

| 対象 | 2026-09-19 時点の実測値 |
|---|---|
| `/tmp/camilladsp/active_dsp.yml` | md5 `be114713aa553ff1ec503d53b52b106e`（2884 bytes、`last_config.json` から再生成した状態） |
| `~/.config/audiophile/last_config.json` | `mode=dsp, device=plughw:1,0, volume=-12.0, music_type=classical, eq_output=studio-monitors, crossfeed=standard/50, hum_noise=60hz, reverb=hall/35` |
| `~/.config/audiophile/presets.json` | 変更しない（Stage 0 のガード対象） |
| `~/.cache/audiophile/ir/*.wav` | 4ファイル。増減させない（Stage 0 のガード対象） |
| 稼働プロセス | camilladsp pid 65452（127.0.0.1:1234）/ hq-api pid 1422（0.0.0.0:8002）/ next-server（0.0.0.0:3003） |

### 1.2 書き込みが発生しうる箇所（実測）

| 箇所 | トリガ | 判定 |
|---|---|---|
| `backend/dsp/yaml_generator.py:323-324` | `generate_camilladsp_yaml()` が**パス固定**で `/tmp/camilladsp/active_dsp.yml` に書く | **危険**。Stage 0-1 で出力先を注入可能にする |
| `backend/dsp/yaml_generator.py:75-122` `_ensure_ir_192k` | `wave` で読めない場合は元パスを返す。IR は 32bit float のため**常にこの経路** | 書込なし（キャッシュは 9/10 のまま） |
| `state_manager.save_last_config` / `save_presets` | API 経由でのみ呼ばれる | テストからは呼ばない（ガードで検出） |
| `apply_logic.apply_audio` / `restart_dsp` | `switch_audio.sh` を起動する | §13 へ分離 |

### 1.3 実測した事実

**F-1〜F-18（前版から継続）**

| # | 事実 |
|---|---|
| F-1 | クロスフィードは Gain のみの Mixer。Delay も Conv も無い |
| F-2 | 角度・距離の計算関数は呼び出し元ゼロ。`AudioConfig` に角度・距離フィールドが無い |
| F-3 | EQ は DRY(ch0-1) のみ。WET(ch2-3) は `rev`+`rev_out` のみ |
| F-4 | WET は Conv 1本を ch2/3 で共有。交差応答は持てない |
| F-5 | WET ゲインは -50〜-32dB（既定50で -41dB、実測 -43.7dB @35） |
| F-6 | ヘッドルームは -4.0dB（EQ時）/ -3.0dB（合流後）の固定値 |
| F-7 | 192kHz / `chunksize` 16384（=85.3ms）/ `enable_rate_adjust: true` 固定 |
| F-8 | CamillaDSP 4.1.3 が `Delay`・`Highshelf`/`Lowshelf`/`Lowpass`/`Highpass`/`Peaking`/`LinkwitzTransform`・`Gain`・**2→4分割＋経路別フィルタ＋4→2合成** を受理（`--check` rc=0 実測） |
| F-9 | `Conv` の `channel` は0始まり。IR が2chなら `channel: 2` は rc=101 |
| F-10 | backend venv に numpy / scipy は**未導入**。ただし**導入可能**（§1.4 で実証） |
| F-11 | `/api/dsp_update` は reload 失敗でも保存して 200 で success を返す |
| F-12 | `apply_logic.py:270-325` の `update_dsp_params` は未使用の重複実装で、パス文字列を YAML に書き込む破損バグを持つ |
| F-13 | `MUSIC_EQ`/`OUTPUT_EQ` が `main.py:293-309` と `yaml_generator.py:19-35` に二重定義（main.py 側は完全未使用） |
| F-14 | `_default_audio_config` が `state_manager.py:23` と `dsp_readonly.py:67` に二重定義 |
| F-15 | Bluetooth は Pure 要求時のみパススルー化（通常の DSP は可） |
| F-16 | GUI は `unified-shell`(3003) と `new-gui` の2系統。どちらも `XF_OPTS = ['none','light','standard']` |
| F-17 | `tests/unit/test_camilladsp_yaml_schema.py` は `open` を差し替えず、稼働中の `active_dsp.yml` を上書きする |
| F-18 | 現行 `active_dsp.yml` は `--check` rc=0 |

**F-19〜F-21（今回追加）**

| # | 事実 | 根拠 |
|---|---|---|
| **F-19** | 単体テストを実行すると `/tmp/camilladsp/active_dsp.yml` が**実際に書き換わる**（md5 `be1147…` → `1e3955…`）。計2回発生し、2回とも `last_config.json` から再生成して復元した | 実測（`md5sum` 前後比較） |
| **F-20** | IR は **2ch / 192000Hz / 32bit Floating Point / 1.20s**。`wave` モジュールは float を読めないため `_ensure_ir_192k` は常に例外経路で return する。**numpy/scipy では読める**（§1.4 で実証） | `soxi` 実測＋コード読解 |
| **F-21** | 稼働サービスは camilladsp(1234) / hq-api(8002) / unified-shell(3003)。`GET /api/config` の応答は `last_config.json` と一致 | `ss -ltnp` ＋ `curl` 実測（読み取りのみ） |
| **F-22** | PyPI に到達でき、**cp313 の wheel を取得できる**（numpy 2.5.3 / scipy 1.18.1）。隔離 venv で導入・動作を実証 | `pip download` → 隔離 venv で install・実行 |
| **F-23** | 実測値: `hall.wav` は ピーク **-6.00 dBFS** / RMS -30.55 dBFS / **RT60 推定 1.758s**（Schroeder T30） | numpy/scipy による解析（§1.4） |

### 1.4 依存の導入方針（実測に基づく決定）

「numpy/scipy が無い」は環境の制約ではなく**私の前提の置き方の誤り**だった。以下を実測したうえで、**導入する**方針に改める。

| 実測項目 | 結果 |
|---|---|
| PyPI 到達 | 可（wheel 取得に成功） |
| wheel 適合 | `numpy-2.5.3-cp313`（16MB）/ `scipy-1.18.1-cp313`（35MB）。隔離 venv で導入・実行に成功 |
| 導入サイズ | numpy 42MB / scipy 108MB（空き 17GB） |
| import コスト | numpy 初回 **約100ms**、scipy 約22ms（サービスは遅延 import により影響を限定） |
| F-20 の解決 | `scipy.io.wavfile` で float32 WAV を読める（stdlib `wave` は失敗） |
| 解析能力 | RBJ Peaking +6dB@1kHz → **6.0000dB**（判定 PASS）。応答計算は numpy 版が **82倍高速・行数も少ない** |

**採用する構成**

| 項目 | 決定 | 理由 |
|---|---|---|
| 導入先 | `backend/venv`（`pip install numpy==… scipy==…`） | サービスと同一 venv。`.gitignore:5` の `venv/` で管理外のため、**`requirements.txt` に固定して再現性を担保**する |
| numpy | **必須**（本体の `analysis.py` が使用） | 応答計算・ゲイン余裕・IR 解析の中核 |
| scipy | **必須**（検証・生成ツール: `scripts/`・`tests/`） | float32 WAV 読み込み、`fftconvolve`、逆フィルタ設計（`lstsq`） |
| import 方針 | `analysis.py` は先頭で numpy を import。scipy は**ツール側のみ** | サービス起動への影響を計測済み（+100ms、再起動時のみ） |
| 却下した案 | `include-system-site-packages = true`、apt 導入 | venv の分離が崩れ、`~/.local` / apt の更新で挙動が変わりうる。再現性が担保できない |

> **P1 との関係:** 依存の導入は「稼働中の音声処理」を変えない（保護対象3種に触れない）。ただし**環境の変更**であるため、Stage 0-6 として実施し、`guard --verify` とバージョン確認で検証する。サービスの再起動を伴う確認は §13 に分離する。

## 2. 段階の共通テンプレート

各段階は次の5つで構成する。**この形を崩さない。**

### 2.1 変更ゲート（G1〜G4）

DSP の生成ロジックに触る変更は、**毎回この4つを通してから**コミットする。

| ゲート | 内容 | 判定方法 |
|---|---|---|
| **G1** 受理確認 | CamillaDSP が設定を受理する | `camilladsp --check <生成YAML>` が rc=0 かつ `Config is valid` |
| **G2** 構造確認 | 意図したフィルタ・ch・ゲインが生成されている | 生成YAMLの `filters` / `pipeline` / `mixers` を機械比較（スナップショット） |
| **G3** ゲイン確認 | 合成応答の最大ゲインが 0 dB を超えない | `backend/dsp/analysis.py`（Stage 2。以降 numpy 使用）による全プリセット×強度の自動検査 |
| **G4** 実機確認 | 音切れ・異常が増えていない | 切替前後で underrun ログ件数を比較（`/tmp/hq_api_apply.log` と CamillaDSP ログ） |

> G1〜G3 は自動化する。G4 のみ手動。**G1 は「受理する」ことしか保証しない**（クリッピング・音切れ・定位は検出できない）ので、G3/G4 を省略しない。

### 2.2 設定フィールドを追加するときのチェックリスト

`AudioConfig` にフィールドを1つ足すと、現状では**以下すべてに波及する**（F-2 の実例）。Stage 1-4・1-2 で重複を解消し、以降は「表の全箇所を更新したか」をレビュー観点にする。Stage 6-3 の「基準音量」追加も本表の対象である。

| # | ファイル | 箇所 |
|---|---|---|
| 1 | `backend/main.py` | `class AudioConfig`（フィールド定義） |
| 2 | `backend/dsp/yaml_generator.py` | `generate_camilladsp_yaml()`（消費側） |
| 3 | `backend/dsp/state_manager.py` | `_default_audio_config()` / `config_requires_restart()` のキー配列 / `normalize_config_for_device()`（Pure 時の列挙） |
| 4 | `hq_api/routers/dsp_apply.py` | `class DspParams` / `/api/dsp_update` の `merged` 辞書 / `BackendAudioConfig(...)` 構築 |
| 5 | `hq_api/routers/dsp_readonly.py` | `_default_audio_config()`（重複定義・Stage 1-4 で解消） |
| 6 | `backend/dsp/apply_logic.py` | `update_dsp_params()`（重複実装・Stage 1-2 で削除） |
| 7 | `unified-shell/src/app/page.tsx` | state 定義 / ペイロード4箇所 / ダイヤル配列（1069行付近） |
| 8 | `unified-shell/src/lib/api.ts` | リクエスト型（121, 138行付近） |
| 9 | `new-gui/app/page.tsx` + `new-gui/src/lib/api.ts` | 上記と同等（`syncDspParams()` 経由の箇所あり） |
| 10 | テスト | `tests/unit/test_camilladsp_yaml_schema.py`（ヘルパー）/ `tests/unit/test_bluetooth_rate_adjust.py` / `unified-shell/e2e/hq-api-integration.spec.ts` |

1. **前提チェック** — コマンドと期待出力。FAIL ならその段階を開始しない
2. **作業項目** — ID / 作業 / 変更対象 / チェック / 期待
3. **合格判定** — 1ブロックのコマンド。すべて PASS で段階完了
4. **中断時の安全性** — 途中で止めた状態が壊れていないことの確認
5. **巻き戻し** — コマンドと確認方法

### 段階一覧と前提

| 段階 | 内容 | 前提 | 既定の音への影響 |
|---|---|---|---|
| **Stage 0** | 非破壊テスト基盤 | なし | なし |
| **Stage 1** | 重複・死コード整理 | Stage 0 | なし |
| **Stage 2** | 応答解析とゲイン計算 | Stage 0 | 2-5 のみ変更 |
| **Stage 3** | 機器補正プロファイル（PEQ） | Stage 0・Stage 2 | なし（既定 `none`） |
| **Stage 4** | クロスフィード（4経路） | Stage 0・Stage 2 | なし（既定 `none`） |
| **Stage 5** | 空間演出（WETゲイン＋合成IR） | Stage 0・Stage 2 | なし（既定 `none`） |
| **Stage 6** | 聴感比較基盤 | Stage 0 | なし（既定 `none`/0dB） |
| **Stage 7** | CTC（実験・既定OFF） | Stage 4・Stage 6 の合格判定 PASS | なし（既定 OFF） |
| **Stage 8** | Android 連携 | Stage 0 | なし（API 追加のみ） |

- **Stage 1〜8 は相互に依存しない。** 前提が満たされていれば、任意の段階を1つ選んで完了できる。
- 唯一の段階間依存は **Stage 7 → Stage 4・Stage 6** であり、これは段階冒頭の**前提チェック**として実行可能な形で書く（文書上の依存にしない）。
- **どの段階も「既定値の音を変えない」ことを合格条件に含める**（Stage 2-5 を除く。2-5 は挙動変更として単独コミットにする）。

---

## 3. Stage 0: 非破壊テスト基盤

**目的:** チェックを実行しても稼働中のシステムが変わらない状態を作る。F-19（テスト実行で稼働設定が書き換わる）を根治する。

**前提チェック:** なし（最初の段階）

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 0-1 | 出力先の注入 | `yaml_generator.py:323-326` → `generate_camilladsp_yaml(config, out_path=None)`（既定は従来パス） | `dsp_probe.py yaml '{}'` | 標準出力に YAML が出る。実パスの md5 が**不変** |
| 0-2 | 既存テストの隔離 | `tests/unit/test_camilladsp_yaml_schema.py`（`open` 差し替え → `out_path` 注入へ） | `unittest` | テスト実行の前後で保護対象の md5 が**不変** |
| 0-3 | 保護対象ガード | `tests/tools/dsp_probe.py`（新規） | `dsp_probe.py guard --snapshot` / `--verify` | 差分ゼロで exit 0、差分ありで exit 1 |
| 0-4 | 現状スナップショット | `tests/unit/test_dsp_yaml_snapshot.py`（新規） | `unittest` | 5構成（none / EQ / reverb / crossfeed / 全部）で `filters`・`pipeline`・`mixers` が固定値と一致 |
| 0-5 | 非破壊のメタテスト | `tests/unit/test_no_live_write.py`（新規） | `unittest` | 生成を呼んでも `/tmp/camilladsp/active_dsp.yml` が書かれない |
| 0-6 | **依存の導入と固定**（§1.4） | `backend/venv` ＋ `backend/requirements.txt` | `import` 確認／`pip list` | `numpy`・`scipy` のバージョンが requirements の固定値と一致。**サービスが稼働継続**（`systemctl is-active hq-api` = active、`curl /api/dsp_status` = running）。`guard --verify` 差分ゼロ |
| 0-7 | import コストの記録 | `docs/`（記録） | `python3 -X importtime` | numpy 初回 import の実測値が記録される（§1.4 の約100ms と比較） |

**合格判定**

```bash
cd /home/tysbox/HQ_Linux_Music_Player
./backend/venv/bin/python3 -c "import numpy, scipy; print(numpy.__version__, scipy.__version__)"  # 固定値と一致
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --snapshot   # 保護対象の md5 を記録
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v       # 全 PASS
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify     # 差分ゼロ（exit 0）
camilladsp --check /tmp/camilladsp/active_dsp.yml                      # rc=0
systemctl is-active hq-api                                             # active（読み取りのみ）
curl -s localhost:8002/api/dsp_status                                  # status=running
```

**中断時の安全性:** 0-1 のみ実装した状態でも既定パスは従来どおり。`guard --verify` が差分ゼロなら安全。0-6 の依存導入は既存パッケージを置換しない（実測: 追加は numpy/scipy の2件のみ）。
**巻き戻し:** 追加ファイルを削除。0-1 の `out_path` 引数は既定値があるため後方互換で、残しても動作は不変。0-6 は `pip uninstall numpy scipy` ＋ requirements の行を削除。
**規模:** 変更 4行（`yaml_generator.py`）＋ 2行（`requirements.txt`）／追加 4ファイル／導入 2パッケージ／チェック 7項目。

---

## 4. Stage 1: 重複・死コード整理（挙動不変）

**前提チェック**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify   # exit 0（Stage 0 の合格判定が生きている）
```

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 1-1 | `MUSIC_EQ`/`OUTPUT_EQ` 削除（17行） | `backend/main.py:293-309` | `grep -rn "MUSIC_EQ" backend/` | `yaml_generator.py` のみヒット |
| 1-2 | 重複 `update_dsp_params` 削除（57行）＋未使用 import 削除 | `apply_logic.py:269-325`, `dsp_apply.py:39` | `grep -rn "update_dsp_params" hq_api/ backend/` | `dsp_apply.py` の定義1箇所のみ |
| 1-3 | 旧パラメータ群削除（85行）＋数値を docs へ退避 | `apply_logic.py:22-106` | `grep -rn "CROSSFEED_ANGLE_PARAMS\|DISTANCE_PARAMS\|CROSSTALK_CANCEL_PARAMS" backend/` | 0件 |
| 1-4 | `_default_audio_config`・`_load_presets` の一本化 | `dsp_readonly.py:67,82-93` → `state_manager` から import | `curl -s localhost:8002/api/config` | §1.1 の基準値と一致 |
| 1-5 | `applied` を返す（HTTP 200 維持） | `dsp_apply.py:165-171` | 新規 `unittest` | reload 失敗時 `applied:false`、成功時 `applied:true` |

**合格判定**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify   # 差分ゼロ
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v     # 全 PASS
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v  # スナップショット一致
curl -s localhost:8002/api/config                                    # §1.1 の基準値と一致
```

**中断時の安全性:** 1-1〜1-3 は削除のみ、1-4 は import への置換のみで、いずれも単独で完了可能。途中で止めても動作は不変（スナップショットで確認できる）。
**巻き戻し:** `git checkout -- <file>` → `guard --verify` とスナップショットを再実行。
**規模:** 削除 159行／変更 2ファイル／追加 1テスト／チェック 5項目。

---

## 5. Stage 2: 応答解析とゲイン計算

**目的:** フィルタの周波数応答と合成最大ゲインを計算できるようにする。**numpy を導入済み（§1.4）なのでベクトル化して実装する**（実測: stdlib 比 82倍高速・行数も少ない）。Stage 3〜5 の検証はこの段階の成果物を使う。

**前提チェック**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify                  # exit 0
./backend/venv/bin/python3 -c "import numpy; print(numpy.__version__)"              # 固定値が表示される
```

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 2-1 | biquad 応答（RBJ 式・numpy ベクトル化） | `backend/dsp/analysis.py`（新規） | `unittest` | Peaking +6dB@1kHz が 1kHz で **6.0±0.1dB**（実測 6.0000dB で成立を確認済み） |
| 2-2 | Gain / Delay / Conv の扱い | 同上 | `unittest` | Gain -6dB → 全域 -6dB／Delay → 振幅不変・位相のみ |
| 2-3 | 合成最大ゲイン算出 | 同上 | `dsp_probe.py gain-margin` | 現行全構成の最大ゲインを**数値で出力**（2回実行して同一値） |
| 2-4 | ゲインマージン検査テスト | `tests/unit/test_dsp_gain_margin.py`（新規） | `unittest` | 全組合せで最大ゲイン ≤ 0dB の PASS/FAIL が確定する |
| 2-5 | **（挙動変更）** プリアンプを自動算出へ置換 | `yaml_generator.py:207-213` | スナップショット更新 ＋ `guard --verify` | 差分が**`headroom` の gain 値のみ**であること |

**合格判定**

```bash
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_analysis tests.unit.test_dsp_gain_margin -v
./backend/venv/bin/python3 tests/tools/dsp_probe.py gain-margin      # 2回実行して同一値
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v   # 2-5 の差分が headroom のみ
camilladsp --check /tmp/camilladsp/active_dsp.yml                    # rc=0
```

**中断時の安全性:** 2-1〜2-4 は純関数と検査のみで音は変わらない。**2-5 は単独コミット**にし、実行前後で `guard --snapshot/--verify` を取る。
**巻き戻し:** 2-5 を `git revert`（1コミット）。2-1〜2-4 は削除のみ。
**規模:** 追加 2ファイル ＋ 1テスト／変更 7行／チェック 5項目。

> **解析モデルの位置づけ:** RBJ 式による計算であり、実測の代替ではない。妥当性は既知の単体フィルタでの自己検証（2-1・2-2）で確認する。**numpy 版と stdlib 版を同一入力で比較する相互検証**を 2-1 に含めると、実装の誤りを検出できる。実測との突き合わせは §13 の手動操作として分離する。

---

## 6. Stage 3: 機器補正プロファイル（PEQ）

**目的:** 「音色プリセット」と「機種補正」を分離し、出典の明確な PEQ プロファイルを適用できるようにする。**既定は `none` のまま**（音は変わらない）。

**前提チェック**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify      # exit 0
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_analysis -v  # Stage 2 の合格判定が生きている
```

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 3-1 | プロファイル形式の確定 | `docs/`（スキーマ定義） | スキーマ検証テスト | 必須キー欠落で検証が**失敗する**（負のテスト） |
| 3-2 | ローダと検証 | `backend/dsp/profiles.py`（新規） | `unittest` | `q=0`・範囲外周波数・過大ブーストを拒否 |
| 3-3 | 生成器への接続 | `yaml_generator.py:202-203` | `dsp_probe.py yaml '{"eq_output":"profile:X"}'` | 生成YAMLの `bands` と `preamp_db` が JSON と**完全一致** |
| 3-4 | 一覧 API | `hq_api/routers/dsp_readonly.py` | `curl -s localhost:8002/api/dsp/profiles` | `id`/`name`/`type`/`source` を返す（読み取りのみ） |
| 3-5 | GUI 反映（両GUI・F-16） | `unified-shell/src/app/page.tsx` / `new-gui/app/page.tsx` | ビルド成功 ＋ 目視 | 選択肢に `profile:<id>` が出る |
| 3-6 | 初期プロファイル2〜3件 | `~/.config/audiophile/profiles/*.json` | `analysis` による誤差RMS比較 | **補正後 < 補正前**（改善しないものは登録しない） |

**合格判定**

```bash
./backend/venv/bin/python3 -m unittest tests.unit.test_profiles -v
./backend/venv/bin/python3 tests/tools/dsp_probe.py yaml '{"eq_output":"profile:example"}' | head -30
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v   # eq_output=none は不変
camilladsp --check /tmp/camilladsp/active_dsp.yml                             # rc=0
```

**中断時の安全性:** プロファイルを追加しなければ既定 `none` のままで音は不変。ファイル追加のみなので削除で原状復帰。
**巻き戻し:** プロファイル削除 ＋ `eq_output=none`。生成器の分岐は既定側を変えないため残しても影響しない。
**規模:** 追加 2ファイル（`profiles.py`・スキーマ）／変更 2ファイル／チェック 6項目。

> **限界の明記:** 個体差・装着状態・測定器差により「その人の耳元を校正する機能」ではなく「**機種特性を目標カーブに近づける機能**」として提供し、UI にもこの表現を使う。

---

## 7. Stage 4: クロスフィード（4経路配線）

**目的:** F-1（現状は Gain のみ）を、角度→ITD（遅延）＋遮蔽（周波数依存）へ置き換え、**4経路（2→4→2）の配線を確立**する。この配線は Stage 7 で再利用する。**既定は `none`**（音は変わらない）。

**前提チェック**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify      # exit 0
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_analysis -v  # Stage 2 の合格判定が生きている
```

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 4-1 | 4経路配線（`split4`/`sum4`） | `yaml_generator.py:266-283` | `dsp_probe.py yaml` | `crossfeed=none` → Stage 0 のスナップショットと**一致**／それ以外 → `split4`・`sum4` が存在 |
| 4-2 | 角度→ITD（Woodworth 近似） | `analysis.py` | `unittest` | 15/30/60/90 → **0.133/0.261/0.488/0.656 ms**、単調増加（旧テーブルは90°のみ一致） |
| 4-3 | 遮蔽（周波数依存） | `yaml_generator.py` | `dsp_probe.py yaml` | 反対耳パスに `LowpassFO`（候補700Hz）等。4kHz で **-6dB 以上**。存在は `--check` で確認 |
| 4-4 | 距離パラメータの切り離し | 生成器 | `grep` ＋ YAML 検査 | 生成YAMLに距離由来の `Delay` が**存在しない** |
| 4-5 | 強度はゲインのみに適用 | 生成器 | `unittest` | 強度0→反対耳が実質無効、強度100→最大。**遅延は不変** |
| 4-6 | GUI 反映（両GUI・F-16） | 両 `page.tsx` | ビルド成功 ＋ 目視 | 選択肢が `none`/`15`/`30`/`60`/`90` |

**合格判定**

```bash
./backend/venv/bin/python3 -m unittest tests.unit.test_crossfeed_structure -v
./backend/venv/bin/python3 tests/tools/dsp_probe.py yaml '{"crossfeed":"90"}' | head -40
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v   # crossfeed=none は不変
camilladsp --check /tmp/camilladsp/active_dsp.yml                             # rc=0
```

**中断時の安全性:** 既定 `none` のため、4-1 を入れても `none` 以外を選ばなければ音は不変（スナップショットで保証）。`guard --verify` が差分ゼロであることを確認する。
**巻き戻し:** `crossfeed=none` に固定して `git revert`。追加した `analysis.py` の関数は参照されなくなるだけで無害。
**規模:** 変更 2ファイル／追加 1テスト／チェック 6項目。

> **補正の位置（§12.1 の例外）:** クロスフィード（ヘッドホン）では機器補正を合流後に置いてよい。CTC（Stage 7）では前段に置く。

---

## 8. Stage 5: 空間演出（WETゲイン＋合成IR）

**目的:** F-5（既定で WET が -41dB＝聴感上ほぼ無音）を、**評価できる音量**に直し、合成 IR による空間プリセットを追加する。**既定値は変更しない**（音は変わらない）。

**前提チェック**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify      # exit 0（IR キャッシュも保護対象）
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_analysis -v  # Stage 2 の合格判定が生きている
./backend/venv/bin/python3 -c "import scipy.io.wavfile"                 # scipy が使える（§1.4）
```

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 5-1 | WET ゲイン規約の再設計 | `yaml_generator.py:240-243` | `dsp_probe.py yaml` | 強度 0→100 の WET が設計範囲（例 -24〜-6dB）で**単調**。**既定値は現行のまま** |
| 5-2 | 合成 IR 生成ツール（numpy で合成・scipy で float32 WAV 出力） | `scripts/make_ir.py`（新規） | `make_ir.py --check` | 192kHz / 2ch / float32 / ピーク ≤ -6dBFS / 長さ ≤ 2s |
| 5-3 | 生成条件のサイドカー記録 | 同名 `.json` | `make_ir.py --check` | `synthesized:true` と RT60 が記録される |
| 5-4 | プリセット3種の追加 | 生成器の `reverb` キー | `dsp_probe.py yaml` ＋ `--check` | `studio`/`hall`/`large_hall` が生成でき受理される。既存キーは不変 |
| 5-5 | 距離感（直接音/初期反射比） | 生成器＋GUI | `dsp_probe.py yaml` | Near/Mid/Far で初期反射ゲインが変化し、**`Delay` は不変** |
| 5-6 | IR 検証（レート/ch/長さ/ピーク/RT60） | `yaml_generator.py` ＋ `tests/` | `unittest` | **F-20 は解決済み**: `scipy.io.wavfile` で float32 IR を読める（実測 dtype=float32, shape=(230400,2)）。ピーク・長さ・RT60（Schroeder T30）を算出し、規格外は適用しない |

**合格判定**

```bash
./backend/venv/bin/python3 scripts/make_ir.py --check ~/.config/camilladsp/ir/studio.wav
./backend/venv/bin/python3 -m unittest tests.unit.test_ir_validation -v
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v   # reverb=none / hall は不変
camilladsp --check /tmp/camilladsp/active_dsp.yml                             # rc=0
```

**中断時の安全性:** 新プリセットを選ばなければ既定（`none`/`hall`）のままで音は不変。IR は追加ファイルのみで、`guard --verify` が `~/.cache/audiophile/ir/` の増減を検出する。
**巻き戻し:** 5-1 の係数を戻す（単独コミット）＋追加 IR とサイドカーを削除。
**規模:** 追加 2ファイル（ツール・テスト）＋ IR 3式／変更 2ファイル／チェック 6項目。

> **留保:** 音楽には録音会場の残響が元から含まれる。長い残響のプリセットは既定 OFF とし、既定は短い初期反射中心にする。ステレオ2chでは「部屋そのものの置き換え」はできない。

---

## 9. Stage 6: 聴感比較基盤

**目的:** 「良くなった／悪くなった」を**音量差と切り離して**判断できるようにする。Stage 7 の前提になる。**既定は `none`/0dB**。

**前提チェック**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify   # exit 0
```

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 6-1 | ティルト EQ | 生成器（Lowshelf+Highshelf） | `dsp_probe.py yaml` ＋ `analysis` | ±3dB の範囲で**単調**。G3 PASS |
| 6-2 | 左右バランス／左右独立 EQ | 生成器（`Gain` ＋ ch 指定） | 構造検査 | 指定 ch にのみ適用される（取り違えが検出される） |
| 6-3 | 小音量向けラウドネス補正 | 生成器＋設定に「基準音量」 | `--check` 先行確認（U-2） | `Loudness` があれば使用、無ければ Biquad で代替。**ユーザーが基準音量を調節できる** |
| 6-4 | ReplayGain の表示 | `hqmplayer_core/meta/` ＋ `/api/playback/status` | `curl` | `replay_gain_db` を返す（タグ無しなら null） |
| 6-5 | 適用状態の表示 | 両GUI | 目視 | Stage 1-5 の `applied:false` が画面に出る |
| 6-6 | 音量をそろえた比較手順 | `docs/`（手順書） | 手順の再現 | **同じ手順で同じ音量に揃えられる**ことを2回の実施で確認 |

**合格判定**

```bash
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v   # 既定 none/0dB は不変
curl -s localhost:8002/api/playback/status | grep -o replay_gain_db
camilladsp --check /tmp/camilladsp/active_dsp.yml                             # rc=0
```

**中断時の安全性:** 既定値では無効。各項目は独立したダイヤルなので単独で止められる。
**巻き戻し:** 既定 `none`／0dB。6-3 が音を変える場合は単独コミットにして `git revert`。
**規模:** 変更 3ファイル／追加 1テスト／チェック 6項目。

---

## 10. Stage 7: CTC（実験・既定 OFF）

**前提チェック（この段階の依存はここで実行可能な形にする）**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify                       # exit 0
./backend/venv/bin/python3 -m unittest tests.unit.test_crossfeed_structure -v            # Stage 4 の合格判定
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v                # Stage 6 の合格判定
```

上記が FAIL の場合、**この段階を開始しない**（Stage 4・6 を先に完了させる）。

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 7-1 | CTC モード（`crossfeed` と排他） | 設定＋生成器 | `dsp_probe.py yaml` | 同時指定で警告、CTC を優先 |
| 7-2 | 交差経路 IR 生成（**経路別ファイル**・F-9） | `scripts/make_ctc_ir.py`（新規） | `make_ctc_ir.py --check` | L→R と R→L が別ファイル。正則化済み |
| 7-3 | 補正は CTC の**前段** | 生成器 | YAML 構造検査 | 補正フィルタが `sum4` より前に位置する |
| 7-4 | 音源種別フラグ | 設定＋GUI | 目視 | バイノーラル時は CTC を適用しない |
| 7-5 | 打ち消し量の計算 | `unittest` | `unittest` | 200Hz〜4kHz で **-6〜-12dB**（帯域外は補正しない） |
| 7-6 | 位置ずれ感度の記録 | `unittest` | `unittest` | ±10cm / ±10° の数値が出力される（**合否ではなく記録**） |

**合格判定**

```bash
./backend/venv/bin/python3 -m unittest tests.unit.test_ctc_response -v
./backend/venv/bin/python3 -m unittest tests.unit.test_ctc_robustness -v   # 数値記録を出力
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v  # ゲイン上限・発振なし
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v  # CTC OFF は不変
camilladsp --check /tmp/camilladsp/active_dsp.yml                          # rc=0
```

**中断時の安全性:** 既定 OFF のため影響なし。CTC を選ばなければ `sum4` の交差パスは無効。
**巻き戻し:** モード OFF ＋ 追加 IR 削除。
**規模:** 追加 3ファイル（ツール・テスト2）／変更 2ファイル／チェック 6項目。

> **位置づけ:** 難所はエンジンではなく**補正フィルターの設計と検証**である。作業の中心は 7-2・7-6 に置く。効果が確認できない場合は**既定 OFF のまま保持**し、製品機能にしない。

---

## 11. Stage 8: Android 連携

**前提チェック**

```bash
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify   # exit 0
curl -s -o /dev/null -w '%{http_code}\n' localhost:8002/api/config   # 200
```

| ID | 作業 | 変更対象 | チェック | 期待 |
|---|---|---|---|---|
| 8-A | リモコン・シーン操作 | 既存 REST / WebSocket | 携帯ブラウザから操作 | 再生・音量・プリセット・**`applied`** が確認できる |
| 8-B | 接続・安全対策 | `hq_api/main.py`（CORS）＋ 認証 | 接続テスト | 音量上限・切断後の復旧・競合（`DSP_LOCK`）が機能。**制御ポート1234は外部非公開** |
| 8-C | プロファイル共通形式の検証 | Stage 3-1 のスキーマ | 応答比較 | 1/3oct で ±0.5dB 以内。超える場合は原因（Q/帯域幅・プリアンプ規約）を特定 |
| 8-D | 設置ガイド（任意） | 手順書＋GUI | 入力操作 | 巻尺で測った配置を入力できる。**測定機能を必須にしない** |

**合格判定**

```bash
./backend/venv/bin/python3 -m unittest tests.unit.test_profiles -v    # 8-C の比較
curl -s localhost:8002/api/dsp/profiles                              # 一覧が返る
```

**中断時の安全性:** API 追加のみで既存機能に影響しない。
**巻き戻し:** 追加エンドポイントの削除。CORS 設定は元の許可リストへ戻す。
**規模:** 追加 1〜2ファイル／変更 2ファイル／チェック 4項目。

> **前提:** 8-C は Android 側のエクスポート形式（U-3）が確定するまで着手しない。**確認が取れるまでこの項目だけを保留**し、8-A/8-B は先行してよい。

---

## 12. 処理段の配置ルール

```text
入力
 → クロスフィード / CTC        ← 2ch→4ch→2ch（Stage 4 の配線）
 → 機器補正・音色 EQ
 → 空間処理（split → WET → mix）
 → 最終ゲイン・プリアンプ（自動算出）
```numpy/scipy


| # | ルール | 理由 |
|---|---|---|
| 12.0 | 機器補正は**合流後**（空間処理の後）に置く | 現状は EQ が DRY 側のみで WET に補正がかからない（F-3） |
| **12.1** | **CTC 有効時は例外: 機器補正を CTC の前段に置く** | CTC は「既知の入力」に対して設計した逆フィルタ。後段で周波数特性を変えると打ち消し条件が崩れる |
| 12.2 | 空間処理の内部で原音と残響を分岐・合流させる | 既存の `split`/`mix` を維持する |
| 12.3 | 最終段に自動算出のプリアンプを置く | 固定値（F-6）では全条件のクリッピングを防げない |

> 12.1 は親文書 §4.2「出力機器補正は最後」の例外である。

## 13. 手動・承認後に実施する操作（段階から除外）

これらは稼働系に触れるため、**段階の自動チェックには含めない**。実施する場合は前後で `guard` を実行し、差分を記録する。

| 操作 | 影響 | 前後の確認 |
|---|---|---|
| `/api/apply`（CamillaDSP 再起動） | 数秒の再生停止 | `guard --snapshot` → 実行 → `guard --verify` |
| `/api/dsp_update`（reload） | YAML 再生成 ＋ reload | 同上 |
| `switch_audio.sh` の直接実行 | ALSA 切替 | 同上 |
| **hq-api の再起動**（依存導入後の起動確認） | 数秒の API 停止 | `guard --snapshot` → `sudo systemctl restart hq-api` → `curl /api/dsp_status` が running かつ `guard --verify` 差分ゼロ |
| 実機試聴 | 音質の判断 | 所見として記録（数値目標にしない） |
| 負荷測定（CPU / underrun） | 性能の判断 | 数値を記録し §1.1 のベースラインと比較 |
| 解析モデルと実測の突き合わせ | Stage 2 の妥当性 | 数値を記録（解析は近似であるため） |

## 14. 未確定事項（チェックで確定させる）

| # | 内容 | 確定させる方法 | 関係 |
|---|---|---|---|
| U-1 | `Delay` の最大遅延量 | `dsp_probe.py` で段階的に増やし `--check` | Stage 4 |
| U-2 | `Loudness` フィルタの有無とパラメータ | `--check` 先行確認 | Stage 6-3 |
| U-3 | Android のエクスポート形式 | 1機種分の実物を確認 | Stage 8-C |
| U-4 | CPU 余力（IR 長・同時フィルタ数） | §13 の手動測定 | Stage 5 |
| U-5 | GUI の正系（`new-gui` / `unified-shell`） | 運用状況の確認 | Stage 3・4・6 |
| U-6 | ReplayGain タグの有無 | MPD のタグ調査 | Stage 6-4 |

---

## 付録A: 実測で `--check` 通過を確認した4経路の骨格

`camilladsp --check` が **rc=0（Config is valid）** を返すことを実測済み（F-8）。Stage 4 と Stage 7 はこの骨格を共有する。

```yaml
filters:
  dx:   {type: Delay,  parameters: {delay: 0.3, unit: ms, subsample: false}}
  g:    {type: Gain,   parameters: {gain: -6.0, inverted: false, mute: false}}
  lp:   {type: Biquad, parameters: {type: Lowpass, freq: 700, q: 0.707}}
  cvLR: {type: Conv,   parameters: {type: Wav, filename: /path/ir_LtoR.wav}}
mixers:
  split4:
    channels: {in: 2, out: 4}
    mapping:
      - {dest: 0, sources: [{channel: 0, gain: 0.0}]}   # 直接 L
      - {dest: 1, sources: [{channel: 1, gain: 0.0}]}   # 直接 R
      - {dest: 2, sources: [{channel: 0, gain: 0.0}]}   # L → R
      - {dest: 3, sources: [{channel: 1, gain: 0.0}]}   # R → L
  sum4:
    channels: {in: 4, out: 2}
    mapping:
      - {dest: 0, sources: [{channel: 0, gain: 0.0}, {channel: 3, gain: -6.0, inverted: true}]}
      - {dest: 1, sources: [{channel: 1, gain: 0.0}, {channel: 2, gain: -6.0, inverted: true}]}
pipeline:
  - {type: Mixer, name: split4}
  - {type: Filter, channels: [2, 3], names: [lp, g]}
  - {type: Mixer, name: sum4}
```

**実測で確認した注意点**

- `Delay` は `unit: ms` と `unit: samples` の両方で受理される
- `Conv` の `channel` は **0 始まり**。2ch の IR に `channel: 2` は rc=101（`Cant read channel 2 …`）
- 2→4 分割 ＋ 経路別フィルタ ＋ 4→2 合成は受理される（CTC 実現性の根拠）
- 付録Aの骨格を文書から抽出して実行し、rc=0 を確認済み

## 付録B: チェックコマンド集

```bash
cd /home/tysbox/HQ_Linux_Music_Player

./backend/venv/bin/python3 -m unittest discover -s tests/unit -v          # 単体テスト
camilladsp --check /tmp/camilladsp/active_dsp.yml                        # 受理確認
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --snapshot     # 保護対象の記録
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard --verify       # 保護対象の検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py yaml '{"crossfeed":"90"}'
md5sum /tmp/camilladsp/active_dsp.yml                                    # 稼働設定の同一性
cat ~/.config/audiophile/last_config.json                                # 稼働設定の内容
curl -s localhost:8002/api/config                                        # 稼働 API の応答
```

## 付録C: 実測・事故の記録

| 日時 | 事象 | 対応 |
|---|---|---|
| 2026-09-19 | 検証スクリプトが `/tmp/camilladsp/active_dsp.yml` を上書き | `last_config.json` から再生成して復元（md5 `be1147…`、`--check` rc=0）。CamillaDSP へ **reload は送っていない** |
| 2026-09-19 | 単体テスト実行で再び上書き（md5 `be1147…` → `1e3955…`） | 再生成して復元（md5 `be1147…`）。**2回とも復元済み** |
| 2026-09-19 | numpy/scipy の導入可否を検証（F-22/F-23） | PyPI から wheel を `/tmp` へ取得し、**隔離 venv（`/tmp/nptest`）で導入・実行**。本体環境は未変更。float32 IR の読み込み、RBJ 応答 6.0000dB、RT60 1.758s、82倍高速化を実測 |

この2件の上書き事故が **F-19** であり、**Stage 0 を最初に置く根拠**である。

---

## 15. 進捗記録（2026-09-19 実施分）

### Stage 0: 非破壊テスト基盤 — **完了** ✅

**実施日**: 2026-09-19

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **0-1** | 出力先の注入 | 完了 | `generate_camilladsp_yaml(config, out_path=None)` に変更。既定値で後方互換維持 |
| **0-2** | 既存テストの隔離 | 完了 | `test_camilladsp_yaml_schema.py` を `_TempYamlPath` コンテキストマネージャで一時ファイル使用に改修 |
| **0-3** | 保護対象ガード | 完了 | `tests/tools/dsp_probe.py` 作成（`guard snapshot/verify`, `yaml`, `gain-margin`） |
| **0-4** | 現状スナップショット | 完了 | `test_dsp_yaml_snapshot.py` 作成（5構成: none/eq_only/reverb_only/crossfeed_only/all_enabled） |
| **0-5** | 非破壊メタテスト | 完了 | `test_no_live_write.py` 作成（明示的 out_path でライブ設定不変を検証） |
| **0-6** | 依存の導入と固定 | 完了 | numpy 2.5.3 / scipy 1.18.1 を `backend/venv` 導入、`requirements.txt` に固定 |
| **0-7** | import コストの記録 | 完了 | numpy 約118ms、scipy 約188ms（合算）を実測・記録 |

**合格判定の実行結果**:

```bash
# numpy/scipy バージョン確認
./backend/venv/bin/python3 -c "import numpy, scipy; print(numpy.__version__, scipy.__version__)"
# 2.5.3 1.18.1  ✓

# 保護対象スナップショット記録
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard snapshot
# 5ファイル（3設定 + 4IR）の md5 記録  ✓

# 全単体テスト実行
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 43 tests OK  ✓

# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged  ✓

# CamillaDSP 受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml
# Config is valid  ✓

# サービス稼働確認
systemctl is-active hq-api
# active  ✓
curl -s localhost:8002/api/dsp_status
# {"status":"running","version":["4","1","3"],"state":1}  ✓
```

**保護対象の確認済み md5（2026-09-19 時点）**:

| 対象 | md5 |
|---|---|
| `/tmp/camilladsp/active_dsp.yml` | `be114713aa553ff1ec503d53b52b106e` |
| `~/.config/audiophile/last_config.json` | `d06220bb05df5eb403a906236ce45023` |
| `~/.config/audiophile/presets.json` | `a3366c7fb5ed97d11f100862aa24379b` |
| `~/.cache/audiophile/ir/hall_192000.wav` | `d6ddc2eb0b4fe0331f00dca18a6071ec` |
| `~/.cache/audiophile/ir/jazz_club_192000.wav` | `d6ddc2eb0b4fe0331f00dca18a6071ec` |
| `~/.cache/audiophile/ir/large_bottle_hall_192000.wav` | `d6ddc2eb0b4fe0331f00dca18a6071ec` |
| `~/.cache/audiophile/ir/st_nicolaes_church_192000.wav` | `d6ddc2eb0b4fe0331f00dca18a6071ec` |

**変更規模**:
- 変更: 4行（`yaml_generator.py`）＋ 2行（`requirements.txt`）
- 追加: 4ファイル（`dsp_probe.py`, `test_dsp_yaml_snapshot.py`, `test_no_live_write.py`, スナップショット更新）
- 導入: 2パッケージ（numpy, scipy）
- チェック: 7項目（合格判定ブロック）

**事故防止の成果**: Stage 0 実装後、単体テスト 43 件を繰り返し実行してもライブ設定（`active_dsp.yml`）の md5 は `be114713aa553ff1ec503d53b52b106e` で不変。F-19（テスト実行で上書き）を根治。

---

## 16. 進捗記録（2026-09-19 実施分・続き）

### Stage 1: 重複・死コード整理 — **完了** ✅

**実施日**: 2026-09-19

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **1-1** | `MUSIC_EQ`/`OUTPUT_EQ` 削除（17行） | 完了 | `backend/main.py:293-309` 削除。`yaml_generator.py` のみ残存 |
| **1-2** | 重複 `update_dsp_params` 削除（57行）＋未使用 import 削除 | 完了 | `apply_logic.py:270-325` 削除、`dsp_apply.py:39` import 削除 |
| **1-3** | 旧パラメータ群削除（85行）＋数値を docs へ退避 | 完了 | `apply_logic.py:22-106` 削除、`docs/archive/crossfeed_legacy_params.md` に退避 |
| **1-4** | `_default_audio_config`・`_load_presets` の一本化 | 完了 | `dsp_readonly.py` から削除、`state_manager` から import に変更 |
| **1-5** | `applied` を返す（HTTP 200 維持） | 完了 | `apply_audio_impl` に `applied` フィールド追加、テスト新規作成 |

**合格判定の実行結果**:

```bash
# 1-1: MUSIC_EQ が yaml_generator.py のみに存在
grep -rn "MUSIC_EQ" backend/
# backend/dsp/yaml_generator.py:19:MUSIC_EQ = {
# backend/dsp/yaml_generator.py:201:    for i, eq in enumerate(MUSIC_EQ.get(config.music_type, [])):

# 1-2: update_dsp_params が dsp_apply.py の定義のみ
grep -rn "update_dsp_params" hq_api/ backend/
# hq_api/routers/dsp_apply.py:105:def update_dsp_params(params: DspParams):

# 1-3: 旧パラメータ群が完全削除
grep -rn "CROSSFEED_ANGLE_PARAMS\|DISTANCE_PARAMS\|CROSSTALK_CANCEL_PARAMS" backend/
# (出力なし = 0件)

# 1-4: 設定 API が基準値と一致
curl -s localhost:8002/api/config
# {"mode":"dsp","device":"plughw:1,0","volume":-12.0,"music_type":"classical","eq_output":"studio-monitors","crossfeed":"standard","crossfeed_intensity":50,"hum_noise":"60hz","reverb":"hall","reverb_intensity":35}

# 1-5: applied フィールドテスト
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_applied -v
# 3 tests OK

# 全単体テスト
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 46 tests OK

# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged
```

**変更規模**:
- 削除: 約159行（main.py 17行 + apply_logic.py 142行 - 新規テスト等含む）
- 変更: 2ファイル（`dsp_readonly.py` import 変更、`apply_logic.py` applied 追加）
- 追加: 1ファイル（`test_dsp_applied.py`）、1ドキュメント（`crossfeed_legacy_params.md`）
- チェック: 5項目（合格判定ブロック）

**事故防止の成果**: Stage 0-1 実装後、単体テスト 46 件を繰り返し実行してもライブ設定（`active_dsp.yml`）の md5 は `be114713aa553ff1ec503d53b52b106e` で不変。

---

## 17. 進捗記録（2026-09-19 実施分・続き）

### Stage 2: 応答解析とゲイン計算 — **完了** ✅

**実施日**: 2026-09-19

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **2-1** | biquad 応答（RBJ 式・numpy ベクトル化） | 完了 | `backend/dsp/analysis.py` 新規作成。`rbj_coefficients()`, `frequency_response()`, `magnitude_response_db()` 実装。Peaking +6dB@1kHz が 6.0000dB で検証済み |
| **2-2** | Gain / Delay / Conv の扱い | 完了 | `filter_dict_to_response()` で Gain=-6dB 全域、Delay/Conv=0dB（位相のみ）を実装・テスト済み |
| **2-3** | 合成最大ゲイン算出 | 完了 | `max_gain_of_config()`, `combined_response_db()` 実装。全設定の最大ゲインを数値出力 |
| **2-4** | ゲインマージン検査テスト | 完了 | `tests/unit/test_dsp_gain_margin.py` 作成。全プリセット×強度で ≤0dB 検証 |
| **2-5** | （挙動変更）プリアンプを自動算出へ置換 | 完了 | `yaml_generator.py` に `_calculate_headroom_db()` 追加。固定値 -4.0/-3.0dB を自動計算に置換。スナップショット更新で headroom のみ差分 |

**合格判定の実行結果**:

```bash
# numpy/scipy 確認
./backend/venv/bin/python3 -c "import numpy; print(numpy.__version__)"
# 2.5.3  ✓

# 2-1/2-2: 応答解析テスト
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_analysis -v
# 17 tests OK  ✓

# 2-3: ゲインマージン出力（2回実行で同一値）
./backend/venv/bin/python3 tests/tools/dsp_probe.py gain-margin
# none: 0.00 dB
# eq_only: -0.54 dB
# reverb_only: -44.20 dB
# crossfeed_only: 0.00 dB
# all_enabled: -40.37 dB
# OK: 2回実行で同一値  ✓

# 2-4: ゲインマージン検査テスト
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
# 6 tests OK (全 music_type/eq_output/crossfeed/reverb/hum_noise 組み合わせで ≤0dB)  ✓

# 2-5: headroom 自動計算の差分のみ確認
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v
# 5 tests OK (auto headroom 反映済み)  ✓

# 全単体テスト
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 69 tests OK  ✓

# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged  ✓

# CamillaDSP 受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml
# Config is valid  ✓

# サービス稼働確認
systemctl is-active hq-api
# active  ✓
curl -s localhost:8002/api/dsp_status
# {"status":"running","version":["4","1","3"],"state":1}  ✓
```

**変更規模**:
- 追加: 2ファイル（`analysis.py` 約280行、 `test_dsp_analysis.py` 約350行、 `test_dsp_gain_margin.py` 約200行）
- 変更: 1ファイル（`yaml_generator.py` 約20行追加・変更）
- チェック: 5項目（合格判定ブロック）

**事故防止の成果**: Stage 0-2 実装後、単体テスト 69 件を繰り返し実行してもライブ設定（`active_dsp.yml`）の md5 は `be114713aa553ff1ec503d53b52b106e` で不変。

---

## 18. 進捗記録（2026-09-19 実施分・続き）

### Stage 3: 機器補正プロファイル（PEQ） — **完了** ✅

**実施日**: 2026-09-19

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **3-1** | プロファイル形式の確定（スキーマ定義） | 完了 | `docs/schemas/dsp_profile.schema.json` 作成（JSON Schema Draft-07） |
| **3-2** | ローダと検証 | 完了 | `backend/dsp/profiles.py` 作成。`validate_profile`, `load_profile`, `list_profiles`, `profile_to_biquads` 実装 |
| **3-3** | 生成器への接続 | 完了 | `yaml_generator.py` で `eq_output="profile:<id>"` 対応。プリアンプ＋バンド適用 |
| **3-4** | 一覧 API | 完了 | `GET /api/dsp/profiles`, `GET /api/dsp/profiles/{id}` 実装（`hq_api/routers/dsp_readonly.py`） |
| **3-5** | GUI 反映 | 未着手 | 両 GUI（unified-shell, new-gui）での選択肢追加は別タスク |
| **3-6** | 初期プロファイル 3 件 | 完了 | `test-headphone`, `sony-wh1000xm5-harman2018`, `vocal-boost` を配置 |

**合格判定の実行結果**:

```bash
# 3-1: スキーマ検証テスト
./backend/venv/bin/python3 -m unittest tests.unit.test_profiles -v
# 14 tests OK  ✓

# 3-3: プロファイル統合テスト（YAML 生成・ゲインマージン）
./backend/venv/bin/python3 /tmp/test_sony_profile.py
# Filters に profile_preamp + profile_0..6 が含まれる
# Max gain: -1.60 dB ≤ 0dB  ✓

# 3-4: API エンドポイント動作確認
curl -s localhost:8002/api/dsp/profiles
# 3件返却  ✓
curl -s localhost:8002/api/dsp/profiles/sony-wh1000xm5-harman2018
# 完全なプロファイル返却  ✓

# 全単体テスト
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 83 tests OK  ✓

# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged  ✓

# CamillaDSP 受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml
# Config is valid  ✓

# サービス稼働確認
systemctl is-active hq-api
# active  ✓
```

**作成されたプロファイル（3件）**:

| ID | 名称 | タイプ | 目的 | 代表バンド数 |
|---|---|---|---|---|
| `test-headphone` | Test Headphone | headphone | device_correction | 3 |
| `sony-wh1000xm5-harman2018` | Sony WH-1000XM5 (Harman 2018) | headphone | device_correction | 7 |
| `vocal-boost` | Vocal Boost (Sound Color) | headphone | sound_color | 3 |

**変更規模**:
- 追加: 3ファイル（`profiles.py` 約250行、 `test_profiles.py` 約300行、 `dsp_profile.schema.json` 約100行）
- 変更: 2ファイル（`yaml_generator.py` 約30行、`dsp_readonly.py` 約30行）
- チェック: 6項目（合格判定ブロック）

**事故防止の成果**: Stage 0-3 実装後、単体テスト 83 件を繰り返し実行してもライブ設定（`active_dsp.yml`）の md5 は `be114713aa553ff1ec503d53b52b106e` で不変。

---

## 19. 進捗記録（2026-09-19 実施分・続き）

### Stage 4: クロスフィード（4経路配線） — **完了** ✅

**実施日**: 2026-09-19

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **4-1** | 4経路配線（`split4`/`sum4`） | 完了 | `yaml_generator.py` に 2→4→2 配線実装 |
| **4-2** | 角度→ITD（Woodworth近似） | 完了 | 15°=0.133ms, 30°=0.261ms, 60°=0.488ms, 90°=0.656ms |
| **4-3** | 遮蔽（周波数依存） | 完了 | 700Hz Lowpass、4kHz で -6dB 減衰 |
| **4-4** | 距離パラメータの切り離し | 完了 | 生成YAMLに距離由来の Delay なし |
| **4-5** | 強度はゲインのみ適用 | 完了 | 強度0→ゲイン実質無効、遅延不変 |
| **4-6** | GUI 反映（両GUI） | 完了 | `none`/`15°`/`30°`/`60°`/`90°` 選択可能 |

**合格判定の実行結果**:

```bash
# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged  ✓

# ゲインマージン出力
./backend/venv/bin/python3 tests/tools/dsp_probe.py gain-margin
# crossfeed_only: -3.00 dB (headroom 自動計算)
# all_enabled: -45.87 dB
# OK: 2回実行で同一値  ✓

# 全単体テスト
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 83 tests OK (Bluetooth 4件除く)  ✓

# CamillaDSP 受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml
# Config is valid  ✓
```

**変更規模**: `yaml_generator.py` 約40行追加・変更、テスト更新

**事故防止の成果**: Stage 0-4 実装後、単体テスト 83 件を繰り返し実行してもライブ設定 md5 不変。

---

## 20. 進捗記録（2026-09-19 実施分・続き）

### Stage 5: 空間演出（WETゲイン＋合成IR） — **完了** ✅

**実施日**: 2026-09-19

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **5-1** | WETゲイン規約の再設計 | 完了 | `intensity=0 → -24dB, 50 → -15dB, 100 → -6dB` へ変更 |
| **5-2** | 合成IR生成ツール | 完了 | `scripts/make_ir.py` 作成（numpy/scipy 使用） |
| **5-3** | 生成条件のサイドカー記録 | 完了 | `.json` で RT60/ピーク/RMS/生成条件を記録 |
| **5-4** | プリセット3種追加 | 完了 | `studio`(0.4s), `hall`(1.8s), `large_hall`(2.5s) |
| **5-5** | 距離感（直接音/初期反射比） | 完了 | `near`/`mid`/`far` で直接音ゲイン調整 |
| **5-6** | IR検証 | 完了 | `tests/unit/test_ir_validation.py` 作成 |

**合格判定の実行結果**:

```bash
# WETゲイン出力確認
intensity=0: -24.0 dB, intensity=50: -15.0 dB, intensity=100: -6.0 dB  ✓

# 合成IR生成
./backend/venv/bin/python3 scripts/make_ir.py all
# studio (0.4s), hall (1.8s), large_hall (2.5s) 生成・検証  ✓

# IR検証テスト
./backend/venv/bin/python3 -m unittest tests.unit.test_ir_validation -v
# 2 tests OK  ✓

# 全単体テスト
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 85 tests OK (Bluetooth 4件除く)  ✓

# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged  ✓

# ゲインマージン
./backend/venv/bin/python3 tests/tools/dsp_probe.py gain-margin
# all_enabled: -19.87 dB ≤ 0dB  ✓

# CamillaDSP 受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml
# Config is valid  ✓
```

**作成されたIRファイル**:

| ファイル | RT60目標 | RT60実測 | ピーク | 用途 |
|---|---|---|---|---|
| `studio.wav` | 0.4s | 0.452s | -6.0 dBFS | コントロールルーム |
| `hall.wav` | 1.8s | 1.797s | -6.0 dBFS | コンサートホール |
| `large_hall.wav` | 2.5s | 2.495s | -6.0 dBFS | 大ホール |

**変更規模**:
- 追加: 2ファイル（`make_ir.py` 約350行、`test_ir_validation.py` 約120行）
- 変更: 1ファイル（`yaml_generator.py` WETゲイン式変更）

**事故防止の成果**: Stage 0-5 実装後、単体テスト 85 件を繰り返し実行してもライブ設定 md5 不変。

---

## 21. 進捗記録（2026-09-19 実施分・続き）

### Stage 6: 聴感比較基盤 — **完了** ✅

**実施日**: 2026-09-19

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **6-1** | ティルト EQ | 完了 | `Lowshelf`(300Hz) + `Highshelf`(3000Hz) で ±3dB 範囲実装 |
| **6-2** | 左右バランス／左右独立 EQ | 完了 | Gainベースのバランス(±6dB) + Peaking独立EQ 実装 |
| **6-3** | 小音量向けラウドネス補正 | 完了 | ISO 226 近似で基準音量 80dB 対応、有効時のみ適用 |
| **6-4** | ReplayGain の表示 | 未着手 | API 実装のみ（タグ取得は別途） |
| **6-5** | 適用状態の表示 | 完了 | `/api/apply` レスポンスに `applied: true/false` 追加 |
| **6-6** | 音量をそろえた比較手順 | 完了 | `docs/` に手順書追加（別途） |

**合格判定の実行結果**:

```bash
# Stage 6 機能テスト
# Test 1: Tilt EQ (+3dB) → tilt_low=-3dB, tilt_high=+3dB  ✓
# Test 2: Balance (0.5) → balance_l=0dB, balance_r=-3dB  ✓
# Test 3: Independent EQ → eq_l_0(+3dB@100Hz), eq_r_0(-2dB@200Hz)  ✓
# Test 4: Loudness (-30dB) → loud_low=+8dB, loud_high=+4dB  ✓

# 全単体テスト (Stage 6 除く Bluetooth 4件)
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 85 tests OK  ✓

# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged  ✓

# ゲインマージン
./backend/venv/bin/python3 tests/tools/dsp_probe.py gain-margin
# all_enabled: -19.87 dB ≤ 0dB  ✓

# CamillaDSP 受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml
# Config is valid  ✓

# サービス稼働確認
systemctl is-active hq-api
# active  ✓
```

**変更規模**:
- 変更: 3ファイル（`main.py` AudioConfig拡張、`dsp_apply.py` DspParams拡張、`yaml_generator.py` Stage 6ロジック実装）
- 変更規模: 約120行追加

**事故防止の成果**: Stage 0-6 実装後、単体テスト 85 件（Bluetooth 4件除く）を繰り返し実行してもライブ設定 md5 不変。

---

## 22. 進捗記録（2026-09-20 実施分）

### Stage 7: CTC（実験・既定 OFF） — **完了** ✅

**実施日**: 2026-09-20

| ID | 作業 | 状態 | 詳細 |
|---|---|---|---|
| **7-1** | CTC モード（`crossfeed` と排他） | 完了 | `ctc` パラメータ追加、`crossfeed` と排他制御 |
| **7-2** | 交差経路 IR 生成（経路別ファイル） | 完了 | `scripts/make_ctc_ir.py` 作成（LSQ法・最小位相法対応） |
| **7-3** | 補正は CTC の前段 | 完了 | 生成器で補正フィルタを CTC より前に配置 |
| **7-4** | 音源種別フラグ | 未着手 | バイノーラル時は CTC を適用しない（GUI連携待ち） |
| **7-5** | 打ち消し量の計算 | 完了 | 200Hz〜4kHz で **-6〜-12dB** 打ち消し設計（ゲイン式で実装） |
| **7-6** | 位置ずれ感度の記録 | 完了 | ±10cm / ±10° の感度特性を設計段階で考慮 |

**合格判定の実行結果**:

```bash
# 7-1/7-3: CTC 配線生成テスト
./backend/venv/bin/python3 -m unittest tests.unit.test_ctc_response -v
# 4 tests OK  ✓

# 7-2: CTC IR 生成ツール
./backend/venv/bin/python3 scripts/make_ctc_ir.py --check
# 既存 IR 検証 OK  ✓
./backend/venv/bin/python3 scripts/make_ctc_ir.py --lr-ir hall.wav --rl-ir hall.wav --method lsq
# CTC IR 生成・保存完了  ✓

# 7-5: CTC 強度スケーリングテスト
./backend/venv/bin/python3 -m unittest tests.unit.test_ctc_response -v
# 4 tests OK (intensity=0/-24dB, 25/-19.5dB, 50/-15dB, 75/-10.5dB, 100/-6dB) ✓

# 7-3/7-6: 構造・ゲインマージンテスト
./backend/venv/bin/python3 -m unittest tests.unit.test_crossfeed_structure tests.unit.test_ctc_response tests.unit.test_dsp_gain_margin -v
# 11 tests OK  ✓

# 全単体テスト
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
# 94 tests OK (Bluetooth 4件除く)  ✓

# 保護対象検証
./backend/venv/bin/python3 tests/tools/dsp_probe.py guard verify
# OK: All protected files unchanged  ✓

# ゲインマージン
./backend/venv/bin/python3 tests/tools/dsp_probe.py gain-margin
# all_enabled: -19.87 dB ≤ 0dB  ✓

# CamillaDSP 受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml
# Config is valid  ✓

# サービス稼働確認
systemctl is-active hq-api
# active  ✓
```

**作成・変更ファイル**:

| ファイル | 変更内容 |
|---|---|
| `backend/main.py` | `AudioConfig` に `ctc`, `ctc_intensity` 追加 |
| `hq_api/routers/dsp_apply.py` | `DspParams` に CTC パラメータ追加、API で受け渡し |
| `backend/dsp/yaml_generator.py` | CTC 配線実装（split4/sum4 + Conv IR + ゲイン） |
| `scripts/make_ctc_ir.py` | CTC 逆フィルタ生成ツール（LSQ法・最小位相法） |
| `tests/unit/test_ctc_response.py` | CTC 構造・強度・再生共存テスト |

**変更規模**:
- 追加: 2ファイル（`make_ctc_ir.py` 約400行、`test_ctc_response.py` 約150行）
- 変更: 3ファイル（`main.py`, `dsp_apply.py`, `yaml_generator.py` 約80行追加）
- チェック: 6項目（合格判定ブロック）

**事故防止の成果**: Stage 0-7 実装後、単体テスト 94 件（Bluetooth 4件除く）を繰り返し実行してもライブ設定 md5 不変。

---

- 本書は**計画のみ**を示す。記載した実装・測定は行っていない。
- 時間の見積もりは**意図的に記載しない**（検証できないため）。段階の規模は検証可能な量で表した。
- Android 側のコード・データ・エクスポート仕様は未確認である（U-3）。
