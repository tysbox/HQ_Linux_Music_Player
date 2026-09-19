#!/usr/bin/env python3
"""合成 IR 生成ツール（Stage 5: 空間演出）

numpy でインパルス応答を合成し、scipy で float32 WAV 出力。
サイドカー JSON で生成条件・RT60 等を記録。

実行例:
  ./backend/venv/bin/python3 scripts/make_ir.py studio
  ./backend/venv/bin/python3 scripts/make_ir.py hall --rt60 1.8 --room 8x6x3
  ./backend/venv/bin/python3 scripts/make_ir.py --list
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve


# ─────────────────────────────────────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 192000
IR_DIR = Path(os.path.expanduser("~/.config/camilladsp/ir"))
IR_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# 合成パラメータプリセット
# ─────────────────────────────────────────────────────────────────────────────
PRESETS = {
    "studio": {
        "name": "Studio (Control Room)",
        "rt60": 0.4,
        "room_size": (5, 4, 2.5),
        "early_reflections": [
            (0.002, 0.8), (0.004, 0.6), (0.006, 0.45), (0.009, 0.3),
            (0.012, 0.2), (0.015, 0.15), (0.018, 0.1), (0.022, 0.07),
        ],
        "late_reverb_density": 0.7,
        "description": "小規模コントロールルーム風。タイトで明確な定位。",
    },
    "hall": {
        "name": "Concert Hall",
        "rt60": 1.8,
        "room_size": (30, 20, 15),
        "early_reflections": [
            (0.020, 0.7), (0.035, 0.55), (0.050, 0.4), (0.070, 0.3),
            (0.090, 0.22), (0.110, 0.16), (0.140, 0.11), (0.180, 0.07),
        ],
        "late_reverb_density": 0.9,
        "description": "中規模コンサートホール風。豊かな残響感。",
    },
    "large_hall": {
        "name": "Large Concert Hall",
        "rt60": 2.5,
        "room_size": (50, 35, 20),
        "early_reflections": [
            (0.035, 0.65), (0.055, 0.5), (0.080, 0.38), (0.110, 0.28),
            (0.140, 0.2), (0.180, 0.14), (0.220, 0.1), (0.280, 0.06),
        ],
        "late_reverb_density": 0.95,
        "description": "大規模ホール風。深い包囲感と長い残響。",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 合成ユーティリティ
# ─────────────────────────────────────────────────────────────────────────────
def generate_noise_burst(duration_sec: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """ホワイトノイズバースト生成（インパルス応答測定用）"""
    n = int(duration_sec * sample_rate)
    return np.random.randn(n).astype(np.float32)


def exponential_decay(rt60: float, duration_sec: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """指数減衰エンベロープ生成 (RT60ベース)"""
    n = int(duration_sec * sample_rate)
    t = np.arange(n) / sample_rate
    # RT60: エネルギーが -60dB (振幅 -30dB = 1/1000) になる時間
    # A(t) = exp(-6.91 * t / RT60)
    decay = np.exp(-6.91 * t / rt60)
    return decay.astype(np.float32)


def allpass_filter(input_signal: np.ndarray, delay_samples: int, gain: float) -> np.ndarray:
    """オールパスフィルタ（残響密度増加用）"""
    output = np.zeros_like(input_signal)
    for i in range(len(input_signal)):
        delayed = input_signal[i - delay_samples] if i >= delay_samples else 0.0
        output[i] = gain * input_signal[i] + delayed - gain * output[i - delay_samples] if i >= delay_samples else input_signal[i]
    return output.astype(np.float32)


def comb_filter(input_signal: np.ndarray, delay_samples: int, gain: float) -> np.ndarray:
    """コムフィルタ（残響成分生成用）"""
    output = np.zeros_like(input_signal)
    for i in range(len(input_signal)):
        delayed = input_signal[i - delay_samples] if i >= delay_samples else 0.0
        output[i] = input_signal[i] + gain * output[i - delay_samples] if i >= delay_samples else input_signal[i]
    return output.astype(np.float32)


def generate_synthetic_ir(preset: dict, duration_sec: float = 2.0, distance: str = "mid") -> tuple[np.ndarray, dict]:
    """合成 IR 生成（ステレオ 2ch）
    
    Args:
        preset: プリセット辞書
        duration_sec: IR 長 [秒]
        distance: "near" / "mid" / "far" - 直接音/初期反射比の調整
    
    Returns:
        (ir_stereo: (N, 2) float32, metadata: dict)
    """
    n = int(duration_sec * SAMPLE_RATE)
    ir_l = np.zeros(n, dtype=np.float32)
    ir_r = np.zeros(n, dtype=np.float32)
    
    # 直接音（時間 0 にインパルス）
    ir_l[0] = 1.0
    ir_r[0] = 1.0
    
    # 距離による直接音ゲイン調整
    distance_gains = {"near": 0.0, "mid": -3.0, "far": -6.0}
    direct_gain_db = distance_gains.get(distance, -3.0)
    direct_gain = 10 ** (direct_gain_db / 20.0)
    ir_l[0] *= direct_gain
    ir_r[0] *= direct_gain
    
    # 初期反射音
    early_reflections = preset.get("early_reflections", [])
    for delay_sec, gain in early_reflections:
        delay_samples = int(delay_sec * SAMPLE_RATE)
        if delay_samples >= n:
            continue
        # ステレオ広がり: L と R で微小な遅延差
        lr_diff = int(0.0001 * SAMPLE_RATE)  # ~0.1ms
        ir_l[delay_samples] += gain * 0.5
        ir_r[delay_samples + lr_diff] += gain * 0.5
        ir_l[delay_samples + lr_diff] += gain * 0.3  # 反対側への漏れ
        ir_r[delay_samples] += gain * 0.3
    
    # 後期残響（指数減衰 + コム/オールパスフィルタで密度稼ぎ）
    rt60 = preset.get("rt60", 1.5)
    density = preset.get("late_reverb_density", 0.8)
    
    # 減衰エンベロープ
    decay = exponential_decay(rt60, duration_sec, SAMPLE_RATE)
    
    # ノイズバーストを生成して残響成分を作る
    noise = generate_noise_burst(duration_sec, SAMPLE_RATE)
    reverb = noise * decay
    
    # コムフィルタで共鳴感を出す（複数段）
    comb_delays = [int(SAMPLE_RATE * d) for d in [0.031, 0.037, 0.041, 0.043, 0.047, 0.053]]
    for delay in comb_delays:
        reverb = comb_filter(reverb, delay, 0.3 * density)
    
    # オールパスで位相拡散
    ap_delays = [int(SAMPLE_RATE * d) for d in [0.005, 0.012, 0.017]]
    for delay in ap_delays:
        reverb = allpass_filter(reverb, delay, 0.7)
    
    reverb *= 0.1  # スケーリング
    
    # L/R に少し異なる残響を適用（ステレオ広がり）
    reverb_r = reverb.copy()
    reverb = np.roll(reverb, 10)  # 微小遅延
    
    # 加算合成
    ir_l += reverb * 0.5
    ir_r += reverb_r * 0.5
    
    # ピーク正規化（-6dBFS 以下）
    peak = max(np.max(np.abs(ir_l)), np.max(np.abs(ir_r)))
    if peak > 0:
        target_peak = 0.5  # -6dBFS
        scale = target_peak / peak
        ir_l *= scale
        ir_r *= scale
    
    ir_stereo = np.column_stack((ir_l, ir_r)).astype(np.float32)
    
    # RT60 推定（シュレーダー法 T30）
    rt60_est = estimate_rt60(ir_stereo, SAMPLE_RATE)
    
    metadata = {
        "synthesized": True,
        "preset": preset.get("name", "unknown"),
        "rt60_target": preset.get("rt60"),
        "rt60_estimated": rt60_est,
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "duration_sec": duration_sec,
        "distance": distance,
        "peak_dbfs": float(20 * np.log10(np.max(np.abs(ir_stereo)) + 1e-12)),
        "rms_dbfs": float(20 * np.log10(np.sqrt(np.mean(ir_stereo**2)) + 1e-12)),
    }
    
    return ir_stereo, metadata


def estimate_rt60(ir_stereo: np.ndarray, sample_rate: int) -> float:
    """シュレーダー法 T30 で RT60 推定"""
    # モノラル化
    ir = np.mean(ir_stereo, axis=1)
    
    # シュレーダー積分（逆時間積分）
    energy = np.cumsum(ir[::-1] ** 2)[::-1]
    energy_db = 10 * np.log10(energy / (energy[0] + 1e-12) + 1e-12)
    
    # -5dB から -35dB の範囲で線形フィット（T30）
    idx_start = np.where(energy_db <= -5)[0]
    idx_end = np.where(energy_db <= -35)[0]
    if len(idx_start) == 0 or len(idx_end) == 0:
        return 0.0
    start = idx_start[0]
    end = idx_end[0]
    if end <= start:
        return 0.0
    
    t = np.arange(start, end) / sample_rate
    coeffs = np.polyfit(t, energy_db[start:end], 1)
    slope = coeffs[0]  # dB/sec
    if slope >= 0:
        return 0.0
    
    # T60 = -60 / slope
    rt60 = -60.0 / slope
    return float(rt60)


def save_ir_and_metadata(ir: np.ndarray, metadata: dict, preset_id: str):
    """IR WAV とメタデータ JSON を保存"""
    IR_DIR.mkdir(parents=True, exist_ok=True)
    
    wav_path = IR_DIR / f"{preset_id}.wav"
    json_path = IR_DIR / f"{preset_id}.json"
    
    # float32 WAV 保存
    wavfile.write(wav_path, SAMPLE_RATE, ir)
    
    # メタデータ JSON 保存
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"Saved: {wav_path}")
    print(f"Saved: {json_path}")
    print(f"  RT60 target: {metadata.get('rt60_target')}s, estimated: {metadata.get('rt60_estimated'):.3f}s")
    print(f"  Peak: {metadata.get('peak_dbfs'):.2f} dBFS, RMS: {metadata.get('rms_dbfs'):.2f} dBFS")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="合成 IR 生成ツール")
    parser.add_argument("preset", nargs="?", choices=list(PRESETS.keys()) + ["all"], 
                        help="プリセット名 (studio/hall/large_hall/all)")
    parser.add_argument("--list", action="store_true", help="プリセット一覧表示")
    parser.add_argument("--rt60", type=float, help="RT60 上書き [秒]")
    parser.add_argument("--duration", type=float, default=2.0, help="IR 長 [秒]")
    parser.add_argument("--distance", choices=["near", "mid", "far"], default="mid", 
                        help="距離感（直接音ゲイン調整）")
    parser.add_argument("--check", action="store_true", help="既存 IR の検証のみ")
    
    args = parser.parse_args()
    
    if args.list:
        for pid, p in PRESETS.items():
            print(f"  {pid}: {p['name']} (RT60={p['rt60']}s) - {p['description']}")
        return
    
    if args.check:
        # 既存 IR の検証
        for wav_file in sorted(IR_DIR.glob("*.wav")):
            pid = wav_file.stem
            json_file = IR_DIR / f"{pid}.json"
            try:
                sr, ir = wavfile.read(wav_file)
                if ir.ndim == 2:
                    ir = ir.astype(np.float32) / 32768.0 if ir.dtype == np.int16 else ir.astype(np.float32)
                else:
                    ir = ir.astype(np.float32) / 32768.0 if ir.dtype == np.int16 else ir.astype(np.float32)
                    ir = np.column_stack((ir, ir))
                
                rt60_est = estimate_rt60(ir, sr)
                peak = np.max(np.abs(ir))
                rms = np.sqrt(np.mean(ir**2))
                
                meta = {}
                if json_file.exists():
                    with open(json_file) as f:
                        meta = json.load(f)
                
                print(f"{pid}: sr={sr}, ch={ir.shape[1] if ir.ndim==2 else 1}, "
                      f"len={len(ir)/sr:.2f}s, peak={20*np.log10(peak+1e-12):.1f}dBFS, "
                      f"RMS={20*np.log10(rms+1e-12):.1f}dBFS, RT60={rt60_est:.3f}s")
                if meta:
                    print(f"  target RT60: {meta.get('rt60_target')}, "
                          f"synthesized: {meta.get('synthesized')}")
            except Exception as e:
                print(f"{pid}: ERROR - {e}")
        return
    
    if not args.preset:
        parser.print_help()
        return
    
    presets_to_gen = list(PRESETS.keys()) if args.preset == "all" else [args.preset]
    
    for pid in presets_to_gen:
        if pid not in PRESETS:
            print(f"Unknown preset: {pid}")
            continue
        
        preset = PRESETS[pid].copy()
        if args.rt60:
            preset["rt60"] = args.rt60
        
        ir, meta = generate_synthetic_ir(preset, duration_sec=args.duration, distance=args.distance)
        save_ir_and_metadata(ir, meta, pid)


if __name__ == "__main__":
    main()
