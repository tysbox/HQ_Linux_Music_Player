#!/usr/bin/env python3
"""
IR 最適化スクリプト (192kHz / 32bit float / 可聴限界以下のテイル除去)

参照: https://manual.camille/docs/ ... (CamillaDSP manual)
- 直接音スパイクを除去（ピーク + 2ms 以降を切り出し）
- max_duration (既定 1.2秒) で末尾を cosine フェードアウト
- scipy.signal.resample_poly で 192kHz に高品質リサンプル
- ピークを -6 dBFS にノーマライズ
- 32bit float WAV (FLOAT subtype) で保存

使い方:
  python3 optimize_ir.py <input_48k.wav> <output_192k.wav>
  python3 optimize_ir.py <input_48k.wav>            # -> <basename>_192k.wav
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd


def optimize_ir(input_file: str,
                output_file: str | None = None,
                target_sr: int = 192000,
                max_duration: float = 1.2,
                direct_sound_skip_ms: float = 2.0) -> str:
    """48kHz (or any rate) の IR を 192kHz/32bit float に最適化する.

    Parameters
    ----------
    input_file : str
        入力 IR (48kHz/16bit/stereo 想定、ただし任意フォーマット可)
    output_file : str | None
        出力先。未指定なら <input>_192k.wav
    target_sr : int
        出力サンプリングレート (デフォルト 192000)
    max_duration : float
        残響をカットする最大秒数 (デフォルト 1.2 秒)
    direct_sound_skip_ms : float
        直接音ピークからスキップする秒数 (デフォルト 2ms)

    Returns
    -------
    出力ファイルパス
    """
    in_path = Path(input_file)
    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")

    if output_file is None:
        output_file = str(in_path.with_name(f"{in_path.stem}_192k.wav"))
    out_path = Path(output_file)

    print(f"[optimize_ir] Input : {in_path}")
    print(f"[optimize_ir] Output: {out_path}")

    # 1. 読み込み
    data, sr = sf.read(str(in_path), always_2d=True)
    if data.ndim != 2 or data.shape[1] != 2:
        raise ValueError(f"Expected stereo IR, got shape {data.shape}")
    print(f"[optimize_ir] Loaded: SR={sr}, channels=2, frames={data.shape[0]}, "
          f"duration={data.shape[0] / sr:.3f}s, dtype={data.dtype}")

    if sr <= 0:
        raise ValueError(f"Invalid sample rate: {sr}")

    # 2. 各チャンネルを処理
    processed: list[np.ndarray] = []
    for ch_idx in range(2):
        x = data[:, ch_idx].astype(np.float64)

        # 2-a. 直接音 (Direct Sound) トリミング
        # 提供資料: "IR先頭の直接音トリミング"
        #   "Audacityなどの波形編集ソフトでIR出力データを開き、先頭に鋭いスパイク
        #    （直接音）がある場合は、そのピーク直後までをカット（またはゼロクロス点
        #    から数ミリ秒フェードイン）させて「初期反射と残響テイルのみ」を抽出した
        #    IRに加工します。"
        #
        # 単純な peak+skip では最初のサンプル近傍の小さいピークに引っかかり、
        # 直接音本体 (先頭 5-10ms) が残る問題があった。
        # → 先頭 5ms を「完全にゼロクリア」+ 続く 5ms を cosine フェードインする
        #   ことで、コムフィルタ (位相干渉) の原因となる直接音を根絶する。
        direct_zero_ms = 5.0
        fade_in_ms = 5.0
        direct_zero_samples = int(direct_zero_ms * 0.001 * sr)
        fade_in_samples = int(fade_in_ms * 0.001 * sr)

        # ピーク検出 (情報表示用のみ、実処理は時間ベース)
        peak_idx = int(np.argmax(np.abs(x)))
        print(f"[optimize_ir]   ch{ch_idx}: orig peak@{peak_idx} "
              f"({peak_idx / sr * 1000:.2f}ms), magnitude={abs(x[peak_idx]):.4f}")

        # 先頭を強制ゼロクリア → cosine フェードイン
        end_zero = min(direct_zero_samples, len(x))
        x[:end_zero] = 0.0
        end_fade = min(direct_zero_samples + fade_in_samples, len(x))
        if end_fade > end_zero:
            n = end_fade - end_zero
            fade_curve = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n)))
            x[end_zero:end_fade] *= fade_curve
        print(f"[optimize_ir]   ch{ch_idx}: zeroed first {direct_zero_ms}ms "
              f"({direct_zero_samples} samples) + {fade_in_ms}ms cosine fade-in")

        # 2-b. max_duration に切り詰め + 末尾 cosine フェード
        max_samples = int(max_duration * sr)
        if len(x) > max_samples:
            x = x[:max_samples].copy()
            fade_len = max(1, int(max_samples * 0.20))
            fade_curve = 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fade_len)))
            x[-fade_len:] *= fade_curve
            print(f"[optimize_ir]   ch{ch_idx}: truncated to {max_samples} samples "
                  f"({max_duration}s) with {fade_len}-sample cosine fade-out")

        processed.append(x)

    # 3. チャンネル長を揃える
    min_len = min(len(c) for c in processed)
    matrix = np.column_stack([c[:min_len] for c in processed]).astype(np.float64)
    print(f"[optimize_ir] Pre-resample: {matrix.shape[0]} samples, "
          f"{matrix.shape[0] / sr:.3f}s @ {sr}Hz")

    # 4. 192kHz へ高品質リサンプル (polyphase)
    if sr != target_sr:
        g = gcd(target_sr, sr)
        up = target_sr // g
        down = sr // g
        print(f"[optimize_ir] Resampling: up={up}, down={down} ({sr} -> {target_sr} Hz)")
        matrix = resample_poly(matrix, up, down, axis=0)
    print(f"[optimize_ir] Post-resample: {matrix.shape[0]} samples, "
          f"{matrix.shape[0] / target_sr:.3f}s @ {target_sr}Hz")

    # 5. ピーク -6 dBFS にノーマライズ (オーバーフロー防止)
    max_val = float(np.max(np.abs(matrix)))
    if max_val > 0:
        target_peak = 10.0 ** (-6.0 / 20.0)  # -6 dBFS ≈ 0.5012
        matrix = (matrix / max_val) * target_peak
        print(f"[optimize_ir] Normalized: peak {max_val:.4f} -> "
              f"{np.max(np.abs(matrix)):.4f} (-6 dBFS)")

    # 6. 32bit float WAV で保存 (FLOAT subtype)
    sf.write(str(out_path), matrix, target_sr, subtype='FLOAT', format='WAV')
    print(f"[optimize_ir] Saved: {out_path} "
          f"(taps={matrix.shape[0]}, duration={matrix.shape[0] / target_sr:.2f}s)")

    return str(out_path)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python3 optimize_ir.py <input.wav> [output.wav]")
        return 1
    in_file = argv[1]
    out_file = argv[2] if len(argv) >= 3 else None
    try:
        optimize_ir(in_file, out_file)
    except Exception as e:
        print(f"[optimize_ir] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))