"""DSP 状態管理モジュール（D-2 分離）.

backend/main.py から設定永続化・正規化・前提条件チェックを移植。
FastAPI 等の Web フレームワーク非依存（純粋ロジック）。
"""

import json
import os
from typing import Optional

from fastapi import HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# 定数定義
# ─────────────────────────────────────────────────────────────────────────────
LAST_CONFIG_PATH = os.path.expanduser("~/.config/audiophile/last_config.json")
PRESETS_PATH = os.path.expanduser("~/.config/audiophile/presets.json")


# ─────────────────────────────────────────────────────────────────────────────
# 内部ヘルパー関数
# ─────────────────────────────────────────────────────────────────────────────
def _default_audio_config() -> dict:
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


# ─────────────────────────────────────────────────────────────────────────────
# 設定永続化
# ─────────────────────────────────────────────────────────────────────────────
def load_last_config() -> dict:
    """前回保存された設定を読み込み（存在しない場合はデフォルト）。"""
    config = _default_audio_config()
    try:
        if os.path.exists(LAST_CONFIG_PATH):
            with open(LAST_CONFIG_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update(data)
    except Exception:
        pass
    return config


def save_last_config(config_dict: dict):
    """設定を永続化。"""
    os.makedirs(os.path.dirname(LAST_CONFIG_PATH), exist_ok=True)
    with open(LAST_CONFIG_PATH, "w") as f:
        json.dump(config_dict, f)


def update_last_config(patch: dict):
    """設定を部分更新して永続化。"""
    config = load_last_config()
    config.update(patch)
    save_last_config(config)


# ─────────────────────────────────────────────────────────────────────────────
# 設定正規化・比較
# ─────────────────────────────────────────────────────────────────────────────
def config_requires_restart(config: "AudioConfig", last_config: Optional[dict]) -> bool:
    """前回設定と比較し、DSP 再起動が必要か判定。"""
    if last_config is None:
        return True
    for key in [
        "mode",
        "device",
        "music_type",
        "eq_output",
        "crossfeed",
        "crossfeed_intensity",
        "hum_noise",
        "reverb",
        "reverb_intensity",
    ]:
        if last_config.get(key) != getattr(config, key):
            return True
    return False


def normalize_config_for_device(config: "AudioConfig", requested_mode: Optional[str] = None) -> "AudioConfig":
    """Bluetooth を pure で選択した場合は DSP でパススルーし、処理をすべて無効化する。"""
    if "bluealsa" in config.device and requested_mode == "pure":
        # 循環 import 回避のため遅延 import
        from backend.main import AudioConfig
        return AudioConfig(
            mode="dsp",
            device=config.device,
            volume=config.volume,
            music_type="none",
            eq_output="none",
            crossfeed="none",
            hum_noise="none",
            reverb="none",
            reverb_intensity=5,
        )
    if "bluealsa" in config.device:
        config.mode = "dsp"
    return config


# ─────────────────────────────────────────────────────────────────────────────
# 前提条件チェック
# ─────────────────────────────────────────────────────────────────────────────
def has_loopback_capture_device() -> bool:
    """ALSA Loopback キャプチャデバイスの存在確認。"""
    capture_path = "/proc/asound/Loopback/pcm1c/info"
    return os.path.exists(capture_path)


def ensure_dsp_prerequisites(config: "AudioConfig"):
    """DSP モードの前提条件をチェック。"""
    if config.mode != "dsp":
        return
    if not has_loopback_capture_device():
        raise HTTPException(
            status_code=503,
            detail="ALSA Loopback device is unavailable. Load snd-aloop and retry.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# プリセット管理
# ─────────────────────────────────────────────────────────────────────────────
def load_presets() -> dict:
    """プリセット一覧を読み込み。"""
    try:
        with open(PRESETS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_presets(presets: dict):
    """プリセットを永続化。"""
    os.makedirs(os.path.dirname(PRESETS_PATH), exist_ok=True)
    with open(PRESETS_PATH, "w") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)
