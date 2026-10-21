# bisen-dspd — Bisen DSP daemon (Tube / Restore / TruePeakLimiter 完全移植)

Bisen-DSP-System の Android C++ DSP (`android/app/src/main/cpp/dsp/`) を
Linux ALSA デーモンとして移植したもの。計画書 `docs/BISEN_FEATURE_PORT_PLAN.md` §3-B 方式2。

## 信号チェーン (Bisen NativeAudioEngine 忠実)

```
[MPD → hw:Loopback,0,0] → CamillaDSP (EQ/IR/crossfeed/HPキャリブ)
   → hw:Loopback,0,1 → [capture hw:Loopback,1,1] bisen-dspd
   RestorationEngine → TubeModel → TruePeakLimiter
   → plughw:1,0 (DAC)
```

hum / EQ / spatial は CamillaDSP 担当のため本デーモンは持たない (二重処理なし)。

## ゼロ影響設計 (既存システム保護)

- **standby が既定**: `routing=0` の間 ALSA デバイスを一切開かない → CamillaDSP
  直結構成 (現行) に完全に無影響。
- 切替は hq_api / switch_audio.sh がオーケストレーションする:
  1. `set routing 1` → デーモンが capture + DAC を確保 (`playback_open=1` を確認)
  2. CamillaDSP の YAML を `hw:Loopback,0,1` 出力へホットリロード
  3. 戻すときは逆順 (CDSP → 直結 YAML → `set routing 0`)

## Restore 3 モード (2026-10-13 利用者指示 — 3 モード固定切替)

| モード | 対象ソース | punch | harmonicGain | HF強調 | 目的 |
|---|---|---|---|---|---|
| `lossy_standard` | Lossy (MP3) 192-320kbps | 0.65 | 0.08 | — | 擬似ロスレス (Bisen デフォルト) |
| `lossy_high` | Lossy (MP3) 低ビットレート | 0.85 | 0.13 | 0.25 | 補完度を高くした擬似ロスレス (16kHz 帯域欠損重点補完) |
| `cd` | Lossless (CD) | 0.30 | 0.06 | 0.50 | 疑似ハイレゾ (10-20kHz 倍音 → 20kHz 超の倍音生成) |

## ビルドとテスト

```bash
cd dmp/bisen-dspd
cmake -B build && cmake --build build -j4
./build/test_dsp_chain   # 20 項目: 係数パリティ (96k=Bisen/192k=§3-B)・高調波・モード別動作
ctest --test-dir build --output-on-failure
```

## 制御 (Unix domain socket — ラインプロトコル)

```
set routing 0|1                       # ALSA 経路 確保/解放
set bypass 0|1                        # true = bitwise passthrough (S32 往復なし)
set tube_enabled 0|1
set tube_type TRIODE|PENTODE          # 300B / KT88
set tube_bias <0..100>                # GUI 値 (内部で Bisen 仕様 0..1 に正規化)
set restore_enabled 0|1
set restore_mode lossy_standard|lossy_high|cd
get params / get peaks / ping
```

例: `echo 'set tube_type KT88' | nc -U /run/bisen-dspd/control.sock`
(Python の場合は `socket.AF_UNIX, SOCK_STREAM`)

## 実行

```bash
# 直接起動 (デバッグ)
./build/bisen-dspd --socket /tmp/bisen-dspd.sock
# systemd (本番)
sudo systemctl enable --now bisen-dspd.service
journalctl -u bisen-dspd -f
```

## パラメータ / 経路の意味論 (決定事項)

- **バイパスは bitwise**: tube off + restore off のとき S32 → float → S32 の往復変換を
  行わないため入力と出力はビット等価 (Phase 3 受け入れ条件)。
- **音量の意味論** (決定 D-6): CamillaDSP 音量 = tube 前段 = プリアンプ →
  パワーアンプ型。音量でドライブ感が変わる実機アンプと同じ挙動。
- **レート適応**: Bisen の 96kHz 前提ハードコード係数は時定数保存
  (`a = exp(-1/(rate·tau))`) に一般化。96kHz で Bisen と完全一致、192kHz で
  計画書 §3-B の √f 変換値 (0.99960/0.99990/0.99975/0.99980) に一致
  (テスト `testCoefficientParity` で検証)。
