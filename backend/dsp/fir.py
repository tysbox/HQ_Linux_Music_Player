"""FIR 全帯域キャリブレーション (Bisen移植 追加 Step / 決定 D-5).

PEQ (最大 10 バンド = 10 制御点) では近似できない全帯域連続補正を、
minimum-phase FIR で実現する:

    bands (PEQ 定義) → 全帯域連続応答 (RBJ biquad 合成)
                    → firwin2 で線形位相 FIR 合成
                    → minimum_phase 変換 (pre-ringing 無し・アナログ EQ 的挙動)
                    → 192kHz float32 stereo WAV IR (CamillaDSP Conv 用)

設計根拠 (計画書 §3-A-2):
- Conv フィルタ (WAV IR) は Reverb IR / CTC で実績済み → 導入リスク小
- min-phase 推奨: pre-ringing が無くアナログ EQ と同じ因果挙動
- レイテンシ: min-phase でも数 ms 程度 — 音楽再生では無問題
- venv: numpy 2.5.x / scipy 1.18.x 確認済み (firwin2 / minimum_phase 使用可)

強度スケーリング (headphone_intensity) は PEQ と同じ意味論:
band gain にのみスケールし、preamp はスケールしない (Bisen 仕様)。
"""
import hashlib
import logging
import os
import struct
import wave
from pathlib import Path

import numpy as np
from scipy.signal import firwin2, minimum_phase

from backend.dsp.analysis import rbj_coefficients, magnitude_response_db

logger = logging.getLogger(__name__)

SAMPLE_RATE = 192000
# FIR タップ数: 192kHz で約 85ms の長さ。min-phase 変換でエネルギーは先頭に
# 集約されるため実効レイテンシはほぼゼロ (10% エネルギー到達 = 0ms)。
# タップ数は低域精度の決定要素: 4097 で最大誤差 0.74dB、8193 で 0.28dB、
# 16385 で 0.10dB (20Hz lowshelf 実測)。生成時間は 0.85s (キャッシュ付き)。
# 奇数 (Type I): 偶数タップ (Type II) はナイキスト增益が 0 制約を受けるため
# 高域補正 (highshelf 等) が歪む。Type I はナイキスト增益が自由。
FIR_TAPS = 16385
# 応答サンプリングの周波数点数 (firwin2 の grid)。
# 線形等間隔のため低域の狭-Q band (例: 67Hz Q1.41 = 帯域幅 ~47Hz) を捉えるには
# 高解像度が必要: 1024 点 (間隔 93.8Hz) だと 67Hz band を格子点間で見逃し
# 最大 1.7dB 誤差。8192 点 (間隔 11.7Hz) で最大 0.34dB / 平均 0.03dB。
FIR_GRID = 8192

# FIR IR の保存先 (Reverb IR と同一ディレクトリ = CamillaDSP Conv が参照する場所)
FIR_IR_DIR = Path(os.path.expanduser("~/.config/camilladsp/ir"))

_TYPE_MAP = {
    "peaking": "peaking",
    "lowshelf": "lowshelf",
    "highshelf": "highshelf",
    "lowpass": "lowpass",
    "highpass": "highpass",
    "notch": "notch",
}


def _band_response_db(bands: list[dict], gain_scale: float, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """PEQ bands の全帯域合成振幅応答 [dB] を計算。

    Returns:
        (frequencies, response_db) — frequencies は firwin2 用に
        0..fs/2 を FIR_GRID 点で線形サンプリング (端点含む)。
    """
    freqs = np.linspace(0.0, fs / 2.0, FIR_GRID)
    total = np.zeros_like(freqs, dtype=float)
    for band in bands:
        btype = _TYPE_MAP.get(band.get("type", "peaking"))
        if btype is None:
            continue
        gain = float(band.get("gain", 0.0)) * gain_scale
        b, a = rbj_coefficients(btype, float(band.get("freq", 1000.0)),
                                float(band.get("q", 0.707)), gain, fs)
        total += magnitude_response_db(b, a, freqs, fs)
    return freqs, total


def _write_wav_stereo_float32(path: Path, impulse: np.ndarray) -> None:
    """単位インパルス列を 2ch float32 WAV (192kHz) として保存。

    CamillaDSP Conv の Wav 形式 (既存 Reverb IR と同一: RIFF float32)。
    L/R 同一 (ヘッドホン補正は左右共通)。
    """
    data = np.column_stack((impulse, impulse)).astype(np.float32)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(4)  # float32 = 4 bytes (WAVE_FORMAT_IEEE_FLOAT)
        wf.setframerate(SAMPLE_RATE)
        # wave モジュールは fmt=3 (IEEE float) を直接サポートしないため
        # raw ヘッダを書く (既存 IR と同一形式)。
        wf.close()
    # 手動で fmt=3 ヘッダ + data を書く
    n_frames = data.shape[0]
    data_bytes = data.tobytes()
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data_bytes)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 3, 2, SAMPLE_RATE,
                                 SAMPLE_RATE * 8, 8, 32)
    hdr += b"data" + struct.pack("<I", len(data_bytes))
    tmp = str(path) + "._converting.wav"
    with open(tmp, "wb") as f:
        f.write(hdr)
        f.write(data_bytes)
    os.replace(tmp, path)


def generate_fir_ir(profile: dict, gain_scale: float = 1.0,
                    taps: int = FIR_TAPS, fs: float = SAMPLE_RATE) -> Path | None:
    """プロファイル bands から min-phase FIR IR を生成して保存。

    Args:
        profile: プロファイル辞書 (bands / preamp_db を含む。preamp は
            FIR に含めず Gain フィルタとして別途注入されるためここでは無視)
        gain_scale: band ゲインのスケール (headphone_intensity / 100)
        taps: FIR タップ数
        fs: サンプリングレート

    Returns:
        保存した WAV IR のパス。bands が空 / 生成失敗は None。
    """
    bands = [b for b in profile.get("bands", []) if b.get("type") in _TYPE_MAP]
    if not bands:
        return None

    # キャッシュパス: プロファイル内容 + 強度 + タップ数のハッシュ。
    # 生成 (firwin2 + minimum_phase ≈ 0.8s) より先に判定してヒット時は即返す。
    key = json_hash(profile, gain_scale, taps, fs)
    FIR_IR_DIR.mkdir(parents=True, exist_ok=True)
    out = FIR_IR_DIR / f"hp_fir_{key}.wav"
    if out.exists():
        return out

    freqs, resp_db = _band_response_db(bands, gain_scale, fs)
    resp_lin = 10.0 ** (resp_db / 20.0)

    # firwin2 (scipy 1.18): 周波数は Hz で渡し fs= を指定する (正規化 0..1 は
    # fs=None 時の仕様)。グリッドは 0..fs/2 昇順・端点必須 (linspace が満たす)。
    fir_lin = firwin2(taps, freqs, resp_lin, fs=fs, window="hamming")
    # minimum_phase 変換 (pre-ringing除去・因果 FIR 化)。
    # half=False: 振幅スペクトルを元のまま維持 (half=True 既定は平方根になる
    # 仕様のため補正量が半減する — scipy 1.14+ のドキュメント参照)。
    # DC 正規化は行わない: PEQ 応答の DC 値 (lowshelf 減衰等) が絶対ゲインとして
    # 正しいため。preamp は Gain フィルタで別途注入される。
    fir_min = minimum_phase(fir_lin, method="homomorphic", half=False)

    try:
        _write_wav_stereo_float32(out, fir_min.astype(np.float32))
        return out
    except Exception:
        logger.warning("FIR IR write failed", exc_info=True)
        if out.exists():
            os.remove(out)
        return None


def json_hash(profile: dict, gain_scale: float, taps: int, fs: float) -> str:
    """FIR IR ファイル名用の短いコンテンツハッシュ (内容変化で再生成)。"""
    payload = {
        "bands": [
            {k: b.get(k) for k in ("type", "freq", "q", "gain")}
            for b in profile.get("bands", [])
        ],
        "scale": round(float(gain_scale), 4),
        "taps": int(taps),
        "fs": int(fs),
    }
    import json
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def fir_response_db(ir_path: Path, frequencies: np.ndarray,
                    fs: float = SAMPLE_RATE) -> np.ndarray:
    """保存済み FIR IR の振幅応答 [dB] を計算 (検証・Total Curve 表示用)。"""
    from scipy.io import wavfile
    sr, data = wavfile.read(str(ir_path))
    if data.ndim == 2:
        data = data[:, 0]
    # FFT ベースの振幅応答
    n = 1 << int(np.ceil(np.log2(len(data) + len(frequencies))))
    spec = np.fft.rfft(data, n)
    freq_axis = np.fft.rfftfreq(n, d=1.0 / sr)
    resp = np.interp(frequencies, freq_axis, np.abs(spec))
    return 20.0 * np.log10(resp + 1e-12)
