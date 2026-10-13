# Bisen-DSP-System 機能移植計画 — ホンキャリブレーション / Tube / Restore / Info

- **移行元**: `tysbox/Bisen-DSP-System` ブランチ `feature/gapless-phase-v5`（ローカルクローン: `/home/tysbox/Bisen-DSP-System`）
- **移行先**: HQ Linux Music Player（本リポジトリ）
- **対象機能**（利用者指定）:
  1. ホンキャリブレーション（AutoEq ベース ヘッドホン補正）
  2. Tube（真空管サチュレーション）
  3. Restore（レストレーション）
  4. Info（信号真理・制作クレジット・VU/LUFS 表示）
- **作成日**: 2026-10-12（rev.2 同日更新）
- **ステータス**: **実装進行中** → §9 進捗・HANDOVER を最新の状態に保つこと
- **rev.2 の決定事項（利用者指示 2026-10-12）**:
  - **LUFS 機能は不要** → §3-D・Phase 2 から削除済み
  - **Tube / Restore は CamillaDSP 以外の手法（独自 DSP デーモン）での本物移植**を主案に変更 → §3-B/3-C・Phase 3
  - **キャリブレーション / Info の高精度・高機能拡張**（FIR 全帯域モード、ファイル真理、リッチクレジット）を追加 → §3-A/3-D
- **rev.3 の決定事項（利用者指示 2026-10-12）**:
  - **2,810 機種の計測カタログを同梱**（D-4 改訂）→ config/profiles/catalog.json
  - **リキャリブレーション機能（Bisen targetCurveId 相当）を実装**（§3-A-3）→ backend/dsp/headphone.py
  - **Info は MusicBrainz + Discogs + Wikipedia の 3 ソース統合**（Bisen V6.1 アーキテクチャ完全移植）→ hq_api/routers/info.py
  - **GUI は Android（Bisen）と同一仕様**: HP CALIBRATION Popup（モバイル＝ボトムシート / PC＝横長）、LISTENING WIKI 3タブ、黒/シルバーパネルの左=リスニング機種/右=リキャリブ先表示

---

## 1. 前提 — 2 アーキテクチャの決定的な違い

| 項目 | BiScene Audio（Bisen） | HQ Linux Music Player |
|---|---|---|
| DSP エンジン | 独自ネイティブ C++（`libbiscene_native_dsp`）+ Web Audio | CamillaDSP 4.1.3（Rust, YAML 設定） |
| 信号経路 | デコーダ → NativeDspChain → USB / AudioTrack | MPD → ALSA Loopback → CamillaDSP → DAC |
| 処理の自由度 | 無制限（サンプル単位・非線形・状態依存 OK） | YAML で宣言できるフィルタのみ |
| 利用可能フィルタ | 自由実装 | Gain / Biquad / Conv / Delay / Volume / Loudness / Compressor / Limiter / Mixer |
| 非線形処理（tanh 等） | ○ 実装済み（TubeModel / RestorationEngine） | ✕ **存在しない**（検証済み: `camilladsp -c` で WaveShaper は Invalid） |

> **検証記録 (2026-10-12)**: 実機の camilladsp 4.1.3 に対し、WaveShaper 型フィルタを含む設定を
> `-c` 検証した結果、Invalid config で拒否。CamillaDSP の表現力は
> 「線形フィルタ（Biquad/Conv/Gain 等）+ ダイナミクス（Compressor/Limiter/Loudness）」に限られる。
> したがって **移植可否は「そのエフェクトが線形フィルタ+ダイナミクスで表現できるか」で決まる**。

### 1-1. すでに移植済みの Bisen 由来機能（再実装しないこと）

`backend/dsp/yaml_generator.py` を確認したところ、以下は**本計画の対象外**（実装済み）:

- **Source EQ**（jazz / classical / electronic / vocal）— Bisen `SOURCE_EQ_PRESETS` と係数同一
- **Output EQ**（studio / JBL / planar / loud / crystal）— Bisen `OUTPUT_EQ_PRESETS` と同一 + 独自 `Tube-Warmth` EQ
- **Ambience**（Reverb IR: hall / jazz_club / large_bottle_hall / st_nicolaes_church）— Bisen IR + WET トリム (`REVERB_WET_TRIM_DB`)
- **Crossfeed / Hum Filter / 絶対位相 (absolute_phase) / CTC / Tilt EQ / Balance / ISO226 Loudness**

### 1-2. ライセンス

- Bisen-DSP-System は利用者自身のリポジトリ（自由に移植可）。
- AutoEq 測定データ（oratory1990 / crinacle 等）は出典記載が必須 → 既存スキーマの `source` フィールドで記録する（`docs/schemas/dsp_profile.schema.json` の設計どおり）。
- CamillaDSP は設定 YAML を生成するのみでプロセス結合はないため、ライセンス影響なし。

---

## 2. 機能別 移植可能性 総評

| 機能 | 移植可能性 | 移植方式 | 理由 |
|---|---|---|---|
| **ホンキャリブレーション** | ★★★ ほぼ完全 | AutoEq バンド → CamillaDSP Biquad 1:1 変換 | PEQ (peaking/lowshelf/highshelf) + preamp は Gain+Biquad で等価表現可。基盤（スキーマ/ローダ/API）は既存 |
| **Info（信号真理・クレジット・VU・LUFS）** | ★★★ ほぼ完全 | MPD status + CamillaDSP WebSocket + MusicBrainz API | いずれもデータ取得と表示の問題で、DSP 表現力の制約を受けない |
| **Tube（真空管サチュレーション）** | ★★★ 完全移植（方式2・主案） | 独自 ALSA DSP デーモン `bisen-dspd` に Bisen 製 C++（TubeModel 等）をそのまま移植し、非線形処理を本物で実現 | Bisen C++ は `cmath` 依存のみで Linux でビルド可能（自作コード）。ループバックに空きサブストリームを実測確認 |
| **Restore（レストレーション）** | ★★★ 完全移植（方式2・主案） | Tube と同一デーモン内に移植（RestorationEngine + TruePeakLimiter）。チェーン順も Bisen 忠実（restoration → tube → limiter） | 過渡検出・高調波添加・適応パンチまで全て忠実に再現 |
| （参考）方式1: CamillaDSP のみで構成する近似 | ★★ 近似 | Tube-Warmth EQ + Compressor（Sag 近似）+ Limiter / 高域シェルブ | tanh 高調波は線形フィルタで生成不可。rev.2 で主案からは外れたが代替として §3-B/3-C に残す |

---

## 3. 機能別 詳細検討

### 3-A. ホンキャリブレーション → 完全移植（Phase 1）

**Bisen 側の資産**:

| ファイル | 内容 | 移植先 |
|---|---|---|
| `src/dsp/headphoneProfiles.ts` | 内蔵 8 プロファイル（HIFIMAN Deva Pro, AKG K702/K371, Etymotic ER4SR, ATH-M50x, HD650 等）。preampGainDb + 最大 10 バンド PEQ | `~/.config/audiophile/profiles/*.json`（スキーマ準拠 JSON へ変換） |
| `src/dsp/customProfileStorage.ts` | AutoEq `ParametricEQ.txt` パーサ + 保存 | `backend/dsp/autoeq.py`（新規・Python 移植） |
| `src/dsp/onlineAutoEq.ts` | AutoEq GitHub（jaakkopasanen/AutoEq）を Contents API で走査・検索・`ParametricEQ.txt` 取り込み | `hq_api` 新規ルータ（**サーバー側実行**を推奨。キャッシュ・レート制御が容易） |
| `src/dsp/totalCurve.ts` | 全 DSP 段の合成周波数応答（+calibrationIntensity スケーリング） | `new-gui` 内 TS としてほぼそのまま移植 |
| `src/components/HeadphoneCalibrationDrawer.tsx` (778 行) | プロファイル選択 / 強度スライダ / カーブ表示 UI | `new-gui` パネルに簡素化移植 |
| `docs/PHONE_CALIBRATION_SPEC_20260901.md` | 仕様書 | `docs/` 参照資料として複写可 |

**HQ 側の既存基盤（作りかけで止まっている部分）**:

- `backend/dsp/profiles.py` — JSON Schema 検証付きローダ。`type: headphone` / `purpose: device_correction` / `preamp_db` / bands（最大 20）に**既に対応**。`profile_to_biquads()` で CamillaDSP Biquad 形式への変換関数**も既存**。
- `hq_api/routers/dsp_readonly.py` — `GET /api/dsp/profiles`（一覧）と `GET /api/dsp/profiles/{id}` は**実装済み**。
- `~/.config/audiophile/profiles/` — sony-wh1000xm5-harman2018 等が既に 3 件存在。
- **しかし** `yaml_generator.py` は `load_profile` / `profile_to_biquads` を import しているだけで**パイプライン生成に使っていない**。`AudioConfig` / `DspParams`（`backend/dsp/models.py`）に headphone 系フィールドもない。
- 残作業は「**設定モデル → YAML 生成 → 適用 API → GUI** の接続」に集約される。

**変換規約（等価性の担保）**:

| Bisen (AutoEq) | CamillaDSP | 備考 |
|---|---|---|
| `preampGainDb`（例 -6.5） | `Gain` フィルタ（パイプラインのキャリブレーション Biquad 直前に挿入） | 負値が基本（ブースト帯のヘッドルーム確保） |
| band `peaking` | `Biquad: Peaking` | 1:1 |
| band `lowshelf` / `highshelf` | `Biquad: Lowshelf / Highshelf` | 1:1 |
| `calibrationIntensity` (0–1) | 各 band の `gain *= intensity` | Bisen ネイティブの `calibScale` と同じ意味論 |
| バンド数 10 | スキーマ上限 20 本 | CamillaDSP の Biquad 直列数に実質制限なし |

**ヘッドルーム安全性**: Stage 2 の自動ヘッドルーム計算（`backend/dsp/analysis.py: max_gain_of_config`）が既存のため、
キャリブレーション Biquad 列をパイプラインに加えた**後**にヘッドルームを再計算すればクリップ防止は自動。
Preamp はキャリブレーション Biquad の**前**に置く（AutoEq の意味論: preamp → 補正 EQ）。

#### 3-A-2. Bisen を超える高精度・高機能オプション（rev.2 追加）

10 バンド PEQ（Bisen と同等）を基本としつつ、HQ 側の既存資産を活かすと **Bisen より高い精度・機能**が可能。
根拠: Conv フィルタ（WAV IR 読込）は Reverb IR で実績済み、venv に **numpy 2.5.3 / scipy 1.18.1 を確認済み**。

| 拡張 | 内容 | 精度・効果 |
|---|---|---|
| **FIR 全帯域モード（高精度）** | AutoEq の `GraphicEQ.txt`（127 バンド）または測定 CSV から **minimum-phase FIR** を生成（scipy: `firwin2` + `minimum_phase`）し、WAV IR として CamillaDSP `Conv` で畳み込み | PEQ の 10 制御点 → **全帯域連続補正**に向上 = Bisen（ネイティブも 10 バンド biquad）を超える精度。機構は既存 Reverb IR と同一で導入リスク小。**minimum-phase 推奨**（pre-ringing 無し・アナログ EQ 的挙動） |
| **リキャリブレーション（他機種シミュレート）** | Bisen 機能「別のヘッドホンの音をシミュレート」を移植: EQ(自機→Harman) + inverse(EQ(目標機→Harman))。FIR 領域で演算すれば高精度 | 現在の機種から別機種の音への変換。PEQ 領域では近似、FIR 領域では高精度 |
| **スピーカー / ルーム補正** | スキーマは `type: speaker` に対応済み。REW 等の測定インポータで上記 FIR 資産を流用可能 | Bisen に無い領域（HQ 独自の拡張余地） |

**拡張の限界（正直な評価）**:
- 装着個体差（パッド経年・装着位置）は AutoEq の平均測定では補正できない。
  → 「自前測定 CSV インポート」を将来追加すればこの限界を突破可能。
- 2ch DAC 経路のため音色補正は周波数領域が上限。HRTF 級の空間補正は CTC（実装済み・別機能）の役割。
- FIR モードはレイテンシがやや長い（min-phase でも数 ms 程度）— 音楽再生では無問題。

### 3-B. Tube → 方式2: 完全移植（主案）/ 方式1: 近似（代替）

**Bisen の実装**（`android/app/src/main/cpp/dsp/TubeModel.cpp`）:

```
TRIODE(300B):  s = tanh((x + bias*0.2) * 1.1);  y = s + 0.12*s²   ← 偶数次高調波
PENTODE(KT88): y = tanh((x + bias*0.2) * 1.3) / 1.05
Sag:           env = attack 0.9992 / release 0.9998 で (L²+R²)/2 の包絡
               gain = 1 / (1 + env * 0.35)                    ← 大音量で電源が垂れる挙動
DC 除去:       1-pole HPF @ ~5Hz（バイアスオフセットの排除）
```

#### 方式2（主案・完全移植）: 独自 ALSA DSP デーモン `bisen-dspd` による本物の非線形処理

**結論: 可能**（rev.2・利用者指示により主案化）。根拠は 3 点:

1. Bisen の DSP 部（`TubeModel` / `RestorationEngine` / `TruePeakLimiter` / `PhaseInverter`）は
   `cmath` / `algorithm` / `vector` しか使わないプラットフォーム非依存の C++ で Android 依存が一切ない
   → **Linux 向けにそのままビルド・移植できる**（自作コードのためライセンス制約も無い）。
2. ALSA ループバックに**空きがある**（実測: `pcm_substreams=8`、現行は sub0 のみ使用 → 第 2 ホップに sub1 を使用可）。
3. `switch_audio.sh` のモード分岐を 1 箇所拡張するだけで、既存構成（直結）へのフォールバックも自動化できる。

**信号チェーン（実測に基づく設計）**:

```
現行:  MPD ─ hw:Loopback,0,0 ─▶ [capture hw:Loopback,1,0] CamillaDSP ─▶ plughw:1,0 (DAC)

追加:  MPD ─ hw:Loopback,0,0 ─▶ CamillaDSP ─ hw:Loopback,0,1 ─▶ [capture hw:Loopback,1,1]
                               (EQ/IR/crossfeed 等)             bisen-dspd
                                                                restoration → tube → TruePeakLimiter
                                                                ─▶ plughw:1,0 (DAC)
```

設計詳細:

- **形式**: ループバック間は S32_LE / 192kHz 固定（`/etc/mpd.conf` 192000:32:2、`active_dsp.yml` 実測）
  → デーモン内で int32↔float32 変換（Tube/Restore は float32 前提）。
- **チェーン順序は Bisen 本体に忠実に**（`NativeAudioEngine.cpp` L227-252 実測:
  hum → EQ → restoration → tube → spatial → compressor → limiter → phase 最終段）。
  HQ では hum / EQ / spatial（crossfeed・CTC）は CamillaDSP 担当のため、
  **デーモンは restoration → tube → TruePeakLimiter → absolute_phase のみ担当**（二重処理なし）。
- **レート適応（移植時の必須作業）**: Bisen の 1 極係数は 96kHz 前提のハードコード。HQ は 192kHz なので
  時定数保存変換 `f₂ = f₁^(96/192) = √f₁` を適用:
  Sag attack 0.9992→0.99960 / release 0.9998→0.99990 / DC blocker 0.9995→0.99975 /
  restoration release 0.9996→0.99980。TruePeakLimiter はレート対応済み。tanh 伝達自体はレート非依存。
- **制御 API**: Unix domain socket（localhost 専用・決定 D-8）で enabled / tube_type(300B|KT88) / bias /
  restore / restore_intensity / bypass を再生中に可変更新。Bisen は std::atomic でパラメータ安全性を
  担保済み → 実装もそのまま流用。
- **運用**: systemd `bisen-dspd.service`（Restart=always / WatchdogSec / SCHED_FIFO 50 = camilladsp と同位）。
- **フォールバック**: デーモン停止時・Tube/Restore 無効時は `switch_audio.sh` が
  「CamillaDSP → DAC 直結」（= 現行構成）へ切戻す。**デーモンは Tube/Restore 有効時のみ必要**で、
  他機能（EQ・Reverb・キャリブレーション・Info）に影響しない。
- **レイテンシ**: +1 ALSA ホップ ≈ 数 ms @192kHz（chunksize 4096 実績値）。音楽再生では無視可能。実測して記録。
- **音量の意味論**: CamillaDSP の音量は tube の前段 = プリアンプ→パワーアンプ型
  （音量でドライブ感が変わる実機のアンプと同じ挙動）。これを維持する（決定 D-6）。

#### 方式1（代替・近似）: CamillaDSP のみで構成

CamillaDSP で再現できる要素 / できない要素:

| TubeModel の要素 | CamillaDSP での近似 | 忠実度 |
|---|---|---|
| 偶数次高調波（tanh + s²） | **不可**（線形フィルタでは高調波を生成できない） | 0% — 音色の核が失われる |
| 電源 Sag（レベル依存の圧縮） | `Compressor`（ソフトニー）で近似。attack/release を 300B/KT88 で変える | 動的挙動の傾向は再現可 |
| 温かい音色（歪みの結果としての傾き） | 既存 `Tube-Warmth` EQ（200Hz +2.5dB / 4kHz -1.5dB / 10kHz -2dB） | 聴感近似 |
| DC 除去 | 不要（そもそもバイアス DC を生成できない） | N/A |
| bias パラメータ | Compressor の threshold / knee / makeup へのマッピング | 制御の意図は踏襲可 |

**推奨する実装**: `tube` を 1 エフェクトとしてモデル化し、YAML 生成時に
「Tube-Warmth EQ + Compressor（Sag 近似）+ Limiter（安全弁）」の 3 点チェーンを合成して出す。
GUI パラメータは Bisen と同じ 2 つ（`tube_type: 300B|KT88`, `tube_bias: 0-100`）を維持し、内部でマップ:

| パラメータ | 300B (TRIODE) | KT88 (PENTODE) |
|---|---|---|
| Compressor ratio | 1.5:1（穏やか） | 2.0:1（やや強い） |
| threshold | bias 増 → 浅く（例: -24 + bias*0.12 dB） | 同左 |
| knee | 9 dB（ソフト） | 6 dB |
| attack / release | 20ms / 300ms | 10ms / 200ms |
| makeup | bias に比例 +0〜3dB | 同左（やや大きめ） |
| 後段 Limiter | threshold -1.0dB | threshold -1.5dB |

> **位置づけ（rev.2）**: 方式1 は「CamillaDSP 構成のみで完結させたい場合」の代替案。
> 方式2（本物移植）が主案となったため Phase 3 では採用しないが、パラメータ設計の参考として本節を残す。

### 3-C. Restore → 方式2 で完全移植（Tube と同一デーモン・主案）

**Bisen の実装**（`android/app/src/main/cpp/dsp/RestorationEngine.cpp`）:

```
過渡検出:    env = |x - prev| の包絡（release 0.9996）
高調波添加:  wet = tanh(x*1.05);  harmonics = (wet - x) * 0.08   ← 高域寄りの非線形
過渡パンチ:  gain = 1 + min(0.5, env * 0.65 * 15)                ← 最大 +3.5dB の上向き伸張
```

**方式2（主案）**: restoration → tube の順（Bisen チェーン忠実）で Tube と同一デーモン `bisen-dspd` に移植。
追加作業は 192kHz 向けレート変換（release 0.9996 → 0.99980）のみ。

**Restore 3 モード固定切替（2026-10-13 利用者指示 — Bisen 将来構想に合わせた設計採用）**:

強度スライダ方式（`restore_intensity`）は廃止し、3 段階のモード切替に一本化:

| モード (制御値) | 対象ソース | punch | harmonicGain | HF強調 | 目的 |
|---|---|---|---|---|---|
| `lossy_standard` | Lossy (MP3) 192〜320kbps 級 | 0.65 | 0.08 | — | **擬似ロスレス** (Bisen V4.5.6 デフォルト値) |
| `lossy_high` | Lossy (MP3) 低ビットレート (128kbps 級) | 0.85 | 0.13 | 0.25 | **補完度を高くした擬似ロスレス** (16kHz 帯域欠損を重点補完) |
| `cd` | Lossless (CD) | 0.30 | 0.06 | 0.50 | **疑似ハイレゾ** (10-20kHz 倍音 → 20kHz 超の超音波帯生成) |

- HF 強調 = tanh ドライブへの 1-pole HPF (fc≈6kHz) 成分加算。高域の曲率が増え
  HF/超音波帯倍音が強化される (CD は 30kHz 倍音が標準モードの約 1.7 倍 — テスト実測)。
- punch はモードで差別化: 低ビットレートは過渡も荒れているため強め、
  CD は過渡が無傷のため絞り、代わりに帯域拡張に専念。
- 制御: `set restore_mode lossy_standard|lossy_high|cd` (Unix socket)。
- 実測 (test_dsp_chain): 過渡伸張の順序 lossy_high (0.0776) > lossy_standard (0.0747) > cd (0.0630)、
  静寂は静寂のまま、超音波倍音 cd 0.000516 > std 0.000298。

**方式1（代替・CamillaDSP のみ）で再現できる要素 / できない要素**:

| RestorationEngine の要素 | CamillaDSP での近似 | 忠実度 |
|---|---|---|
| 高調波添加（tanh 差分） | **不可**（非線形） | 0% |
| 適応過渡ゲイン（上向き伸張） | **不可**（Expander が存在しない。Compressor は下向きのみ） | 0% |
| 高域の瑞々しさ（結果としての聴感） | `Highshelf` EQ（例: +3dB @ 8kHz, Q 0.7）+ 全体 Limiter | 聴感近似 |

方式1の実装参考: 「高域シェルブ（強度で 0〜+4dB スケール）+ Limiter(-1.0dB)」。
強度 50% で高域 +2dB 程度を想定。rev.2 では主案から外れた（方式2 が本物を担うため）。

### 3-D. Info → ほぼ完全移植 + Bisen を超える拡張（Phase 2）

**LUFS は利用者指示により廃止（2026-10-12）**。残る 3 機能に加え、rev.2 で「Bisen 超え」拡張を追加:

| 機能 | HQ での実現手段 | 既存資産 |
|---|---|---|
| **信号真理**（format / srcRate / srcBits） | MPD `status` の `audio: "44100:16:2"` → `format_now_playing()` が**既に** `audio` フィールドとして返却済み。GUI 表示を追加するだけ | `hqmplayer_core/meta/formatting.py:89` |
| **ファイル真理（Bisen 超え）** | MPD currentsong のファイルパスを `ffprobe` で解析 → ファイル本来のコーデック / ビット深度 / サンプリングレート / ビットレートを表示（MPD の audio はデコード後の値、ffprobe はファイル原本の値） | **ffmpeg CLI は未導入**（lib のみ）→ `apt install ffmpeg` が必要（決定 D-7）。未導入なら当該表示を省略する設計 |
| **出力真理（Bisen 超え）** | CamillaDSP WS の state で処理中レート/フォーマット（192kHz S32 等）を表示 → 「ファイル → DSP → DAC」の 3 段の真理表示 | `routers/dsp.py` に CamillaClient 実績 |
| **VU メータ**（peakL/peakR） | CamillaDSP WS levels を 8002 中継で取得。**Phase 3 のデーモン完成後は bisen-dspd が実際に DAC へ出す信号の true-peak（TruePeakLimiter が 4x オーバーサンプリングで計算済み）に切替可能** → Bisen（レンダラの float ピーク報告）より高精度 | camilladsp lib `levels.py` |
| **制作クレジット** | 新規ルータ `GET /api/info/credits`。MusicBrainz + キャッシュ。**Bisen 超え拡張**: ISRC / レーベル / 発売日・国 / ジャンル / アーティスト関係（メンバー・プロデューサー・マスタリング）まで構造化表示。Discogs フォールバック可。UI は Bisen `WikiModal.tsx`（282 行）を移植 | アートキャッシュ（`hqmplayer_core/art`）と同一パターン |

**できないこと（正直な評価）**: リアルタイムスペクトラム表示は CamillaDSP の levels API では不可能
（RMS/peak のみで FFT 無し）。ただし Phase 3 のデーモンは全 PCM を握っているため、
将来デーモン側で FFT を計算して公開すれば**実現可能**（Phase 5 の将来オプションに記載）。

**MusicBrainz API の運用注意**: User-Agent にアプリ名+連絡先を必須化、レート制限 1 req/sec を厳守、
応答は `~/.cache/audiophile/musicbrainz/` に永続キャッシュ（オフライン再利用）。エンドポイントは非同期 (run_in_executor) で実装。

---

## 4. 段階的実装計画

原則: **各 Phase は独立して価値を持ち、1 Phase = コミット群 + テスト緑 + 実機確認**で進める。
優先順位（rev.2）: Phase 1 ホンキャリブレーション → Phase 2 Info → Phase 3 bisen-dspd（Tube/Restore 本物移植）→ Phase 4 連携強化。

**設計原則の改定（rev.2）**: 従来の「全 DSP を CamillaDSP に一本化」は次のように改定する:
「**設定ベースの DSP（EQ / IR / ダイナミクス / ラウドネス）は CamillaDSP に一本化**し、
**サンプル単位の非線形段（Tube / Restore）のみ bisen-dspd に分離**する」。
CamillaDSP の YAML 生成・運用（CamillaGUI・状態管理・レート切替・障害設計）はそのまま生かし、
非線形段だけを出力直前の独立プロセスに置く。

### Phase 1: ホンキャリブレーション（最優先・ほぼ完全移植）— 見込み 2〜3 日

| Step | 内容 | 成果物 |
|---|---|---|
| 1-1 | `models.py` の `AudioConfig`/`DspParams` に `headphone_profile: str = "none"` / `headphone_intensity: int = 50` を追加 | backend |
| 1-2 | `yaml_generator.py`: プロファイル選択時、パイプライン先頭に preamp `Gain` + キャリブレーション Biquad 列（`profile_to_biquads` 使用、gain×intensity）を注入。ヘッドルーム再計算が自動で効くことを確認 | backend |
| 1-3 | Bisen 内蔵 8 プロファイル（`headphoneProfiles.ts`）を JSON スキーマ準拠 JSON に変換して `~/.config/audiophile/profiles/` に格納（source に出典明記） | profiles |
| 1-4 | `backend/dsp/autoeq.py` 新規: AutoEq `ParametricEQ.txt` パーサ（`customProfileStorage.ts` の Python 移植）+ `tests/unit/test_autoeq.py` | backend + test |
| 1-5 | `hq_api` 新規ルータ: `GET /api/dsp/autoeq/search?q=` / `POST /api/dsp/autoeq/import`（サーバー側 GitHub API、`onlineAutoEq.ts` 移植、応答キャッシュ） | hq_api |
| 1-6 | `new-gui`: キャリブレーション パネル（プロファイル選択・強度スライダ・応答カーブ表示。`totalCurve.ts` + `HeadphoneCalibrationDrawer.tsx` の簡素化移植） | GUI |
| 1-7 | 検証: 単体テスト + 生成 YAML を `camilladsp -c` で検証 + 実機 A/B 聴取 | test |
| 1-8 | （後追加・決定 D-5）FIR 全帯域モード: `GraphicEQ.txt` → min-phase FIR 生成（scipy）→ Conv 用 WAV IR。PEQ モードと併存選択式 | backend + test |

**Phase 1 の受け入れ条件**: 任意の AutoEq プロファイルを選択し強度 0〜100% を動かしたとき、
生成 YAML が常に valid で、preamp・全 Biquad・ヘッドルームが仕様どおりに変化すること。

### Phase 2: Info 機能（見込み 2〜4 日）

| Step | 内容 | 成果物 |
|---|---|---|
| 2-1 | 信号真理表示: `/ws/now_playing` 既存 `audio` フィールドを GUI のフォーマットバッジ（例: FLAC 44.1kHz/16bit）に表示 | GUI 中心 |
| 2-2 | VU メータ: `hq_api` に `/ws/levels`（CamillaDSP :1234 からのレベル中継）を追加し、`VuMeter.tsx` 移植 | hq_api + GUI |
| 2-3 | MusicBrainz クレジット: `GET /api/info/credits`（キャッシュ・レート制限付き）+ Info パネル（`WikiModal.tsx` 移植） | hq_api + GUI |
| 2-4 | ファイル真理 + 出力真理: ffprobe（決定 D-7 導入時）と CamillaDSP state を Info に統合。「ファイル → DSP → DAC」の 3 段表示 | hq_api + GUI |

### Phase 3: bisen-dspd — Tube / Restore の本物移植（見込み 3〜5 日）

Bisen の C++（TubeModel / RestorationEngine / TruePeakLimiter / PhaseInverter）を独自 ALSA デーモンとして移植し、
純正の非線形処理そのものを得る（§3-B 方式2）。近似（方式1）は採用しない。

| Step | 内容 | 成果物 |
|---|---|---|
| 3-1 | `dmp/bisen-dspd/`（新規）: CMake + ALSA capture/playback スケルトン、S32_LE↔float32 変換、192kHz 動作確認 | C++ |
| 3-2 | DSP 本体移植: 4 ファイルをコピーし、96k→192k の**時定数保存変換（√f）をパラメータ化**（§3-B 変換表） | C++ |
| 3-3 | 制御 API（Unix domain socket）: enabled / tube_type / bias / restore / restore_intensity / bypass。std::atomic による再生中の安全な更新 | C++ |
| 3-4 | systemd ユニット `bisen-dspd.service`（Restart=always / WatchdogSec / SCHED_FIFO 50）+ `config/systemd` テンプレート | systemd |
| 3-5 | `switch_audio.sh` 拡張: Tube/Restore 有効時は CDSP playback → `hw:Loopback,0,1`・デーモン → DAC。無効時・障害時は現行の直結構成（=フォールバック） | shell |
| 3-6 | `models.py` / `dsp_apply` に tube / restore フィールド追加、hq_api がデーモン制御を仲介 | backend + hq_api |
| 3-7 | GUI: Tube トグル + 球種(300B/KT88) + bias ダイヤル、Restore トグル + 強度スライダ | GUI |
| 3-8 | 検証: ゴールデンサンプル（数値一致）+ passthrough lossless + xrun ゼロ soak（30 分）+ レイテンシ実測 + 実機 A/B | test |

**Phase 3 の受け入れ条件**:
- tube off + restore off のとき、デーモンは **bitwise passthrough**（S32→float→S32 往復が lossless）であること
- 任意パラメータで 30 分連続再生 xrun ゼロ・メモリ RSS 横ばいであること
- bisen-dspd 停止 → `switch_audio.sh` が自動で直結構成へ復帰すること

### Phase 4: Info × デーモン連携（見込み 0.5〜1 日）

| Step | 内容 | 成果物 |
|---|---|---|
| 4-1 | VU をデーモン由来の true-peak（TruePeakLimiter の計算値を制御 API 経由で公開）に切替えるオプション | hq_api + GUI |
| 4-2 | 出力真理にデーモン状態（tube/restore 稼働・バイパス状態）を統合表示 | GUI |

### Phase 5（将来オプション）: さらに先

- **CamillaDSP フォーク（WaveShaper 追加）は不要化** — 方式2 が成立したため保守負荷だけが残る。採用しない。
- **リアルタイムスペクトラム**: bisen-dspd 内で FFT 計算 → WS 公開（デーモンが全 PCM を持つため原理的に可能）
- **自前測定 CSV インポート**: キャリブレーションの限界（装着個体差）を突破
- **restore 定数の GUI 化**: punch / harmonicGain をユーザー調整可能に拡張（§3-C の Bisen 超え）

---

## 5. 横断リスクと対策

| # | リスク | 影響 | 対策 |
|---|---|---|---|
| R-1 | キャリブレーション preamp（-6dB 等）+ 既存 EQ ブースト + Tube makeup の合計でクリップ | 音割れ | Stage 2 自動ヘッドルーム（`max_gain_of_config`）が全フィルタを考慮するよう、**フィルタ注入順序を統一**してから再計算。YAML スナップショットテスト（`test_dsp_yaml_snapshot.py`）に新フィルタを追加 |
| R-2 | Pure モード（DSP バイパス）でキャリブレーション/Tube/Restore が無音になる誤解 | UX 混乱 | GUI で `mode=pure` 時は該当コントロールを無効化 + 「DSP モードでのみ有効」注記 |
| R-3 | AutoEq オンライン検索の GitHub API レート制限（anonymous 60/h） | 検索失敗 | サーバー側で 30 分キャッシュ（Bisen 実装の `CACHE_TTL_MS` 踏襲）+ 失敗時は内蔵プロファイルへフォールバック |
| R-4 | MusicBrainz 規約違反（UA 未設定・過密アクセス） | API 禁止 | UA 必須 + 1 req/sec 制限 + 永続キャッシュ。テストでは録画レスポンス（fixture）を使用し実 API を叩かない |
| R-5 | CamillaDSP WS (1234) 直接参照の CORS / 認証 | VU メータ不動 | 8002 (hq_api) 経由の中継 WS に一本化。README の「必ず8002」原則を遵守 |
| R-6 | Compressor/Limiter 追加によるレイテンシ・チャンク影響 | 音途切れ | Compressor はブロック処理で遅延ゼロ。chunksize 16384 の実績値（Root Fix B）を維持し、アンダーランカウンタで回帰監視 |
| R-7 | 設定スキーマ拡張による旧プリセット（last_config.json）の非互換 | 起動失敗 | 新フィールドはすべてデフォルト値付きで追加（Pydantic が既存 JSON をそのまま受理）。`test_dsp_applied.py` に旧形式フィクスチャを残す |
| R-8 | bisen-dspd 異常終了時に DAC が無音になる | 再生中断 | systemd Restart=always + WatchdogSec + `switch_audio.sh` による直結構成への自動復帰（Phase 3-5）。復帰までの空白時間を実測記録 |
| R-9 | 第 2 ループバックホップによる追加レイテンシ | 同期ズレ（動画視聴時など） | @192kHz で数 ms。音楽専用用途のため影響なし。実測値を §8 に記録 |
| R-10 | camilladsp と bisen-dspd の SCHED_FIFO 競合 | xrun | 同優先度 50。バッファ設計は camilladsp 実績値を参考に設定し、soak テストで xrun ゼロを確認 |
| R-11 | ffmpeg CLI 未導入（ファイル真理表示に必要） | 機能欠落 | `apt install ffmpeg`（任意依存・決定 D-7）。未導入環境では当該表示を自動省略 |
| R-12 | 192kHz での Bisen 定数の時間定数ズレ | 音質の再現性喪失 | √f 変換（§3-B）と Python 参照実装との数値一致テスト（§7）で担保 |
| R-13 | 音量が tube 前段にあることによる挙動変化 | 音量でドライブ感が変わる | 実機アンプと同じ挙動として意図的に維持（決定 D-6）。不満が出れば tube 後段への音量移動を将来検討 |

## 6. 意思決定が必要な点（着手前の確認事項）

| # | 質問 | 状況 / 推奨 |
|---|---|---|
| D-1 | ~~Tube/Restore は近似でよいか~~ | **解決済（2026-10-12）**: 利用者指示により**独自デーモン（方式2）で本物移植**に決定 |
| D-2 | ~~LUFS の表示/適用~~ | **解決済（2026-10-12）**: 利用者指示により **LUFS は廃止** |
| D-3 | AutoEq オンライン検索の配置 | 推奨: hq_api（サーバー側）。キャッシュ・レート制御・オフライン耐性 |
| D-4 | oratory/crinacle 全カタログ（2.7 万行）の同梱 | 推奨: 同梱しない。内蔵 8 + オンライン検索で必要なものだけ取り込む |
| D-5 | FIR 全帯域モード（§3-A-2）の採用 | 推奨: Phase 1 完了後に追加 Step として導入（PEQ と併存選択式・min-phase） |
| D-6 | 音量の位置（tube 前段=プリアンプ型 / tube 後段） | 推奨: tube 前段を維持（実機アンプと同じ挙動。Bisen との意図的差分として記録） |
| D-7 | ffmpeg 導入（ファイル真理用） | 推奨: 導入する（`sudo apt install ffmpeg`）。任意依存のため未導入でも他機能に影響なし |
| D-8 | bisen-dspd 制御 API の方式 | 推奨: Unix domain socket（localhost 専用・外部露出なし）。詳細 I/F は Phase 3-3 で確定 |

## 7. テスト方針

- **単体テスト**（既存パターン踏襲: `backend/venv/bin/python3 -m unittest tests.unit.<name> -v`）:
  - `test_autoeq.py` — ParametricEQ.txt パーサ（正常/異常/エッジケース）
  - `test_dsp_headphone.py` — headphone_profile×intensity の YAML 生成（フィルタ名・順序・preamp・ヘッドルーム）
  - `test_dsp_tube_restore.py` — Compressor/Limiter パラメータマッピング
  - `test_info_credits.py` — MusicBrainz ルータ（fixture、レート制限モック）
- **YAML 検証**: 生成物を `camilladsp -c` に通す結合チェック（`test_camilladsp_yaml_schema.py` 拡張）
- **スナップショット**: `test_dsp_yaml_snapshot.py` に代表パターン（キャリブ無効/有効、Tube 3 種、Restore）を追加
- **実機確認**: 各 Phase 完了時に MPD 実再生 → アンダーラン 0 であることを確認（Root Fix B の検証方法を踏襲）
- **Phase 3（bisen-dspd）向け追加**:
  - `tests/unit/test_bisen_dspd_math.py` — Python 参照実装との数値一致（tanh カーブ・Sag 包絡・√f レート変換の検算）
  - `dmp/bisen-dspd/tests/`（C++ 側）— ゴールデンサンプル（固定入力 WAV → 出力比較）+ tube/restore off の passthrough lossless 試験
  - soak 試験 — 30 分連続再生で xrun 0 / メモリ RSS 横ばい
  - フォールバック試験 — bisen-dspd 停止 → `switch_audio.sh` が直結構成へ自動復帰すること

## 8. 調査メモ（出典）

- Bisen 側: `src/dsp/AudioEngine.ts`（tube_v4 payload L565-571, calibScale, LUFS L152-166）,
  `src/dsp/presets.ts`, `src/dsp/headphoneProfiles.ts`, `src/dsp/totalCurve.ts`,
  `src/dsp/onlineAutoEq.ts`, `android/.../dsp/TubeModel.cpp`, `android/.../dsp/RestorationEngine.cpp`,
  `docs/PLAYBACK_GAPLESS_WALKTHROUGH_V5.md`
- HQ 側: `backend/dsp/models.py`, `backend/dsp/profiles.py`, `backend/dsp/yaml_generator.py`（584 行）,
  `backend/dsp/analysis.py`, `hq_api/routers/dsp*.py`, `hqmplayer_core/meta/formatting.py:89`（audio フィールド既存）,
  `docs/schemas/dsp_profile.schema.json`
- CamillaDSP 表現力の検証（WaveShaper 不可）: 2026-10-12 実機 camilladsp 4.1.3 `-c` による直接検証
- rev.2 追加調査（2026-10-12 実測）:
  - `/etc/mpd.conf`: ALSA 出力 `hw:Loopback,0,0` 固定 `192000:32:2`
  - `/var/lib/camilladsp/active_dsp.yml`: capture `hw:Loopback,1,0` / playback `plughw:1,0`、192kHz S32_LE、chunksize 4096
  - `/sys/module/snd_aloop/parameters/pcm_substreams` = 8（sub1〜sub7 が空き → 第 2 ホップに sub1 使用可）
  - `NativeAudioEngine.cpp` L227-252: チェーン順 = hum → EQ → restoration → tube → spatial（→ compressor → limiter → phase 最終段）
  - Bisen 1 極定数は 96kHz 前提ハードコード（TubeModel 0.9992/0.9998/0.9995、RestorationEngine 0.9996）→ 192kHz では √f 変換が必要
  - `TruePeakLimiter`: 4x オーバーサンプリング true-peak、attack/release はレート対応済み
  - venv: numpy 2.5.3 / scipy 1.18.1 / requests 2.33.1 を確認。ffmpeg CLI は未導入（lib のみ）

---

## 9. 進捗・HANDOVER（2026-10-12 実装完了分 — 新セッションはここから継続）

### 9-1. 実装完了済み（Phase 1 + Phase 2 完了、実機検証済み）

#### Phase 1: ホンキャリブレーション ✅ 完了

| Step | 内容 | 成果物 | 状態 |
|---|---|---|---|
| 1-1 | AudioConfig/DspParams に `headphone_profile`/`headphone_intensity` 追加 | `backend/dsp/models.py` | ✅ |
| 1-2 | YAML 生成に preamp + Biquad 列注入（Output EQ 直後 = Bisen チェーン順） | `backend/dsp/yaml_generator.py` | ✅ |
| 1-3 | Bisen 内蔵 7 プロファイルを JSON 変換 + インストーラ | `config/profiles/*.json`, `backend/dsp/profiles.py` | ✅ |
| 1-3b | **2,810 機種カタログ同梠**（D-4 改訂・利用者指示） | `config/profiles/catalog.json` (2.81MB) + `scripts/convert_bisen_catalog.py` | ✅ |
| 1-4 | AutoEq ParametricEQ.txt パーサ（PK/LSC/HSC 種別解析含む改善版） | `backend/dsp/autoeq.py` | ✅ |
| 1-5 | カタログ検索・取込み API | `GET /api/dsp/headphones/catalog`, `POST .../import` | ✅ |
| 1-6 | **HP CALIBRATION Popup**（モバイル＝ボトムシート / PC＝横長 2 カラム） | `HeadphoneCalibrationModal.tsx` | ✅ |
| 1-6b | **リキャリブレーション**（Bisen targetCurveId 相当） | `backend/dsp/headphone.py` (resolve_target_profile + compute_effective_profile) | ✅ |
| 1-6c | GUI ターゲットセレクタ（HARMAN/FLAT/BYPASS + →TGT）+ 黒/シルバーパネル二列表示 | `page.tsx`, `HeadphoneCalibrationModal.tsx` | ✅ |

**リキャリブレーション設計（backend/dsp/headphone.py）**:
- `headphone_target` フィールド: `"harman"`(既定=リスニング補正のみ) / `"flat"` / `"bypass"`(素の音) / 機種プロファイルID
- 機種指定時の合成: **バンド連結** `C_L + negate(C_T)` — Bisen 簡易差分 (`target−listening` 周波数マッチ) は「デフォルト Harman 近似」が数学的に達成されないため、意図された機能を正確に実現する方式に変更
- 同一機種指定 = 補正なし (Bisen 仕様: `listening.id === target.id`)
- ターゲット解決: インストール済み → 同梱カタログ の順
- プロファイル総数: 10 (7 内蔵 + 3 ユーザー) + カタログ 2,810 機種

#### Phase 2: Info 機能 ✅ 完了

| Step | 内容 | 成果物 | 状態 |
|---|---|---|---|
| 2-1 | 信号真理: PC メタバー + シルバーパネル FORMAT/DEPTH/RATE + モバイル バッジ → 実値表示 | `page.tsx`, `ws/status.py` (audio フィールド) | ✅ |
| 2-2 | **VU メータ**: CamillaDSP 実レベル (playback peak/rms) 10Hz 中継 | `hq_api/ws/levels.py` (新規 WS), `useLevels.ts` | ✅ |
| 2-3 | **LISTENING WIKI**: MusicBrainz + Discogs + Wikipedia 3 ソース統合 | `hq_api/routers/info.py` (~840 行), `InfoPanel.tsx` | ✅ |
| 2-4 | ファイル真理 (ffprobe): ffmpeg CLI 未導入のため**先送り**（任意依存） | — | ⏸️ |

**LISTENING WIKI 実装詳細（Bisen V6.1 完全移植）**:
- **3 ソース + ランク統合**: MB(rank 3) > Discogs(rank 2) > MB Release(rank 1) > Wikipedia(rank 0)
- MusicBrainz: 3 段階検索クエリ → 録音詳細 (`inc=artist-rels+work-rels+work-level-rels+place-rels+releases` — **旧実装の 400 エラーは inc 名の誤り `"artist-relations"` が原因、`"artist-rels"` に修正**) → リリース詳細 → 長さ信頼性判定 (±10% or 15s)
- Discogs: MB url-rels 権威リンク → master 優先 direct lookup、無ければ fuzzy 検索 (scoreMatch: artist 40/30 + title 40/25 + album 20 + master 10 + year 5、閾値 50)
- Wikipedia: 記事検索(en→ja) → wikitext infobox 採掘 (producer/studio/recorded/engineer/label/genre) → 冒頭要約 420 字 → アーティスト bio (非音楽家拒否・音楽家性検証 ≥2 語)
- GUI: **Bisen WikiModal 完全移植** — 3 タブ (People 14 行 / Album 11 行 + Album Notes / Signal 3 行)、"Not catalogued" italic、行タップで Google 検索
- キャッシュ: `~/.cache/audiophile/musicbrainz/` 永続 (30 日)、初回はレート制限 1.1s × 5-10 リクエスト (MB 規約準拠)、2 回目以降即応答 (実測 0.02s)

**VU メータ**: CamillaDSP `GetPlaybackSignalPeak/Rms` を 10Hz で中継。dB → 0..1 は `(db+60)/60`。pure モードは従来の音量連動アニメにフォールバック。

**Signal タブ `Native Resolution` 修正済み**: `srcRate` は **Hz (44100)** で渡す（Bisen 仕様。kHz で渡すと二重割り算で `0.1kHz` 表示になる）。

### 9-2. Total EQ Curve（アルバムアート タップ）✅ 完了（2026-10-13、実機確認済み）

Bisen `AlbumArtFrame.tsx` Total Mode + `totalCurve.ts` の移植。

| 項目 | 内容 |
|---|---|
| 成果物 | `new-gui/src/components/TotalCurveOverlay.tsx`（新規）+ `page.tsx` 統合 |
| 合成対象 | SRC EQ + OUT EQ + X-FEED + HUM + HP補正（リスニング + negate(ターゲット)）× 強度 |
| カーブ精度 | **240点サンプリング**（42→240）、周波数対数軸 **20Hz/100/1k/10k/20kHz** ラベル + マイナー目盛り 11 本 |
| 線幅 | メイン 0.85 / グロー 2.2 (22%) — SVG 128x90 直描画 |
| 警告 | ±3dB 超過で `⚠ TOTAL x.x dB EXCEEDS SAFE RANGE`（Bisen と同一） |
| 表示 | トップバーに `PEAK ±x.xdB · 240pt`、下段にアクティブエフェクト一覧（SRC EQ / TUBE / OUT EQ / HEADPHONE [→TGT] / X-FEED / CTC / AMB / HUM） |
| 操作 | PC・モバイル両方のアルバムアートをタップ → カーブ⇔アート切替 |
| GUI_REV | R10 |

### 9-3. 実機環境の状態（2026-10-13 時点）

| 項目 | 状態 |
|---|---|
| ブランチ | `feature/bisen-phase1-hp-calibration`（ベース: `V3/1_Inspected`） |
| hq-api (8002) | ✅ 稼働中（systemd `hq-api.service`）— カタログ・リキャリブ・LISTENING WIKI 含む |
| GUI (3003) | ✅ 稼働中（systemd `audiophile-new-gui.service`）— R10 ビルド |
| CamillaDSP (1234) | ✅ 稼働中 — **音声経路は本 Phase で一度も未接触** |
| テスト | ✅ **203/203 全パス**（`backend/venv/bin/python3 -m unittest discover -s tests/unit`） |
| Node.js | `/home/tysbox/.local/nodejs/node/bin`（PATH に追加して `npm run build`） |
| プロファイル | `~/.config/audiophile/profiles/` 10 件 + `config/profiles/catalog.json` 2,810 機種 |
| MBキャッシュ | `~/.cache/audiophile/musicbrainz/`（LISTENING WIKI 永続キャッシュ） |
| sudo | `systemctl restart` 等に必要（ターミナルでパスワード入力） |

### 9-4. コミット一覧（本ブランチ）

```
5ba1efba docs: Bisen機能移植計画 (rev.2)
192129ec feat(dsp): ホンキャリブレーション基盤 (Stage 8)
dd806d7d feat(profiles): Bisen 内蔵ヘッドホンプロファイル 7 機種を同梠 (Step 1-3)
269d022b feat(autoeq): AutoEq ParametricEQ.txt パーサ (Step 1-4)
cb555dca feat(catalog): Bisen 計測カタログ 2,810 機種を同梠 (Step 1-3b)
61a2fb78 feat(gui): ホンキャリブレーション Popup (Step 1-6)
0b2b7d42 feat(recal): リキャリブレーション (Step 1-6c)
（次コミット対象）feat(info): Phase 2 LISTENING WIKI 3ソース統合 + VU実レベル + 信号真理 + Total EQ Curve
```

### 9-5. クイックスタート（新セッション向け）

```bash
cd /home/tysbox/HQ_Linux_Music_Player
git branch --show-current              # feature/bisen-phase1-hp-calibration
./backend/venv/bin/python3 -m unittest discover -s tests/unit  # 203/203
curl -s http://localhost:8002/health   # {"status":"ok",...}
# GUI R10: http://<IP>:3003（強リロード Ctrl+Shift+R）
#   - アルバムアート タップ → TOTAL EQ CURVE（周波数軸+240pt）
#   - ℹボタン → LISTENING WIKI（People/Album/Signal 3タブ）
#   - 🎧 HP CAL → キャリブレーション Popup（→TGT でリキャリブレーション）
# 再ビルド: cd new-gui && PATH=/home/tysbox/.local/nodejs/node/bin:$PATH npm run build
# 反映: sudo systemctl restart audiophile-new-gui.service hq-api.service
```

### 9-6. テスト実行方法

```bash
# 全件 (203 件)
./backend/venv/bin/python3 -m unittest discover -s tests/unit

# 個別
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_headphone    # キャリブ+リキャリブ (19 件)
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_catalog     # カタログ (12 件)
./backend/venv/bin/python3 -m unittest tests.unit.test_autoeq          # AutoEq パーサ (13 件)
./backend/venv/bin/python3 -m unittest tests.unit.test_phase2_info     # LISTENING WIKI+VU+信号真理 (19 件)
./backend/venv/bin/python3 -m unittest tests.unit.test_profiles        # プロファイル検証
```

### 9-7. 次の Phase（未着手）

| Phase | 内容 |
|---|---|
| **Phase 3 残** | Step 3-5 (switch_audio.sh 経路切替拡張) / 3-6 (models.py・hq_api 仲介) / 3-7 (GUI Tube トグル+球種+bias、Restore 3モード) / 3-8 (実機 A/B・30分 soak・レイテンシ実測) |
| **Phase 4** | Info × デーモン連携（VU true-peak 切替 + デーモン状態表示） |
| **追加 Step** | FIR 全帯域モード（§3-A-2、決定 D-5）／ ffprobe ファイル真理（決定 D-7、`apt install ffmpeg` 必要） |

### 9-8. Phase 3 進捗（2026-10-13 — Step 3-1〜3-4 実装完了・未コミット→コミット済み）

| Step | 内容 | 成果物 | 状態 |
|---|---|---|---|
| 3-1 | CMake + ALSA capture/playback スケルトン、S32_LE↔float32 変換 | `dmp/bisen-dspd/src/{main,alsa_io}.{cpp,h}`, `CMakeLists.txt` | ✅ |
| 3-2 | DSP 本体移植（4 ファイル）+ √f 時定数保存変換のパラメータ化 | `src/dsp/{TubeModel,RestorationEngine,TruePeakLimiter}.{h,cpp}` | ✅ 20/20 テスト |
| 3-3 | 制御 API（Unix socket、std::atomic、routing/bypass/tube/restore_mode） | `src/{control,params}.{h,cpp}` | ✅ 実機スモークテスト済み |
| 3-4 | systemd `bisen-dspd.service.template` (notify / Watchdog / SCHED_FIFO 50 / RuntimeDirectory) | `config/systemd/bisen-dspd.service.template` + インストーラ対応 | ✅ verify OK |

**実装上の重要設計（既存システム完全保護）**:

- **routing 制御方式**: デーモンは常駐だが `routing=0` (既定) の間は **ALSA デバイスを一切開かない**
  （standby）。CamillaDSP 直結構成と DAC 競合しないため既存音声経路への影響ゼロ。
  切替順序: `set routing 1` → デーモンが capture+DAC 確保 (`playback_open=1` 確認待ち) →
  CamillaDSP YAML を `hw:Loopback,0,1` 出力へホットリロード。復帰は逆順。
  （常時 DAC 保持だと CamillaDSP が起動できなくなるためこの方式が必須）
- **バイパス = bitwise passthrough**: tube off + restore off 時は S32→float→S32 往復変換を
  行わない（float32 は 24bit しか精度保持できないため）→ 入力と出力がビット等価
  （受け入れ条件「bitwise passthrough」を構造的に達成）。
- **TruePeakLimiter は dspActive 時のみ呼ぶ**（常時だと 1ms lookahead 遅延が乗る）。
- **absolute_phase は CamillaDSP 担当のまま**（デーモンでは再実装しない → 二重反転防止）。
- **レート適応**: 係数は `a = exp(-1/(rate·tau))` 形式で一般化（tau は Bisen 96kHz 実装値から逆算）。
  96kHz で Bisen 原値 (0.9992/0.9998/0.9995/0.9996)、192kHz で §3-B 変換値
  (0.99960/0.99990/0.99975/0.99980) — テスト `testCoefficientParity` が両方を検証。
- **Restore は 3 モード固定切替**（§3-C の 2026-10-13 利用者指示参照。強度スライダ廃止）。

**検証済み (2026-10-13)**:

```
ビルド      : cmake 3.31.6 / g++ — 0 error 0 warning
DSP テスト  : ./build/test_dsp_chain → 20/20 (係数パリティ 96k/192k・偶数次高調波・
              3 モード過渡順序・超音波倍音・リミッタ 1.5x クランプ・無効時 no-op)
スモーク    : 実機で standby 起動 → ping/get/set 12 コマンド動作 → SIGTERM グレースフル停止
              (standby 中 /proc/asound の sub1 = closed のまま・DAC 所有権も無変化を確認)
systemd     : install_systemd_units.sh --stage → 3 unit 全て systemd-analyze verify OK
依存追加    : libasound2-dev 1.2.14 / cmake 3.31.6 (apt 導入済み)
```

**残作業（Step 3-5〜3-8、音声経路に触れるため実機検証を要す）**:
- 3-5: `switch_audio.sh` にデーモン経路分岐追加（routing オーケストレーション）
- 3-6: `backend/dsp/models.py` に `tube`/`restore` フィールド追加 + hq_api が制御 socket を仲介
- 3-7: GUI（Tube トグル+球種 300B/KT88+bias ダイヤル / Restore トグル+3モード セレクタ）
- 3-8: 実機 A/B 聴感確認・30 分 soak・レイテンシ実測後、承認を得てコミット





