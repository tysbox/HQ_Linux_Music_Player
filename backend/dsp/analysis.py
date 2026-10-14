#!/usr/bin/env python3
"""DSP 周波数応答解析モジュール（Stage 2: 応答解析とゲイン計算）

numpy ベクトル化による高速な biquad/フィルタ応答計算。
Stage 3〜5 の検証基盤として使用する。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_analysis -v

参考: RBJ Audio EQ Cookbook
  https://www.w3.org/TR/audio-eq-cookbook/
"""
import os

import numpy as np
from typing import Literal


# ─────────────────────────────────────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 192000  # CamillaDSP 固定


# ─────────────────────────────────────────────────────────────────────────────
# RBJ Biquad 係数計算（Audio EQ Cookbook 準拠）
# ─────────────────────────────────────────────────────────────────────────────
def rbj_coefficients(
    filter_type: Literal["peaking", "lowshelf", "highshelf", "lowpass", "highpass", "notch", "allpass"],
    freq_hz: float,
    q: float,
    gain_db: float,
    fs: float = SAMPLE_RATE,
) -> tuple[np.ndarray, np.ndarray]:
    """
    RBJ Cookbook に基づく biquad 係数 (b, a) を計算。

    Args:
        filter_type: フィルタタイプ
        freq_hz: 中心/カットオフ周波数
        q: Q 値（品質因子）
        gain_db: ゲイン [dB]（peaking/lowshelf/highshelf で使用）
        fs: サンプリングレート

    Returns:
        (b, a): 分子・分母係数配列 (形状: (3,), (3,))
    """
    w0 = 2.0 * np.pi * freq_hz / fs
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * q)
    A = 10.0 ** (gain_db / 40.0)  # 振幅ゲイン（dB → 線形）

    if filter_type == "peaking":
        b0 = 1.0 + alpha * A
        b1 = -2.0 * cos_w0
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha / A

    elif filter_type == "lowshelf":
        beta = np.sqrt(A) / q
        b0 = A * ((A + 1.0) - (A - 1.0) * cos_w0 + beta * sin_w0)
        b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w0)
        b2 = A * ((A + 1.0) - (A - 1.0) * cos_w0 - beta * sin_w0)
        a0 = (A + 1.0) + (A - 1.0) * cos_w0 + beta * sin_w0
        a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cos_w0)
        a2 = (A + 1.0) + (A - 1.0) * cos_w0 - beta * sin_w0

    elif filter_type == "highshelf":
        beta = np.sqrt(A) / q
        b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + beta * sin_w0)
        b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
        b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - beta * sin_w0)
        a0 = (A + 1.0) - (A - 1.0) * cos_w0 + beta * sin_w0
        a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
        a2 = (A + 1.0) - (A - 1.0) * cos_w0 - beta * sin_w0

    elif filter_type == "lowpass":
        b0 = (1.0 - cos_w0) / 2.0
        b1 = 1.0 - cos_w0
        b2 = (1.0 - cos_w0) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha

    elif filter_type == "highpass":
        b0 = (1.0 + cos_w0) / 2.0
        b1 = -(1.0 + cos_w0)
        b2 = (1.0 + cos_w0) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha

    elif filter_type == "notch":
        b0 = 1.0
        b1 = -2.0 * cos_w0
        b2 = 1.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha

    elif filter_type == "allpass":
        b0 = 1.0 - alpha
        b1 = -2.0 * cos_w0
        b2 = 1.0 + alpha
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha

    else:
        raise ValueError(f"Unknown filter type: {filter_type}")

    # 正規化
    b = np.array([b0, b1, b2]) / a0
    a = np.array([1.0, a1 / a0, a2 / a0])
    return b, a

# ─────────────────────────────────────────────────────────────────────────────
# 周波数応答計算（ベクトル化）
# ─────────────────────────────────────────────────────────────────────────────
def frequency_response(
    b: np.ndarray,
    a: np.ndarray,
    frequencies: np.ndarray,
    fs: float = SAMPLE_RATE,
) -> np.ndarray:
    """
    複素周波数応答 H(f) をベクトル化計算。

    Args:
        b: 分子係数
        a: 分母係数
        frequencies: 周波数配列 [Hz]
        fs: サンプリングレート

    Returns:
        複素応答配列
    """
    w = 2.0 * np.pi * frequencies / fs
    z = np.exp(-1j * w)

    # 分子・分母の多項式評価（ホーナー法的ベクトル化）
    num = b[0] + b[1] * z + b[2] * z**2
    den = a[0] + a[1] * z + a[2] * z**2

    return num / den


def magnitude_response_db(
    b: np.ndarray,
    a: np.ndarray,
    frequencies: np.ndarray,
    fs: float = SAMPLE_RATE,
) -> np.ndarray:
    """振幅応答 [dB] を計算。"""
    H = frequency_response(b, a, frequencies, fs)
    return 20.0 * np.log10(np.abs(H) + 1e-12)


def phase_response_rad(
    b: np.ndarray,
    a: np.ndarray,
    frequencies: np.ndarray,
    fs: float = SAMPLE_RATE,
) -> np.ndarray:
    """位相応答 [rad] を計算。"""
    H = frequency_response(b, a, frequencies, fs)
    return np.angle(H)


# ─────────────────────────────────────────────────────────────────────────────
# フィルタ辞書からの応答計算（yaml_generator 互換）
# ─────────────────────────────────────────────────────────────────────────────
def filter_dict_to_response(
    filter_dict: dict,
    frequencies: np.ndarray,
    fs: float = SAMPLE_RATE,
) -> np.ndarray:
    """
    CamillaDSP フィルタ定義辞書から振幅応答 [dB] を計算。

    Args:
        filter_dict: {"type": "Biquad", "parameters": {...}} または Gain/Delay/Conv
        frequencies: 周波数配列
        fs: サンプリングレート

    Returns:
        振幅応答 [dB] 配列（形状: (len(frequencies),)）
    """
    ftype = filter_dict.get("type", "")
    params = filter_dict.get("parameters", {})

    if ftype == "Gain":
        gain_db = params.get("gain", 0.0)
        return np.full_like(frequencies, gain_db, dtype=float)

    elif ftype == "Delay":
        # 遅延は振幅に影響しない（位相のみ）
        return np.zeros_like(frequencies, dtype=float)

    elif ftype == "Conv":
        # IR 畳み込みの振幅応答を実計算する (追加 Step D-5 / R-1 対策)。
        # FIR キャリブレーション IR (hp_fir_*.wav) のブーストが
        # max_gain_of_config (= Stage 2-5 自動ヘッドルーム) から漏れると
        # クリップするため、WAV を読んで FFT 応答を返す。
        #
        # Reverb/CTC IR は対象外 (従来どおり 0dB):
        # - Reverb IR は WET path (headroom 計算対象外) にのみ存在するが
        #   max_gain_of_config は filters 全体を見るため、長大な残響 IR の
        #   |H(f)| (+21dB) を数え上げると誤ったヘッドルームになる。
        # - CTC IR は減衰のみ。
        filename = params.get("filename", "")
        if "hp_fir_" not in os.path.basename(filename):
            return np.zeros_like(frequencies, dtype=float)
        try:
            from scipy.io import wavfile as _wavfile
            _sr, _ir = _wavfile.read(filename)
            if _ir.ndim == 2:
                _ir = _ir[:, 0]
            _ir = _ir.astype(np.float64)
            _n = 1 << int(np.ceil(np.log2(len(_ir) + len(frequencies))))
            _spec = np.abs(np.fft.rfft(_ir, _n))
            _fax = np.fft.rfftfreq(_n, d=1.0 / _sr)
            _resp = np.interp(frequencies, _fax, _spec)
            return 20.0 * np.log10(_resp + 1e-12)
        except Exception:
            # 読み取り不能時は 0dB (呼び出し側で処理)
            return np.zeros_like(frequencies, dtype=float)

    elif ftype == "Biquad":
        bq_type = params.get("type", "Peaking")
        freq_hz = params.get("freq", 1000.0)
        q = params.get("q", 0.707)
        gain_db = params.get("gain", 0.0)

        # CamillaDSP タイプ名 → RBJ タイプ名マッピング
        # 2026-10-12: CamillaDSP 4.1.3 の正しい型名 Lowshelf/Highshelf を追加。
        # 旧キー (LowShelf/HighShelf) は profiles.py のバグで生成され得た無効名の
        # 互換維持として残す (実害なし)。
        type_map = {
            "Peaking": "peaking",
            "LowShelf": "lowshelf",
            "HighShelf": "highshelf",
            "Lowshelf": "lowshelf",
            "Highshelf": "highshelf",
            "Lowpass": "lowpass",
            "Highpass": "highpass",
            "Notch": "notch",
            "Allpass": "allpass",
            "LinkwitzTransform": "peaking",  # 近似
        }
        rbj_type = type_map.get(bq_type, "peaking")

        b, a = rbj_coefficients(rbj_type, freq_hz, q, gain_db, fs)
        return magnitude_response_db(b, a, frequencies, fs)

    else:
        # 未知タイプは 0dB
        return np.zeros_like(frequencies, dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# 合成応答計算（複数フィルタの直列接続）
# ─────────────────────────────────────────────────────────────────────────────
def combined_response_db(
    filter_dicts: list[dict],
    frequencies: np.ndarray,
    fs: float = SAMPLE_RATE,
) -> np.ndarray:
    """
    複数フィルタの直列接続による合成振幅応答 [dB] を計算。

    Args:
        filter_dicts: フィルタ定義辞書のリスト
        frequencies: 周波数配列
        fs: サンプリングレート

    Returns:
        合成振幅応答 [dB] 配列
    """
    if not filter_dicts:
        return np.zeros_like(frequencies, dtype=float)

    total_db = np.zeros_like(frequencies, dtype=float)
    for fd in filter_dicts:
        total_db += filter_dict_to_response(fd, frequencies, fs)
    return total_db


# ─────────────────────────────────────────────────────────────────────────────
# 公開 API: プリセット/設定からの最大ゲイン計算
# ─────────────────────────────────────────────────────────────────────────────
def max_gain_of_config(
    filters_dict: dict,
    frequencies: np.ndarray | None = None,
    fs: float = SAMPLE_RATE,
) -> float:
    """
    YAML の filters 辞書から最大ゲイン [dB] を計算。

    Args:
        filters_dict: yaml_generator が生成する filters 辞書
        frequencies: 計算用周波数配列（None なら自動生成）
        fs: サンプリングレート

    Returns:
        最大ゲイン [dB]
    """
    if frequencies is None:
        # 対数スケールで 10Hz〜96kHz を 1000 点
        frequencies = np.logspace(np.log10(10), np.log10(fs / 2), 1000)

    # すべてのフィルタ応答を合算（直列接続と仮定）
    total_db = np.zeros_like(frequencies, dtype=float)
    for fname, fdict in filters_dict.items():
        total_db += filter_dict_to_response(fdict, frequencies, fs)

    return float(np.max(total_db))
