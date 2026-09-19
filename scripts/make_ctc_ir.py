#!/usr/bin/env python3
"""CTC (Crosstalk Cancellation) IR 生成ツール（Stage 7: CTC）

逆フィルタ設計によりクロストーク打ち消し用 IR を生成。
正則化付き最小二乗法で安定化。

実行例:
  ./backend/venv/bin/python3 scripts/make_ctc_ir.py --method lsq --regularization 1e-4
  ./backend/venv/bin/python3 scripts/make_ctc_ir.py --method minphase --check
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve, freqz, minimum_phase


# ─────────────────────────────────────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 192000
IR_DIR = Path(os.path.expanduser("~/.config/camilladsp/ir"))
IR_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# CTC IR 設計
# ─────────────────────────────────────────────────────────────────────────────
def design_ctc_inverse_filter(lr_ir: np.ndarray, rl_ir: np.ndarray,
                              method: str = "lsq",
                              regularization: float = 1e-4,
                              max_delay_samples: int = None) -> tuple[np.ndarray, np.ndarray]:
    """
    クロストーク打ち消し用の逆フィルタ (L→R, R→L) を設計。
    
    Args:
        lr_ir: L→R 方向のクロストーク応答 (ステレオIRの ch1→ch0 成分等)
        rl_ir: R→L 方向のクロストーク応答
        method: "lsq" (正則化最小二乗) または "minphase" (最小位相逆フィルタ)
        regularization: 正則化パラメータ (lsq のみ)
        max_delay_samples: 最大遅延サンプル数 (遅延補正用)
    
    Returns:
        (inv_lr, inv_rl): 逆フィルタ係数 (LR方向打ち消し用, RL方向打ち消し用)
    """
    # 入力を float32 に正規化
    if lr_ir.dtype != np.float32:
        lr_ir = lr_ir.astype(np.float32) / (32768.0 if lr_ir.dtype == np.int16 else 1.0)
    if rl_ir.dtype != np.float32:
        rl_ir = rl_ir.astype(np.float32) / (32768.0 if rl_ir.dtype == np.int16 else 1.0)
    
    # ステレオの場合はモノラル化 (平均)
    if lr_ir.ndim == 2:
        lr_ir = np.mean(lr_ir, axis=1)
    if rl_ir.ndim == 2:
        rl_ir = np.mean(rl_ir, axis=1)
    
    # 長さを揃える
    n = min(len(lr_ir), len(rl_ir))
    lr_ir = lr_ir[:n]
    rl_ir = rl_ir[:n]
    
    if method == "lsq":
        return _design_inverse_lsq(lr_ir, rl_ir, regularization)
    elif method == "minphase":
        return _design_inverse_minphase(lr_ir, rl_ir)
    else:
        raise ValueError(f"Unknown method: {method}")


def _design_inverse_lsq(lr_ir: np.ndarray, rl_ir: np.ndarray,
                        regularization: float = 1e-4) -> tuple[np.ndarray, np.ndarray]:
    """正則化最小二乗法で逆フィルタ設計。"""
    n = len(lr_ir)
    # ターゲットはディラックデルタ (インパルス応答の逆)
    target = np.zeros(n, dtype=np.float32)
    target[0] = 1.0
    
    # 循環畳み込み行列を構築 (FFTベースで効率化)
    # ここでは簡易的に toeplitz 行列を使用 (n が小さい場合)
    # 実用的には FFT-based overlap-save 法が望ましい
    from scipy.linalg import toeplitz
    
    # LR方向の逆フィルタ設計: h_lr * g_lr ≈ δ
    # 正則化最小二乗: (H^T H + λI) g = H^T δ
    # 循環畳み込みの場合、周波数領域で解くのが効率的
    
    N_fft = 1 << int(np.ceil(np.log2(2 * n - 1)))
    
    LR = np.fft.rfft(lr_ir, n=N_fft)
    RL = np.fft.rfft(rl_ir, n=N_fft)
    
    # 正則化逆フィルタ: G = conj(H) / (|H|^2 + λ)
    reg = regularization
    inv_lr_freq = np.conj(LR) / (np.abs(LR)**2 + reg)
    inv_rl_freq = np.conj(RL) / (np.abs(RL)**2 + reg)
    
    # 時間領域に戻す
    inv_lr = np.fft.irfft(inv_lr_freq, n=N_fft)[:n].astype(np.float32)
    inv_rl = np.fft.irfft(inv_rl_freq, n=N_fft)[:n].astype(np.float32)
    
    # 因果性を保つため、前半にエネルギーを集中させる (最小位相化)
    inv_lr = _make_minimum_phase(inv_lr)
    inv_rl = _make_minimum_phase(inv_rl)
    
    return inv_lr, inv_rl


def _design_inverse_minphase(lr_ir: np.ndarray, rl_ir: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """最小位相反転フィルタ設計 (scipy.signal.minimum_phase 使用)。"""
    # scipy.signal.minimum_phase は scipy 1.10+ で利用可能
    try:
        from scipy.signal import minimum_phase
        inv_lr = minimum_phase(lr_ir, n_fft=len(lr_ir)*2, method="hilbert")
        inv_rl = minimum_phase(rl_ir, n_fft=len(rl_ir)*2, method="hilbert")
        return inv_lr.astype(np.float32), inv_rl.astype(np.float32)
    except ImportError:
        # フォールバック: LSQ法
        return _design_inverse_lsq(lr_ir, rl_ir, 1e-4)


def _make_minimum_phase(ir: np.ndarray) -> np.ndarray:
    """ヒルベルト変換による最小位相化。"""
    n = len(ir)
    N_fft = 1 << int(np.ceil(np.log2(2 * n - 1)))
    
    # 周波数領域
    spec = np.fft.rfft(ir, n=N_fft)
    mag = np.abs(spec)
    
    # 対数振幅スペクトル
    log_mag = np.log(mag + 1e-12)
    
    # ヒルベルト変換で位相を取得 (最小位相の位相)
    # 実部から虚部を復元 (Kramers-Kronig の関係)
    from scipy.signal import hilbert
    analytic = hilbert(log_mag)
    min_phase_spec = np.exp(analytic)
    
    # 元の位相情報を保持しつつ最小位相化
    # ここでは振幅スペクトルを保持し、位相を最小位相に置換
    phase = np.angle(spec)
    new_spec = mag * np.exp(1j * np.imag(analytic))
    
    # 時間領域に戻す
    min_phase_ir = np.fft.irfft(new_spec, n=N_fft)[:len(ir)]
    return min_phase_ir.astype(np.float32)


def save_ctc_ir(inv_lr: np.ndarray, inv_rl: np.ndarray, output_dir: Path, prefix: str = "ctc"):
    """CTC 逆フィルタ IR をステレオ WAV とメタデータ JSON で保存。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # ステレオ WAV として保存 (L=LR逆フィルタ, R=RL逆フィルタ)
    stereo_lr = np.column_stack((inv_lr, np.zeros_like(inv_lr))).astype(np.float32)
    stereo_rl = np.column_stack((np.zeros_like(inv_rl), inv_rl)).astype(np.float32)
    
    # L→R 逆フィルタ (ch0 に配置)
    lr_path = output_dir / f"{prefix}_lr.wav"
    wavfile.write(str(lr_path), SAMPLE_RATE, stereo_lr)
    
    # R→L 逆フィルタ (ch1 に配置)
    rl_path = output_dir / f"{prefix}_rl.wav"
    wavfile.write(str(rl_path), SAMPLE_RATE, stereo_rl)
    
    # メタデータ
    meta = {
        "schema_version": 1,
        "type": "ctc_inverse",
        "lr_file": f"{prefix}_lr.wav",
        "rl_file": f"{prefix}_rl.wav",
        "sample_rate": SAMPLE_RATE,
        "length_samples": len(stereo_lr),
        "duration_sec": len(stereo_lr) / SAMPLE_RATE,
        "peak_dbfs_lr": float(20 * np.log10(np.max(np.abs(inv_lr)) + 1e-12)),
        "peak_dbfs_rl": float(20 * np.log10(np.max(np.abs(inv_rl)) + 1e-12)),
        "rms_dbfs_lr": float(20 * np.log10(np.sqrt(np.mean(inv_lr**2)) + 1e-12)),
        "rms_dbfs_rl": float(20 * np.log10(np.sqrt(np.mean(inv_rl**2)) + 1e-12)),
    }
    
    meta_path = output_dir / f"{prefix}.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    
    print(f"Saved: {lr_path}")
    print(f"Saved: {rl_path}")
    print(f"Saved: {meta_path}")
    print(f"  LR peak: {meta['peak_dbfs_lr']:.2f} dBFS, RL peak: {meta['peak_dbfs_rl']:.2f} dBFS")


# ─────────────────────────────────────────────────────────────────────────────
# 検証ユーティリティ
# ─────────────────────────────────────────────────────────────────────────────
def verify_cancellation(original_lr: np.ndarray, original_rl: np.ndarray,
                        inv_lr: np.ndarray, inv_rl: np.ndarray) -> dict:
    """打ち消し性能を評価。"""
    # 畳み込み: original * inverse ≈ δ
    conv_lr = fftconvolve(original_lr, inv_lr)[:len(original_lr)]
    conv_rl = fftconvolve(original_rl, inv_rl)[:len(original_rl)]
    
    # 主ピークエネルギー比
    peak_lr = np.max(np.abs(conv_lr))
    peak_rl = np.max(np.abs(conv_rl))
    
    # ピーク以外のエネルギー (残留クロストーク)
    main_peak_idx = np.argmax(np.abs(conv_lr))
    mask = np.ones_like(conv_lr, dtype=bool)
    mask[max(0, main_peak_idx-10):min(len(conv_lr), main_peak_idx+10)] = False
    residual_lr = np.sqrt(np.mean(conv_lr[mask]**2))
    
    main_peak_idx_rl = np.argmax(np.abs(conv_rl))
    mask_rl = np.ones_like(conv_rl, dtype=bool)
    mask_rl[max(0, main_peak_idx_rl-10):min(len(conv_rl), main_peak_idx_rl+10)] = False
    residual_rl = np.sqrt(np.mean(conv_rl[mask_rl]**2))
    
    cancellation_lr = 20 * np.log10(residual_lr / (peak_lr + 1e-12)) if peak_lr > 0 else -np.inf
    cancellation_rl = 20 * np.log10(residual_rl / (peak_rl + 1e-12)) if peak_rl > 0 else -np.inf
    
    return {
        "peak_lr": float(peak_lr),
        "peak_rl": float(peak_rl),
        "cancellation_lr_db": float(cancellation_lr),
        "cancellation_rl_db": float(cancellation_rl),
        "residual_rms_lr": float(residual_lr),
        "residual_rms_rl": float(residual_rl),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CTC (Crosstalk Cancellation) IR 生成ツール")
    parser.add_argument("--lr-ir", type=str, help="L→R クロストーク IR ファイル (WAV)")
    parser.add_argument("--rl-ir", type=str, help="R→L クロストーク IR ファイル (WAV)")
    parser.add_argument("--method", choices=["lsq", "minphase"], default="lsq", help="逆フィルタ設計手法")
    parser.add_argument("--regularization", type=float, default=1e-4, help="正則化パラメータ")
    parser.add_argument("--prefix", type=str, default="ctc", help="出力ファイル名プレフィックス")
    parser.add_argument("--output-dir", type=str, help="出力ディレクトリ (デフォルト: ~/.config/camilladsp/ir)")
    parser.add_argument("--verify", action="store_true", help="打ち消し性能を検証")
    parser.add_argument("--check", action="store_true", help="既存 CTC IR の検証のみ")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir) if args.output_dir else IR_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.check:
        # 既存 CTC IR の検証
        for wav_file in sorted(IR_DIR.glob("ctc_*.wav")):
            prefix = wav_file.stem
            json_path = IR_DIR / f"{prefix}.json"
            try:
                sr, ir = wavfile.read(wav_file)
                print(f"{prefix}: sr={sr}, ch={ir.shape[1] if ir.ndim==2 else 1}, len={len(ir)/sr:.2f}s")
                if json_path.exists():
                    with open(json_path) as f:
                        meta = json.load(f)
                    print(f"  meta: {meta}")
            except Exception as e:
                print(f"{prefix}: ERROR - {e}")
        return
    
    if not args.lr_ir or not args.rl_ir:
        parser.error("--lr-ir and --rl-ir are required")
    
    # 入力 IR 読み込み
    print(f"Loading LR IR: {args.lr_ir}")
    print(f"Loading RL IR: {args.rl_ir}")
    sr_lr, lr_ir = wavfile.read(args.lr_ir)
    sr_rl, rl_ir = wavfile.read(args.rl_ir)
    
    assert sr_lr == SAMPLE_RATE, f"LR IR sample rate mismatch: {sr_lr} != {SAMPLE_RATE}"
    assert sr_rl == SAMPLE_RATE, f"RL IR sample rate mismatch: {sr_rl} != {SAMPLE_RATE}"
    
    # 逆フィルタ設計
    print(f"Designing inverse filters (method={args.method}, reg={args.regularization})...")
    inv_lr, inv_rl = design_ctc_inverse_filter(
        lr_ir, rl_ir, method=args.method, regularization=args.regularization
    )
    
    # 保存
    save_ctc_ir(inv_lr, inv_rl, output_dir, args.prefix)
    
    # 検証
    if args.verify:
        print("Verifying cancellation performance...")
        result = verify_cancellation(
            np.mean(wavfile.read(args.lr_ir)[1], axis=1) if wavfile.read(args.lr_ir)[1].ndim == 2 else wavfile.read(args.lr_ir)[1],
            np.mean(wavfile.read(args.rl_ir)[1], axis=1) if wavfile.read(args.rl_ir)[1].ndim == 2 else wavfile.read(args.rl_ir)[1],
            inv_lr, inv_rl
        )
        print(f"Cancellation LR: {result['cancellation_lr_db']:.1f} dB")
        print(f"Cancellation RL: {result['cancellation_rl_db']:.1f} dB")
        if result['cancellation_lr_db'] < -10 and result['cancellation_rl_db'] < -10:
            print("SUCCESS: Cancellation > 10 dB achieved")
        else:
            print("WARNING: Cancellation may be insufficient")


if __name__ == "__main__":
    main()
