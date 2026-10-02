"""DSP 共通 Pydantic モデル・定数 (Single Source of Truth).

backend/main.py から AudioConfig 等を移設。
hq_api, state_manager, tests 等はここから import する。
FastAPI 等の Web フレームワーク非依存（純粋ロジック・データ定義）。
"""

from pydantic import BaseModel
from typing import List


class AudioConfig(BaseModel):
    """DSP 全設定 (Apply / Restart 用)."""

    mode: str
    device: str
    volume: float
    music_type: str
    eq_output: str
    crossfeed: str
    crossfeed_intensity: int = 5
    hum_noise: str
    reverb: str
    reverb_intensity: int = 5
    # Stage 6: 聴感比較基盤
    tilt: float = 0.0              # ティルト EQ (-3.0 ~ +3.0 dB)
    balance: float = 0.0           # 左右バランス (-1.0=左寄り ~ +1.0=右寄り)
    eq_left: List = []             # 左ch独立 EQ（Peaking フィルタ配列）
    eq_right: List = []            # 右ch独立 EQ
    loudness_ref: float = 80.0     # 基準ラウドネス [dB SPL]
    loudness_enabled: bool = False # ラウドネス補正有効
    # 絶対位相 (Absolute Phase): 全チャンネルの 180° 反転
    # 既定 False = 既存の位相を保つ。True にすると出力段で反転する。
    absolute_phase: bool = False
    # Stage 7: CTC (Crosstalk Cancellation)
    ctc: str = "none"              # CTC モード (none/ctc)
    ctc_intensity: int = 50        # CTC 強度 (0-100)


class VolumeControl(BaseModel):
    """音量のみ変更用."""

    volume: float


class StoredAudioConfig(AudioConfig):
    """永続化用 (AudioConfig と同一フィールド)."""
    pass


class DspParams(BaseModel):
    """DSP パラメータのみ更新 (ALSA 切替なし、停止なし)."""

    music_type: str = "none"
    eq_output: str = "none"
    crossfeed: str = "none"
    crossfeed_intensity: int = 5
    hum_noise: str = "none"
    reverb: str = "none"
    reverb_intensity: int = 5
    # Stage 6: 聴感比較基盤
    tilt: float = 0.0
    balance: float = 0.0
    eq_left: List = []
    eq_right: List = []
    loudness_ref: float = 80.0
    loudness_enabled: bool = False
    # 絶対位相 (Absolute Phase) ON/OFF
    absolute_phase: bool = False
    # Stage 7: CTC (Crosstalk Cancellation)
    ctc: str = "none"
    ctc_intensity: int = 50


# ─────────────────────────────────────────────────────────────────────────────
# 既定値定数 (Single Source of Truth)
# ─────────────────────────────────────────────────────────────────────────────
# 2026-10-02: 既定出力デバイス。
#   Bluetooth を既定にすると、BT 切断時に CamillaDSP が playback を開けず
#   exit 0 で自滅し、Restart=on-failure も効かずに無音が続く。
#   SP (PCH) なら BT の有無に依存せず CamillaDSP は生存するため、
#   既定とフォールバック先の双方を SP とする。
#   起動時の可聴音を避けるため -25dB（VOLUME_DEFAULT）を使う。
DEFAULT_DEVICE = "plughw:1,0"
VOLUME_DEFAULT = -25.0


def _default_audio_config() -> dict:
    """Legacy default (state_manager 用・互換維持).
    
    注: 実運用では models.py の DEFAULT_DEVICE/VOLUME_DEFAULT が優先される。
    ここは state_manager 内部の fallback 用として残す。
    """
    return {
        "mode": "pure",
        "device": "",
        "volume": -5.0,
        "music_type": "none",
        "eq_output": "none",
        "crossfeed": "none",
        "crossfeed_intensity": 5,
        "hum_noise": "none",
        "reverb": "none",
        "reverb_intensity": 5,
    }


__all__ = [
    "AudioConfig",
    "VolumeControl", 
    "StoredAudioConfig",
    "DspParams",
    "DEFAULT_DEVICE",
    "VOLUME_DEFAULT",
    "_default_audio_config",
]