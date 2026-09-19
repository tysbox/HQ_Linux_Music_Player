# DSP 機能拡張 実装ロードマップ（別紙） — 段階的・検証可能な開発計画

- 作成日: 2026-09-19
- 親文書: `docs/DSP_FEATURE_EXPANSION_PROPOSAL.md`（設計検討・方針）
- 本書の役割: 親文書の方針を、**1段階ずつ「完了したかどうかを機械的に判定できる」作業単位**に分解する。設計の妥当性評価は親文書および親文書へのレビューで扱い、本書は実施計画のみを扱う。
- 根拠の範囲: 2026-09-19 時点の作業ツリー（未コミット変更を含む）で**実測・コード読解により確認した事実のみ**を根拠にする。実機試聴・負荷測定は本書作成時点で未実施。
- 対象外: Android アプリの内部実装、実測ルーム補正、ヘッドトラッキング、マルチチャンネル化。

## 0. 読み方

- フェーズは 0 → 7 の順に進める。**前フェーズの完了条件を満たすまで次に着手しない。**
- すべての作業項目に「完了条件」を付ける。判定は原則としてコマンド実行結果またはファイル差分で行う（主観評価に依存させない）。
- **音質の「効果」の判定は Phase 5 まで保留する。** Phase 5 の音量そろえ比較基盤が無い状態で「良くなった」と判断すると、単なる音量差を効果と誤認する。
- 各フェーズに「撤退条件」を付ける。撤退条件は機能を消すのではなく、既定 OFF にして保持することを基本とする。

## 1. 実装前に確定した事実（2026-09-19 実測）

本書の計画は、以下を前提に組んでいる。番号は本文中で参照する。

| # | 確認した事実 | 根拠（実測・コード） | 計画への影響 |
|---|---|---|---|
| F-1 | クロスフィードは **Gain のみ**の Mixer。Delay も Conv も無い | 生成YAML実測: `crossfeed=standard` → `cf` Mixer のみ（`dest0: ch0 -1.8dB / ch1 -14.8dB`） | Phase 3 で経路構成そのものを作り替える |
| F-2 | 角度・距離の計算関数は**呼び出し元ゼロ**。`AudioConfig` に角度・距離フィールドが無い | `compute_distance_params` / `apply_crossfeed` / `apply_crosstalk_cancel` の参照 0 件。UI は `none/light/standard` のみ（`unified-shell/src/app/page.tsx:45`） | UI だけでなく生成器・設定モデル・API を同時に変える必要がある |
| F-3 | EQ は **DRY(ch0-1) のみ**。WET(ch2-3) は `rev`+`rev_out` のみ | 生成YAML実測（reverb=hall） | 機器補正は合流後に置く。CTC 時は例外（§5.1 参照） |
| F-4 | WET は **Conv 1本を ch2/3 で共有**。交差応答は持てない | `yaml_generator.py:225-245` | Phase 4/6 で経路別 Conv に拡張する |
| F-5 | WET ゲインは **-50〜-32 dB**（既定50で -41dB、実測 -43.7dB @intensity 35） | `yaml_generator.py:242` と生成YAML実測 | 現状の空間演出は聴感上ほぼ無音。Phase 4 の最優先項目 |
| F-6 | ヘッドルームは **-4.0 dB（EQ時）/ -3.0 dB（合流後）の固定値** | `yaml_generator.py:207-213, 305-313` | Phase 1 でフィルタ合成から自動算出に置き換える |
| F-7 | 192kHz / `chunksize` 16384（=85.3ms）/ `enable_rate_adjust: true` 固定 | 生成YAML実測 | 88ms 以上の遅延を持つ IR 追加時は負荷を測る |
| F-8 | CamillaDSP 4.1.3 が次を受理することを実測確認（`--check` rc=0）: `Delay`(`unit: ms`/`samples`)、Biquad `Highshelf`/`Lowshelf`/`Lowpass`/`Highpass`/`Peaking`/`LinkwitzTransform`、`Gain`、**2→4 分割＋経路別フィルタ＋4→2 合成** | `camilladsp --check` 実測 | Phase 3 のクロスフィードと Phase 6 の CTC は同じ 4経路構成で実現可能 |
| F-9 | `Conv` の `channel` は 0 始まり。IR が 2ch なら `channel: 0/1` のみ指定可（`channel: 2` はエラー）。無指定なら同一 IR を各 ch に適用 | 実測: `Cant read channel 2 ... which contains 2 channels` | 交差経路(L→R / R→L)は IR ファイルを分けて用意する |
| F-10 | backend venv に **numpy / scipy は無い** | `import numpy` → ModuleNotFoundError | 検証ツールは標準ライブラリのみで実装する（新規依存を増やさない） |
| F-11 | `/api/dsp_update` は **reload 失敗でも保存して 200 で success を返す** | `hq_api/routers/dsp_apply.py:165-171` | Phase 1 で「適用できたか」を返すように直す |
| F-12 | `backend/dsp/apply_logic.py:270-325` の `update_dsp_params` は**未使用の重複実装**で、戻り値のパス文字列を YAML に書き込む破損バグを持つ | コード読解（ルータ版の NOTE と同型の破損） | Phase 1 で削除する |
| F-13 | `MUSIC_EQ` / `OUTPUT_EQ` が `backend/main.py:293-309` と `yaml_generator.py:19-35` に**二重定義**（main.py 側は完全に未使用） | grep 実測 | Phase 1 で未使用側を削除 |
| F-14 | `_default_audio_config` が `state_manager.py:23` と `dsp_readonly.py:67` に**二重定義** | コード読解 | Phase 1 で一本化 |
| F-15 | Bluetooth は **Pure 要求時のみ**パススルー化（通常の DSP は可） | `state_manager.py:94-110` | 精密な位相検証は有線 DAC を基準にする |
| F-16 | GUI は `unified-shell`(3003) と `new-gui` の**2系統**があり、どちらも `XF_OPTS = ['none','light','standard']` | 両ファイル grep 実測 | ダイヤル変更は両方に反映が必要（`docs/2026-09-18_switch_to_3003_RUNBOOK.md` で切替手順あり） |
| F-17 | `tests/unit/test_camilladsp_yaml_schema.py` は `open` を差し替えず、**稼働中の `/tmp/camilladsp/active_dsp.yml` を上書きする** | テストコード実測（patch/tempfile なし） | Phase 0 の最優先項目（安全網） |
| F-18 | 現行 `/tmp/camilladsp/active_dsp.yml` は `camilladsp --check` で valid（rc=0） | 実測 | これがロールバックの基準状態 |

---

## 2. 全フェーズ共通ルール

### 2.1 変更ゲート（G1〜G4）

DSP の生成ロジックに触る変更は、**毎回この4つを通してから**コミットする。

| ゲート | 内容 | 判定方法 |
|---|---|---|
| **G1** 受理確認 | CamillaDSP が設定を受理する | `camilladsp --check <生成YAML>` が rc=0 かつ `Config is valid` |
| **G2** 構造確認 | 意図したフィルタ・ch・ゲインが生成されている | 生成YAMLの `filters` / `pipeline` / `mixers` を機械比較（スナップショット） |
| **G3** ゲイン確認 | 合成応答の最大ゲインが 0 dB を超えない | `backend/dsp/analysis.py` による全プリセット×強度の自動検査 |
| **G4** 実機確認 | 音切れ・異常が増えていない | 切替前後で underrun ログ件数を比較（`/tmp/hq_api_apply.log` と CamillaDSP ログ） |

> G1〜G3 は自動化する。G4 のみ手動。**G1 は「受理する」ことしか保証しない**（クリッピング・音切れ・定位は検出できない）ので、G3/G4 を省略しない。

### 2.2 設定フィールドを追加するときのチェックリスト

`AudioConfig` にフィールドを1つ足すと、現状では**以下すべてに波及する**（F-2 の実例）。Phase 1 でこの一覧を固定し、Phase 2 以降の追加コストを下げる。

| # | ファイル | 箇所 |
|---|---|---|
| 1 | `backend/main.py` | `class AudioConfig`（フィールド定義） |
| 2 | `backend/dsp/yaml_generator.py` | `generate_camilladsp_yaml()`（消費側） |
| 3 | `backend/dsp/state_manager.py` | `_default_audio_config()` / `config_requires_restart()` のキー配列 / `normalize_config_for_device()`（Pure 時の列挙） |
| 4 | `hq_api/routers/dsp_apply.py` | `class DspParams` / `/api/dsp_update` の `merged` 辞書 / `BackendAudioConfig(...)` 構築 |
| 5 | `hq_api/routers/dsp_readonly.py` | `_default_audio_config()`（重複定義） |
| 6 | `backend/dsp/apply_logic.py` | `update_dsp_params()`（Phase 1 で削除予定） |
| 7 | `unified-shell/src/app/page.tsx` | state 定義 / ペイロード4箇所 / ダイヤル配列（1069行付近） |
| 8 | `unified-shell/src/lib/api.ts` | リクエスト型（121, 138行付近） |
| 9 | `new-gui/app/page.tsx` + `new-gui/src/lib/api.ts` | 上記と同等（`syncDspParams()` 経由の箇所あり） |
| 10 | テスト | `tests/unit/test_camilladsp_yaml_schema.py`（ヘルパー）/ `tests/unit/test_bluetooth_rate_adjust.py` / `unified-shell/e2e/hq-api-integration.spec.ts` |

> **Phase 1 完了後にこの表を更新し、以降は「表の全箇所を更新したか」をレビュー観点にする。**

### 2.3 検証ツール（Phase 0 で整備する）

新規依存を増やさないため、**すべて標準ライブラリのみ**で実装する（F-10）。

| ツール | 役割 | 実装方針 |
|---|---|---|
| `backend/dsp/analysis.py` | フィルタ応答とゲインの解析（本番でも使用） | RBJ cookbook の biquad 係数 → `cmath` で周波数応答を計算。`Gain`/`Delay` は解析的に扱う。20Hz〜20kHz を対数100〜200点で評価 |
| `tests/tools/yaml_probe.py` | 生成YAMLを**稼働中ファイルに触れず**取得 | `tests/unit/test_bluetooth_rate_adjust.py:41-56` と同じ `open` 差し替え＋`tempfile` 方式を共通化 |
| `tests/unit/test_dsp_gain_margin.py` | G3 の自動検査 | 全 `music_type` × `eq_output` × `crossfeed` × `reverb` の組合せで最大ゲイン ≤ 0 dB を assert |

> `analysis.py` の妥当性は、(a) 既知の単体フィルタでの自己検証（例: Peaking +6dB @1kHz → 1kHz で 6.0±0.1dB）、(b) 余力があれば実測スイープとの突き合わせ、の2段で確認する。**解析モデルは RBJ 式に基づく近似であり、実測の代替ではない**ことを明記する。

---

## 3. フェーズ計画

### Phase 0: 安全網の整備（挙動を変えない・最優先）

**目的:** 機能を足す前に「壊したことに気づける」状態を作る。F-17（既存テストが稼働中の設定を上書きする）と F-5（現状の空間演出が聴感上ほぼ無音）は、検証手段が無いまま作業を進めた結果として現れている。

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 0-1 | 生成テストの隔離 | `tests/unit/test_camilladsp_yaml_schema.py` | `open` 差し替え方式（`test_bluetooth_rate_adjust.py` と同型）へ変更。**テスト実行の前後で `/tmp/camilladsp/active_dsp.yml` の md5 が不変** |
| 0-2 | YAML構造スナップショット | `tests/unit/test_dsp_yaml_snapshot.py`（新規） | 代表5構成（無効 / EQ / reverb / crossfeed / 全部）で `filters`・`pipeline`・`mixers` のキーと全 gain を固定。意図しない差分で fail |
| 0-3 | 応答解析モジュール | `backend/dsp/analysis.py`（新規・stdlib のみ） | 既知フィルタの自己検証テストが通る（+6dB Peaking @1kHz が 6.0±0.1dB 等） |
| 0-4 | ゲインマージン検査 | `tests/unit/test_dsp_gain_margin.py`（新規） | 全組合せで最大ゲイン ≤ 0 dB。**現状で PASS するか FAIL するかを記録する**（FAIL なら Phase 1-7 の自動プリアンプの根拠になる） |
| 0-5 | 経路確認手順の確立 | `docs/`（手順書）＋ テスト音源 | L のみ / R のみ のテスト音源を用意し、片ch入力時に反対chへ漏れないことを確認する手順を文書化。所要時間と期待結果を明記 |
| 0-6 | ベースライン記録 | 記録メモ（`docs/` または Issue） | `camilladsp --check` rc=0、underrun 件数、CamillaDSP の CPU%、レイテンシ（chunksize 85.3ms）を数値で記録 |

**検証手順（この Phase の完了判定）**

```bash
cd /home/tysbox/HQ_Linux_Music_Player
md5sum /tmp/camilladsp/active_dsp.yml            # 実行前
./backend/venv/bin/python3 -m unittest tests.unit.test_camilladsp_yaml_schema -v
md5sum /tmp/camilladsp/active_dsp.yml            # 実行後 → 一致すること
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot tests.unit.test_dsp_gain_margin -v
camilladsp --check /tmp/camilladsp/active_dsp.yml
```

**撤退・ロールバック:** テストとツールの追加のみ。アプリケーションコードを変更しないため、失敗時は追加ファイルを削除すればよい。

**工数感: 小〜中**（テスト2本＋解析モジュール1本）

---

### Phase 1: 基盤整理（挙動を変えない）

**目的:** フィールド追加・経路追加のコストと事故率を下げる。**音の出方を変えないことを完了条件に含める**（0-2 のスナップショットが一致すること）。

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 1-1 | 未使用の `MUSIC_EQ`/`OUTPUT_EQ` を削除 | `backend/main.py:293-309` | grep で `yaml_generator.py` のみが定義元。0-2 スナップショット不変 |
| 1-2 | YAML 破損バグを持つ重複実装を削除 | `backend/dsp/apply_logic.py:270-325` ＋ `hq_api/routers/dsp_apply.py:39` の未使用 import | grep で `update_dsp_params` の定義がルータ側1つのみ |
| 1-3 | 角度・距離の旧パラメータ群の扱いを決定 | `apply_logic.py:25-47` | Phase 3 で作り直すため削除。数値は docs に参考値として保存（新テーブルは Phase 3-2 の式で再計算） |
| 1-4 | `_default_audio_config` の一本化 | `hq_api/routers/dsp_readonly.py:67` → `state_manager` から import | 定義が1箇所。`GET /api/config` の応答が不変 |
| 1-5 | 「適用できたか」を返す | `hq_api/routers/dsp_apply.py:105-173` | reload 失敗時も **200 を維持**しつつ `{"status":"success","applied":false,"warning":...}` を返す（フロントは `.catch` のみのため 422 にしない）。CamillaDSP 停止時に `applied:false` になる単体テストを追加 |
| 1-6 | 設定フィールド追加チェックリストの固定 | §2.2 の表 | レビュー手順に組み込む |
| 1-7 | プリアンプの自動算出（**挙動変更あり**） | `backend/dsp/analysis.py` + `yaml_generator.py:207-213` | 固定 `-4.0/-3.0` を、合成応答から算出した値に置換。G1〜G4 を通す。**差分は生成YAMLのスナップショット更新として明示的にコミット** |

**検証手順**

```bash
cd /home/tysbox/HQ_Linux_Music_Player
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v
camilladsp --check /tmp/camilladsp/active_dsp.yml
# 実機: ダイヤルを一巡させ、切替時に音が途切れないこと（/api/dsp_update 経路）
curl -s -X POST localhost:8002/api/dsp_update -H 'content-type: application/json' \
  -d '{"music_type":"classical","eq_output":"none","crossfeed":"none","hum_noise":"none","reverb":"none"}'
```

**撤退・ロールバック:** 1-1〜1-6 は削除と一本化のみで可逆。1-7 のみ音が変わるため、`git revert` で即時復帰できるよう単独コミットにする。

**工数感: 小**（最大の効果は「以降のフェーズの事故率低下」）

---

### Phase 2: 出力機器補正プロファイル（PEQ）

**目的:** 「音色プリセット」と「機種補正」を分離し、出典の明確な PEQ プロファイルを適用できるようにする。親文書 §2.2 の方針どおり、**少数のプロファイルから始めて大量移植はしない**。

**前提:** Phase 0 の応答解析（0-3）と Phase 1 のチェックリスト（1-6）が完了していること。

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 2-1 | プロファイル形式の確定 | `docs/`（スキーマ定義） | `schema_version` / `id` / `type`(headphone・speaker) / `name` / `source`(出典・利用条件) / `purpose`(機種補正・音色) / `preamp_db` / `bands[]`(type・freq・q・gain) / `target_curve` / `notes` を持つ JSON |
| 2-2 | ローダと検証 | `backend/dsp/profiles.py`（新規） | `list_profiles()` / `load_profile(id)` / `validate_profile()`。`q=0`・範囲外周波数・過大ブーストを弾く |
| 2-3 | 生成器への接続 | `backend/dsp/yaml_generator.py:202-203` | `eq_output = "profile:<id>"` のとき `bands` を Biquad として展開し `preamp_db` を Gain で適用。**既存の `OUTPUT_EQ` キーは後方互換で維持** |
| 2-4 | 一覧 API の追加 | `hq_api/routers/dsp_readonly.py` | `GET /api/dsp/profiles` が id・name・type・source を返す（読み取りのみ） |
| 2-5 | GUI 反映 | `unified-shell/src/app/page.tsx` **と** `new-gui/app/page.tsx` | EQ ダイヤルの選択肢に `profile:<id>` を追加（F-16 のため両方）。「機種補正」と「音色」をラベルで区別 |
| 2-6 | 初期プロファイル | `~/.config/audiophile/profiles/*.json` | 出典と測定条件が確認できる **2〜3件のみ**を登録 |

**検証手順**

```bash
cd /home/tysbox/HQ_Linux_Music_Player
# (1) 生成YAMLのバンドがプロファイルと一致するか（機械比較）
./backend/venv/bin/python3 -m unittest tests.unit.test_profiles -v
# (2) 補正前後の目標カーブとの誤差RMS（analysis.py）
./backend/venv/bin/python3 -c "from backend.dsp.analysis import profile_error_rms; print(profile_error_rms('example-headphone'))"
# (3) G1・G3
camilladsp --check /tmp/camilladsp/active_dsp.yml
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
```

**完了条件に含めること:** 補正前後で**誤差RMSが改善している**こと（改善しないプロファイルは登録しない）。聴感評価は Phase 5 で行う。

**撤退・ロールバック:** `eq_output` を `none` に戻せば元の音に戻る。プロファイルは JSON なので削除のみ。

**工数感: 中**

> **限界の明記（親文書 §2.2 の再掲）:** 個体差・イヤーパッドの状態・装着状態・測定器差・目標カーブ差により、「その人の耳元を校正する機能」ではなく「**機種特性を目標カーブに近づける機能**」として提供する。UI にもこの表現を使う。

---

### Phase 3: クロスフィード（遅延＋周波数依存）

**目的:** F-1（現状は Gain のみ）を、**角度→ITD（遅延）＋遮蔽（周波数依存）**を持つ構成に置き換える。同時に **4経路（2→4→2）の配線を確立**する。この配線は Phase 6 の CTC でそのまま再利用する。

**前提:** F-8 により Delay／Biquad／2→4→2 は CamillaDSP 4.1.3 で受理されることを実測済み（付録A）。

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 3-1 | 4経路配線の導入 | `yaml_generator.py` の `cf` Mixer 部（266-283行） | `split4`（2→4）＋経路別フィルタ＋`sum4`（4→2）。`crossfeed="none"` のときは**従来と同じYAML**（0-2 スナップショット一致） |
| 3-2 | 角度→ITD の式を唯一のソースにする | `backend/dsp/analysis.py` または新規 `crossfeed.py` | Woodworth 近似 `Δt = (a/c)(θ + sin θ)`（a=0.0875m, c=343m/s → a/c≈0.2551 ms/rad）。**旧テーブルは 90° のみ一致（0.66ms）。15°/30° は式より約16〜17%、60° は約10%小さいため、式を正として再計算する**（15°→0.133 / 30°→0.261 / 60°→0.488 / 90°→0.656 ms） |
| 3-3 | 遮蔽（周波数依存） | 同上 | 反対耳パスに 1次 Lowpass（`LowpassFO`）または Highshelf を配置。候補: LowpassFO 700Hz（Meier 系）/ Highshelf -4dB@1.5kHz。`LowpassFO` の存在は 3-1 の段階で `--check` により確認する（既存コードが `HighpassFO` を使用中＝系列は存在） |
| 3-4 | 距離パラメータの切り離し | `apply_logic.py:33-37`（1-3 で削除済みなら不要） | 距離をクロスフィードの遅延に使わない。Near/Mid/Far は Phase 4 の「直接音/初期反射比」で実装する |
| 3-5 | 強度（0-100%）の適用範囲を定義 | 生成器 | 反対耳パスの**ゲインのみ**をスケールし、**遅延は角度で固定**する（強度で遅延を動かすと角度の意味が崩れる）。規約を docs に明記 |
| 3-6 | GUI 反映 | 両GUI | Crossfeed ダイヤルの選択肢を `none` + `15/30/60/90` に変更（強度バーは既存の仕組みを流用） |

**検証手順**

```bash
# (a) 構造: 反対耳パスに Delay と Lowpass が入っているか
./backend/venv/bin/python3 -m unittest tests.unit.test_crossfeed_structure -v
# (b) 応答: θ の増加で遅延が単調増加、遮蔽が高域で増加するか
./backend/venv/bin/python3 -c "
from backend.dsp.analysis import crossfeed_response
for th in (15,30,60,90): print(th, crossfeed_response(th)['delay_ms'])"
# (c) ゲイン + 受理
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
camilladsp --check /tmp/camilladsp/active_dsp.yml
```

| 検証項目 | 期待 |
|---|---|
| (a) 構造 | `crossfeed=none` → 旧YAMLと一致 / それ以外 → `split4`・`sum4` と Delay＋LP が存在 |
| (b) 遅延 | θ に対し単調増加（0.133 → 0.656 ms） |
| (b) 遮蔽 | 反対耳パスが低域通過（4kHz で -6dB 以上） |
| (c) ゲイン | 合成最大ゲイン ≤ 0 dB |
| (c) 音切れ | `--check` rc=0、切替時に underrun 増加なし |

**手動確認（Phase 5 まで「参考」扱い）:** 左右に極端に振った素材で正面定位の改善と聴き疲れの変化。**音量をそろえて**比較する。

**撤退・ロールバック:** `crossfeed=none` で従来動作（スナップショットで保証）。問題が出ても既定を `none` に固定したまま改善を続けられる。

**工数感: 中**

---

### Phase 4: 空間演出の実用化（WETゲイン再設計＋合成IR）

**目的:** 既存の IR 畳み込み（`split`→Conv→`mix`）は**配線としては動作しているが、既定値では聴感上ほぼ無音**（F-5: -41dB / 実測 -43.7dB）。距離感プリセットを作る前に、**評価できる音量**に直す。

**前提:** Phase 0 の G3 検査（自動プリアンプ）が機能していること。WET を上げると合流後のクリッピング余裕が減るため。

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 4-1 | WET ゲイン規約の再設計 | `yaml_generator.py:240-243` | 現行 `-50 + intensity*0.18`（= -50〜-32dB）を、**DRY との比をパラメータ化した式**（目安: -24〜-6dB）に置換。合流後のヘッドルームは `analysis.py` の自動算出（1-7）に任せる |
| 4-2 | 合成 IR 生成ツール | `scripts/make_ir.py`（新規・`wave` 使用、stdlib のみ） | 初期反射（6〜10本 / 8〜60ms / 左右で時刻・ゲインを変える）＋指数減衰ノイズ（RT60 0.4〜2.0s）。192kHz/32bit stereo WAV を `~/.config/camilladsp/ir/` へ出力 |
| 4-3 | 生成条件の記録 | 同名 `.json` サイドカー | RT60・初期反射本数・**合成であること（実測IRではない）** を記録。既存の実測IR（`hall` / `jazz_club` / `large_bottle_hall` / `st_nicolaes_church`）は「実測」として区別 |
| 4-4 | プリセット | 生成器の `reverb` キー | `studio`(小) / `hall`(中) / `large_hall`(大) の3種を追加。既存キーは維持 |
| 4-5 | 距離感の実装 | 生成器＋GUI | Near/Mid/Far を **直接音と初期反射の比**で表現（例: 初期反射 -18/-12/-8dB ＋ 到来時刻のスケール）。**クロスフィードの遅延とは独立**（3-4） |
| 4-6 | IR 検証ローダ | `yaml_generator.py` の `_ensure_ir_192k` 前段 | レート・ch数・長さ・ピーク・出典を検証し、規格外は適用せず理由をログ（既存の IR 不在時フォールバックと同様に、既存設定を壊さない） |

**検証手順**

```bash
# (1) IR の健全性（レート・ch・ピーク・長さ）
./backend/venv/bin/python3 scripts/make_ir.py --check ~/.config/camilladsp/ir/studio.wav
# (2) 100%WET の応答（初期反射の到来時刻と残響減衰をオフラインで確認）
./backend/venv/bin/python3 -m unittest tests.unit.test_ir_response -v
# (3) ゲイン余裕と受理
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
camilladsp --check /tmp/camilladsp/active_dsp.yml
# (4) 実機: 音切れ（underrun）と CPU を Phase 0 のベースラインと比較
grep -ci underrun /tmp/hq_api_apply.log
```

| 検証項目 | 期待 |
|---|---|
| IR | 192kHz / stereo / ピーク -6dBFS 以下 / 長さ 2s 以下（負荷確認のため） |
| 応答 | 初期反射が設定時刻に現れ、残響が指数減衰（RT60 が設定値の ±20%） |
| 実機 | underrun 件数がベースラインから増えない、切替時に音が途切れない |
| 聴感 | **音量をそろえて** DRY のみ / WET 少量 を比較し、明瞭度の低下が許容範囲か |

**撤退・ロールバック:** 4-1 の係数のみ元に戻せば従来と同じ（WET が実質無音）。IR は追加ファイルなので既存プリセットに影響しない。**`reverb_intensity` の既定値は変更しない**（既定50の聴感が変わる場合のみ、変更を単独コミットで明示）。

**工数感: 中〜大**（IR 生成の設計が本体。DSP 配線は既存の `split`/`mix` を流用）

> **親文書 §2.3 の留保を維持:** 音楽には録音会場の残響が元から含まれる。強く足すと明瞭度が落ちるため、既定は短い初期反射中心とし、残響時間の長いプリセットは既定 OFF にする。ステレオ2chでは「部屋そのものの置き換え」はできない。

---

### Phase 5: 聴感・比較基盤（効果判定の土台）

**目的:** 「良くなった／悪くなった」を**音量差と切り離して**判断できるようにする。**Phase 6 の CTC より先に置く。** CTC は効果が小さく出る機能であり、比較基盤が無いと「効いているのか分からない」まま作業が終わる。

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 5-1 | ティルト EQ | `yaml_generator.py`（Lowshelf+Highshelf のペア） | ±3dB 程度を1ダイヤルで。`analysis.py` で合成ゲインを検証 |
| 5-2 | 左右バランス／左右独立 EQ | `Gain` フィルタ＋ch 指定 | ch 単位で適用。片ch入力の経路確認（0-5）で ch の取り違えを検出 |
| 5-3 | 小音量向けラウドネス補正 | 設定に「基準音量」を追加（§2.2 の全箇所を更新） | CamillaDSP の Loudness フィルタの有無を先に確認（未確定 U-2）。無ければ Biquad で代替。音量値と連動 |
| 5-4 | ReplayGain の表示・操作 | `hqmplayer_core/meta/replay_gain.py`（未実装）＋ `/api/playback/status` | MPD の `replay_gain_mode` を利用（`/etc/mpd.conf` に設定なし＝要設定）。`docs/DEVELOPMENT_ROADMAP.md:528` の既存計画と統合 |
| 5-5 | 音量をそろえた A/B 比較手順 | 手順書 | 「比較前に音量をそろえる」手順を固定（DSP の音量値を同値に固定、または WET 追加分を補償）。**この手順を Phase 2〜4 の聴感評価に適用する** |
| 5-6 | **適用状態の表示** | 両GUI | 「選択した設定」と「実際に適用できた設定」を区別表示（1-5 の `applied` を反映） |

**検証手順**

```bash
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v      # 5-1〜5-3 のゲイン検査を含む
curl -s localhost:8002/api/playback/status | grep -o replay_gain_db   # 5-4
```

**撤退・ロールバック:** 各項目は独立したダイヤルなので、既定 `none`／0dB で無効化できる。

**工数感: 中**

> **注意:** ラウドネス補正の「基準音量」は、DSP の音量値と実際の音圧が一致しないため、**ユーザーが基準音量を調節できる設計**にする（親文書 §3 の指摘どおり）。

---

### Phase 6: クロストークキャンセル（CTC）— 実験枠

**目的:** 固定リスニング位置向けに、左右スピーカー→左右耳の4経路を扱う実験機能を試作する。**製品の既定機能にはしない。** 親文書 §7.3 のとおり、空間演出とは別モードにする。

**前提（すべて満たすこと）**

- Phase 3 の 4経路配線が完成している（F-8 により受理は実測済み）
- Phase 5 の比較基盤がある
- **有線 DAC（共通クロック）** で評価する（F-15: Bluetooth は位相関係の検証に適さない）
- 帯域を限定（例: 200Hz〜4kHz）し、補正量に上限（例: -6dB）を設ける
- 中央の固定位置のみを対象とし、頭の移動には追従しない（追従は対象外）

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 6-1 | CTC モードの追加 | 設定＋生成器（`crossfeed` とは別キー） | モード ON 時のみ 4経路の交差パスを有効化。`crossfeed` と**排他**（同時指定時は CTC を優先し警告を返す） |
| 6-2 | 交差経路 IR の生成 | `scripts/make_ctc_ir.py`（新規） | 幾何モデル（頭を球・耳間 17.5cm）＋ 遅延/遮蔽（Phase 3-2/3-3 の式を流用）から L→R / R→L の IR を生成。**F-9 により IR ファイルは経路ごとに分ける**。逆フィルタは周波数依存の正則化付き |
| 6-3 | 補正・EQ の配置 | 生成器 | **CTC の後段に機器補正を置かない**（打ち消しの位相・振幅関係が崩れるため）。補正は CTC 前段に置く。§5.1 の例外を実装で担保 |
| 6-4 | 音源種別フラグ | 設定＋GUI | 通常ステレオ / バイノーラル を明示。バイノーラル時に通常ステレオ向け CTC を適用しない |
| 6-5 | ロバスト性の評価 | `tests/unit/test_ctc_robustness.py`（新規） | 頭位置 ±10cm・角度 ±10° を想定したパラメータ掃引で、打ち消し量の変化を計算し記録（**保証ではなく感度の把握**） |

**検証手順**

```bash
# (1) 打ち消し量（オフライン計算: 200Hz〜4kHz で目標 -6〜-12dB）
./backend/venv/bin/python3 -m unittest tests.unit.test_ctc_response -v
# (2) ロバスト性（位置ずれに対する感度）
./backend/venv/bin/python3 -m unittest tests.unit.test_ctc_robustness -v
# (3) ゲイン上限・発振チェック（正則化が効いているか）
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
# (4) 受理（CTC + 空間演出 + 補正の同時有効も確認）
camilladsp --check /tmp/camilladsp/active_dsp.yml
```

| 検証項目 | 期待 |
|---|---|
| 打ち消し量 | 200Hz〜4kHz で -6〜-12dB（帯域外は補正しない） |
| ロバスト性 | ±10cm のずれで打ち消し量がどう劣化するかを**数値で記録**（「動いても効く」とは主張しない） |
| ゲイン | 合成最大ゲイン ≤ 0dB、発振なし |
| 聴感 | 通常ステレオで効果が小さいことを**期待値として記録**（親文書 §7.3 の留保どおり） |

**撤退条件:** 打ち消し帯域が狭い／定位が不自然／ゲイン増大が大きい場合は、**既定 OFF の実験機能として保持**し製品機能にしない。CTC のためだけに共通基盤を作らない（Phase 3 の配線を再利用する）。

**工数感: 大**

> **位置づけの再掲:** 親文書 §2.1-B のとおり、難所はエンジンではなく**補正フィルターの設計と検証**である。したがって工数の大半は 6-2・6-5 に置く。

---

### Phase 7: Android 連携（リモコン → プロファイル共通形式）

**目的:** 親文書 §7.4 の順序どおり、**非リアルタイムの設定・状態共有から始める**。音声処理は Linux 内で完結させ、スマホは制御と表示を担当する。

| ID | 内容 | 対象 | 完了条件（判定） |
|---|---|---|---|
| 7-A | リモコン・シーン操作 | 既存 REST / WebSocket を LAN 内で使用 | レスポンシブ Web UI を携帯で操作し、再生・音量・空間プリセット・**適用結果（5-6 の `applied`）** を確認できる |
| 7-B | 接続・安全対策 | `hq_api/main.py`（CORS）＋ 認証 | 接続先設定・認証・通信保護・**音量上限**・複数端末の競合（`DSP_LOCK` で直列化済み）・切断後の状態復旧を整理。**CamillaDSP の制御ポート(1234)を外部へ公開しない** |
| 7-C | プロファイル共通形式の検証 | Phase 2-1 のスキーマ | Android 側の書き出しを **1〜3機種**で受け取り、Linux で適用して応答を比較（`analysis.py`）。許容差（例: 1/3oct で ±0.5dB）を超える場合は差分の原因（Q/帯域幅・プリアンプ規約・サンプルレート）を特定 |
| 7-D | 設置ガイド（任意） | 手順書＋GUI | 巻尺等で確認した配置の入力のみ。**測定機能は必須条件にしない**（親文書 §7.4-C の留保） |

**検証手順**

```bash
# 7-C: 同一プロファイルの応答比較
./backend/venv/bin/python3 -c "from backend.dsp.analysis import compare_profiles; print(compare_profiles('android-export.json','local.json'))"
# 7-A/B: 携帯ブラウザから操作（手動チェックリスト）
```

**撤退・ロールバック:** 7-A〜7-D はサーバ API を壊さない追加のみ。認証導入が既存のローカル操作を妨げる場合は、ローカル（127.0.0.1）を除外する設定で回避する。

**工数感: 中**（7-C は Android 側の仕様確定待ちのため、**確認が取れるまで着手しない**）

---

## 4. 順序の根拠（なぜこの順か）

| 順序 | 理由 |
|---|---|
| Phase 0 → 1 | 検証手段が無いまま機能を足すと回帰を見逃す。F-17（既存テストが稼働中の設定を上書き）と F-5（空間演出がほぼ無音）はその実例 |
| Phase 1 → 2 | `AudioConfig` のフィールド追加は10箇所に波及する（§2.2）。先に整理すると以降の追加コストが下がる |
| Phase 2 → 3 | プロファイル（PEQ）は実装が最も単純で、**応答比較という検証手段を確立できる**。CTC とも独立 |
| Phase 3 → 4 → 6 | Phase 3 で 4経路配線を作り、Phase 6 で再利用する。Phase 4 は IR 生成とゲイン規約という別の作業 |
| Phase 5 → 6 | CTC は効果が小さく、位置ずれに敏感な機能。**比較基盤が無いと撤退判断ができない** |
| Phase 7 は並行可 | サーバ API を壊さない追加のみ。ただし 7-C は Android 側の仕様確定が前提 |

## 5. 処理段の配置ルール

親文書 §4.2 の整理を、実装で守るためのルールとして固定する。

```text
入力
 → クロスフィード / CTC        ← 2ch→4ch→2ch（Phase 3 の配線）
 → 機器補正・音色 EQ            ← 既存 EQ の位置（DRY側）をここへ移す
 → 空間処理（split → WET → mix）
 → 最終ゲイン・プリアンプ（自動算出）
```

| # | ルール | 理由 |
|---|---|---|
| 5.0 | 機器補正は**合流後（空間処理の後）**に置く | 現状は EQ が DRY 側のみで、WET に補正がかからない（F-3） |
| **5.1** | **CTC 有効時は例外: 機器補正を CTC の前段に置く** | CTC は「既知の入力」に対して設計した逆フィルタ。後段で周波数特性を変えると打ち消し条件が崩れる |
| 5.2 | 空間処理の内部では原音と残響を分岐・合流させる | 既存の `split`/`mix` を維持 |
| 5.3 | 最終段に自動算出のプリアンプを置く | 固定値（F-6）では全条件のクリッピングを防げない |

> **5.1 は親文書 §4.2 の「出力機器補正は最後」という記述の例外である。** クロスフィード（ヘッドホン）では 5.0 のままでよいが、CTC（スピーカー）では 5.1 を適用する。

## 6. やらないこと・撤退条件

| やらないこと | 理由 |
|---|---|
| 全 2800 機種のプロファイル移植 | 相互運用の検証が先（親文書 §7.4-B）。少数で形式を確定する |
| 実測ルーム補正・自動測定を必須にする | スマホ1本では4経路を取得できない（親文書 §7.4-C） |
| ヘッドトラッキング | 総遅延とフィルタ切替の連続性が未検証。YAML の高頻度リロードでは実現できない |
| マルチチャンネル化 | 2ch 前提の拡張。後方・側方の包囲感が必要になった時点で再検討 |
| Bluetooth 経由での精密位相検証 | 独立した無線出力では条件を管理できない（F-15）。有線 DAC を基準にする |
| CTC の製品機能化 | 帯域・位置ずれの制約が大きい。既定 OFF の実験枠に留める |

**共通の撤退原則:** 効果が確認できない機能は削除せず「既定 OFF」で保持し、既定値の音を変えない。

## 7. 未確定事項（着手前に確認する）

| # | 内容 | 確認方法 | 関係フェーズ |
|---|---|---|---|
| U-1 | CamillaDSP `Delay` の最大遅延量 | `--check` と実測 | 3 |
| U-2 | CamillaDSP の `Loudness` フィルタの有無とパラメータ | `--check` | 5-3 |
| U-3 | Android 側のエクスポート形式（PEQ が Q か帯域幅か、プリアンプ規約、目標カーブ、サンプルレート） | 1機種分の実物を確認 | 7-C |
| U-4 | 現行ハードの CPU 余力（IR 長・同時フィルタ数） | Phase 0-6 のベースラインと比較 | 4 |
| U-5 | `new-gui` と `unified-shell` のどちらを正とするか | `docs/2026-09-18_switch_to_3003_RUNBOOK.md` の運用状況を確認 | 2, 3, 5 |
| U-6 | ReplayGain タグの有無（実ライブラリ） | MPD のタグ調査 | 5-4 |

## 8. 親文書への反映事項

本書の作成にあたり、親文書 `docs/DSP_FEATURE_EXPANSION_PROPOSAL.md` に対して以下を反映する形にしている。

| 親文書の記述 | 本書での扱い |
|---|---|
| §4.2「出力機器補正は最後」 | §5.1 に CTC 時の例外を追加 |
| §3 と §7.6 で優先順位が異なる | 本書 §3 の Phase 0〜7 を**唯一の順序**とする |
| §4.4 ゲイン管理 | Phase 0-4（検査）と Phase 1-7（自動算出）に分解 |
| §2.3 空間演出 | Phase 4 で「まず WET ゲインを評価可能な値に直す」を先頭に置いた |

---

## 付録A: 実測で `--check` 通過を確認した 4経路の骨格

`camilladsp --check` が **rc=0（Config is valid）** を返すことを実測済み（F-8）。Phase 3 のクロスフィードと Phase 6 の CTC はこの骨格を共有する。

```yaml
filters:
  dx:   {type: Delay,  parameters: {delay: 0.3, unit: ms, subsample: false}}
  g:    {type: Gain,   parameters: {gain: -6.0, inverted: false, mute: false}}
  lp:   {type: Biquad, parameters: {type: Lowpass, freq: 700, q: 0.707}}
  # 交差経路は経路ごとに別ファイルを参照する（F-9）
  cvLR: {type: Conv,   parameters: {type: Wav, filename: /path/ir_LtoR.wav}}
mixers:
  split4:
    channels: {in: 2, out: 4}
    mapping:
      - {dest: 0, sources: [{channel: 0, gain: 0.0}]}   # 直接 L
      - {dest: 1, sources: [{channel: 1, gain: 0.0}]}   # 直接 R
      - {dest: 2, sources: [{channel: 0, gain: 0.0}]}   # L → R 経路
      - {dest: 3, sources: [{channel: 1, gain: 0.0}]}   # R → L 経路
  sum4:
    channels: {in: 4, out: 2}
    mapping:
      - {dest: 0, sources: [{channel: 0, gain: 0.0}, {channel: 3, gain: -6.0, inverted: true}]}
      - {dest: 1, sources: [{channel: 1, gain: 0.0}, {channel: 2, gain: -6.0, inverted: true}]}
pipeline:
  - {type: Mixer, name: split4}
  - {type: Filter, channels: [2, 3], names: [lp, g]}   # 反対耳パス（クロスフィード）
  - {type: Mixer, name: sum4}
```

**実測で確認した注意点**

- `Delay` は `unit: ms` と `unit: samples` の両方で受理される
- `Conv` の `channel` は **0 始まり**。2ch の IR に `channel: 2` を指定すると `Cant read channel 2 ... contains 2 channels` で rc=101
- 2→4 分割＋経路別フィルタ＋4→2 合成は受理される（これが CTC 実現性の根拠）

## 付録B: 検証コマンド集

```bash
cd /home/tysbox/HQ_Linux_Music_Player

# 単体テスト（すべて）
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v

# G1: CamillaDSP の受理確認
camilladsp --check /tmp/camilladsp/active_dsp.yml

# 稼働中の設定を壊さずに YAML を取得（tests/tools/yaml_probe.py の想定）
./backend/venv/bin/python3 tests/tools/yaml_probe.py --config '{"music_type":"classical","crossfeed":"30"}'

# 稼働中の設定ファイルの同一性確認（Phase 0-1 の判定）
md5sum /tmp/camilladsp/active_dsp.yml

# 現在の設定内容（復元・確認用）
cat ~/.config/audiophile/last_config.json
```

## 付録C: 本書作成時の副作用の記録

- 本書の検証で生成YAMLを実測した際、検証スクリプトが **`/tmp/camilladsp/active_dsp.yml` を上書き**した（CamillaDSP は稼働中）。直ちに `~/.config/audiophile/last_config.json` から再生成して復元した（復元後の md5: `be114713aa553ff1ec503d53b52b106e`、`camilladsp --check` rc=0）。
- **CamillaDSP への reload は送っていないため、稼働中の音声処理には影響していない。** リポジトリ内のファイルは変更していない（作成物は `/tmp` のみ）。
- この事故自体が **F-17（テスト・検証スクリプトが稼働中ファイルを上書きする）** の実例であり、Phase 0-1 を最優先に置く根拠である。

---

- 本書は**計画のみ**を示す。記載した実装・測定は行っていない。
- 難易度・工数感は相対的な目安であり、期間や音響効果を保証するものではない。
- Android 側のコード・データ・エクスポート仕様は未確認である（U-3）。