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
    # Stage 8 (Bisen移植 Phase 1): ホンキャリブレーション (AutoEq)
    # "none" = 無効 (フィルタ追加なし = 従来の YAML 生成結果と完全一致)
    headphone_profile: str = "none"
    # 補正強度 0-100 (Bisen calibrationIntensity と同じ意味論。50 = 補正半分)
    headphone_intensity: int = 50
    # リキャリブレーション先 (Bisen targetCurveId 相当)。
    # "harman"(既定: リスニング補正のみ=AutoEqターゲット近似) / "flat" / "bypass"(素の音)
    # / 機種プロファイルID (当該機種の特性へ近づける = リキャリブレーション)
    headphone_target: str = "harman"
    # Phase 3 (Bisen移植): bisen-dspd デーモン経由の非線形処理。
    # tube: "none" = 無効 (デーモン未経路 = 従来の YAML 生成結果と完全一致)
    #       "triode" = 300B / "pentode" = KT88
    tube: str = "none"
    tube_bias: int = 50               # バイアス 0-100 (Bisen 内部仕様 0..1 に正規化)
    # restore: 3 モード固定切替 (2026-10-13 利用者指示)
    #   "none" = 無効 / "lossy_standard" = 擬似ロスレス / "lossy_high" = 低ビットレート向け
    #   / "cd" = 疑似ハイレゾ (超音波帯倍音生成)
    restore: str = "none"


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
    # Stage 8 (Bisen移植 Phase 1): ホンキャリブレーション
    headphone_profile: str = "none"   # プロファイル ID ("none" = 無効)
    headphone_intensity: int = 50      # 補正強度 (0-100)
    headphone_target: str = "harman"   # リキャリブレーション先 (harman/flat/bypass/機種ID)
    # Phase 3 (Bisen移植): bisen-dspd 経由 (CamillaDSP YAML には現れない)
    tube: str = "none"
    tube_bias: int = 50
    restore: str = "none"


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