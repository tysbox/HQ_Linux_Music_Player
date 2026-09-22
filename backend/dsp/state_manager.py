"""DSP 状態管理モジュール（D-2 分離）.

backend/main.py から設定永続化・正規化・前提条件チェックを移植。
FastAPI 等の Web フレームワーク非依存（純粋ロジック）。
"""

import json
import os
import re
import shutil
import subprocess
import time
from typing import Optional

from fastapi import HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# 定数定義 (移植対応: 環境変数で上書き可能、既定値は従来通り)
# AUDIOPHILE_CONFIG_DIR > XDG_CONFIG_HOME > ~/.config の順で解決する。
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_config_dir() -> str:
    override = os.getenv("AUDIOPHILE_CONFIG_DIR", "").strip()
    if override:
        return override
    xdg = os.getenv("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return os.path.join(xdg, "audiophile")
    return os.path.expanduser("~/.config/audiophile")


_CONFIG_DIR = _resolve_config_dir()
LAST_CONFIG_PATH = os.getenv("AUDIOPHILE_LAST_CONFIG", os.path.join(_CONFIG_DIR, "last_config.json"))
PRESETS_PATH = os.getenv("AUDIOPHILE_PRESETS", os.path.join(_CONFIG_DIR, "presets.json"))


def _atomic_write_json(path: str, obj: dict, **dump_kwargs):
    """クラッシュ時の0バイト化を防ぐ tmp+fsync+os.replace 書き込み。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(obj, f, **dump_kwargs)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


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
    """設定を永続化 (アトミック置換)。"""
    _atomic_write_json(LAST_CONFIG_PATH, config_dict)


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


# ─────────────────────────────────────────────────────────────────────────────
# 出力デバイス実在チェック (移植対応: BT/USB/PCH の有無で事前に明確なエラーを返す)
# ─────────────────────────────────────────────────────────────────────────────
_DEVICE_PROBE_CACHE: dict[str, tuple[float, bool]] = {}


def _probe_ttl() -> float:
    try:
        return float(os.getenv("HQ_DEVICE_PROBE_TTL", "30"))
    except ValueError:
        return 30.0


def _aplay_listing() -> str | None:
    """`aplay -L` の出力を取得。aplay 不在/失敗時は None (= 判定不能)。"""
    if shutil.which("aplay") is None:
        return None
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        res = subprocess.run(["aplay", "-L"], capture_output=True, text=True, env=env, timeout=5)
        return res.stdout or ""
    except Exception:
        return None


def _bt_pcm_paths() -> list[str] | None:
    """BlueALSA が公開している PCM パスの一覧を返す。判定不能時は None。

    1) bluealsa-cli list-pcms : D-Bus 経由で最も正確 (接続デバイスのみ現れる)
    2) aplay -L の bluealsa:DEV=.. 行 : CLI 不在時のフォールバック
    """
    if shutil.which("bluealsa-cli"):
        try:
            env = os.environ.copy()
            env["LC_ALL"] = "C"
            res = subprocess.run(
                ["bluealsa-cli", "list-pcms"], capture_output=True, text=True, env=env, timeout=5
            )
            if res.returncode == 0:
                return [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
        except Exception:
            pass
    listing = _aplay_listing()
    if listing is None:
        return None
    return [ln.strip() for ln in listing.splitlines() if "bluealsa:DEV=" in ln]


def bluetooth_sink_available() -> bool:
    """BlueALSA (A2DP) 出力が利用可能か判定する。

    接続済み BT オーディオ機器の PCM (a2dp) が存在するかを確認する。
    プラグイン導入済みでも機器未接続なら False を返すため、
    「BT 未接続なのに CamillaDSP が即死する」事象を事前に説明できる。
    判定不能 (bluealsa-cli/aplay 不在) の場合は True を返し、
    呼び出し側の既存挙動を変えない。
    """
    key = "__bluealsa__"
    ttl = _probe_ttl()
    now = time.monotonic()
    cached = _DEVICE_PROBE_CACHE.get(key)
    if cached is not None and (now - cached[0]) < ttl:
        return cached[1]
    paths = _bt_pcm_paths()
    if paths is None:
        return True  # 判定不能 → ブロックしない
    if not paths:
        # bluealsa-cli は動いたが PCM が無い = 未接続 (もしくは aplay -L に DEV= が無い)
        # aplay -L にプラグイン自体が無ければ「BT 非対応環境」としてブロックしない
        listing = _aplay_listing()
        if listing is not None and "bluealsa" not in listing:
            return True
        available = False
    else:
        available = any("a2dp" in p for p in paths)
    _DEVICE_PROBE_CACHE[key] = (now, available)
    return available


def output_device_available(device: str) -> bool:
    """指定出力デバイスが現在利用可能か判定する。

    - bluealsa : BT 接続状態に依存 (bluetooth_sink_available)
    - hw:N,0 / plughw:N,0 : /proc/asound/cards に該当カード番号が存在するか
    - それ以外 (plug:*, pipe:*, 等) : 判定不能のため True
    """
    if not device:
        return True
    if "bluealsa" in device:
        return bluetooth_sink_available()
    m = re.search(r"(?:^|:)(?:plughw|hw):(\d+),\d+", device)
    if not m:
        return True
    card_no = m.group(1)
    key = f"__card_{card_no}__"
    ttl = _probe_ttl()
    now = time.monotonic()
    cached = _DEVICE_PROBE_CACHE.get(key)
    if cached is not None and (now - cached[0]) < ttl:
        return cached[1]
    if _aplay_listing() is None:
        return True
    available = False
    try:
        # 1) /proc/asound/cards (言語非依存)。"N [Name ]: ..." 形式
        if os.path.exists("/proc/asound/cards"):
            with open("/proc/asound/cards", encoding="utf-8", errors="replace") as f:
                cards_text = f.read()
            available = any(
                line.strip().startswith(f"{card_no} [") for line in cards_text.splitlines()
            )
        # 2) フォールバック: aplay -l (LC_ALL=C 固定)
        if not available:
            env = os.environ.copy()
            env["LC_ALL"] = "C"
            res = subprocess.run(["aplay", "-l"], capture_output=True, text=True, env=env, timeout=5)
            available = any(
                (f"card {card_no}:" in line) or (f"カード {card_no}:" in line)
                for line in (res.stdout or "").splitlines()
            )
    except Exception:
        return True  # 判定不能 → ブロックしない
    _DEVICE_PROBE_CACHE[key] = (now, available)
    return available


def device_unavailability_reason(device: str) -> str | None:
    """未使用デバイスの場合に、利用者向けの説明文を返す (利用可能なら None)。"""
    if output_device_available(device):
        return None
    if "bluealsa" in device:
        return (
            "Bluetooth (A2DP) 出力デバイスが見つかりません。"
            "BT スピーカー/ヘッドホンを接続してから再実行するか、"
            "出力先を PC Speaker / USB DAC に変更してください。"
        )
    return (
        f"指定された出力デバイス '{device}' が見つかりません。"
        "デバイス番号を確認するか、利用可能なデバイスを選択してください。"
    )


def ensure_dsp_prerequisites(config: "AudioConfig"):
    """DSP モードの前提条件をチェック。"""
    if config.mode != "dsp":
        return
    if not has_loopback_capture_device():
        raise HTTPException(
            status_code=503,
            detail="ALSA Loopback device is unavailable. Load snd-aloop and retry.",
        )
    # 出力デバイス実在チェック (移植対応): CamillaDSP 即死ではなく明確なエラーを返す
    if getattr(config, "device", None):
        reason = device_unavailability_reason(config.device)
        if reason:
            raise HTTPException(status_code=503, detail=reason)


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
    """プリセットを永続化 (アトミック置換)。"""
    _atomic_write_json(PRESETS_PATH, presets, ensure_ascii=False, indent=2)
