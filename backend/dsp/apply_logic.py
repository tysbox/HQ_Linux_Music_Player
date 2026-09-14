"""DSP 適用ロジックモジュール（D-2 分離）.

backend/main.py から音量初期化・DSP再起動・設定適用フローを移植。
FastAPI 等の Web フレームワーク非依存（純粋ロジック）。
"""

import os
import subprocess
import threading
import time
from typing import Optional

from camilladsp import CamillaClient

# ─────────────────────────────────────────────────────────────────────────────
# 定数定義
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SWITCH_AUDIO_SCRIPT = os.path.join(BASE_DIR, "..", "scripts", "switch_audio.sh")


# ─────────────────────────────────────────────────────────────────────────────
# クロスフィード・クロストーク打ち消しパラメータ計算（既存実装を活用）
# ─────────────────────────────────────────────────────────────────────────────
CROSSFEED_ANGLE_PARAMS = {
    "none": {"delay_ms": 0.0, "gain_db": 0.0, "label": "OFF"},
    "15": {"delay_ms": 0.11, "gain_db": -3.0, "label": "15°"},
    "30": {"delay_ms": 0.22, "gain_db": -6.0, "label": "30°"},
    "60": {"delay_ms": 0.44, "gain_db": -10.0, "label": "60°"},
    "90": {"delay_ms": 0.66, "gain_db": -14.0, "label": "90°"},
}

DISTANCE_PARAMS = {
    0.0: {"label": "0.5m (ニア)", "delay_ms": 1.5, "gain_db": -2.0},
    0.5: {"label": "3m (中間)", "delay_ms": 8.7, "gain_db": -8.0},
    1.0: {"label": "20m (ファー)", "delay_ms": 58.0, "gain_db": -20.0},
}

# クロストーク打ち消し（外部スピーカー用）— 逆位相の混合を加えて打ち消し
# 角度に応じたパラメータ（クロスフィードと同じ角度キーを使用）
CROSSTALK_CANCEL_PARAMS = {
    "none": {"delay_ms": 0.0,  "gain_db": 0.0,  "label": "OFF", "inverted": False},
    "15":  {"delay_ms": 0.11, "gain_db": -3.0,  "label": "15°", "inverted": True},
    "30":  {"delay_ms": 0.22, "gain_db": -6.0,  "label": "30°", "inverted": True},
    "60":  {"delay_ms": 0.44, "gain_db": -10.0, "label": "60°", "inverted": True},
    "90":  {"delay_ms": 0.66, "gain_db": -14.0, "label": "90°", "inverted": True},
}


def compute_crossfeed_params(angle: str, intensity: int = 50) -> dict:
    base = CROSSFEED_ANGLE_PARAMS.get(angle, CROSSFEED_ANGLE_PARAMS["none"])
    intensity_pct = max(0.0, min(1.0, intensity / 100.0))
    gain_db = round(base["gain_db"] * intensity_pct, 1)
    delay_ms = round(base["delay_ms"] * intensity_pct, 2)
    return {"delay_ms": delay_ms, "gain_db": gain_db, "label": base["label"]}


def compute_distance_params(distance_ratio: float) -> dict:
    if distance_ratio <= 0.5:
        t = distance_ratio / 0.5
        delay_ms = 1.5 + (8.7 - 1.5) * t
        gain_db = -2.0 + (-8.0 - (-2.0)) * t
    else:
        t = (distance_ratio - 0.5) / 0.5
        delay_ms = 8.7 + (58.0 - 8.7) * t
        gain_db = -8.0 + (-20.0 - (-8.0)) * t
    if distance_ratio < 0.25:
        label = "0.5m (ニアフィールド)"
    elif distance_ratio < 0.75:
        label = "3m (リスニングポジション)"
    else:
        label = "20m (ファーフィールド)"
    return {"label": label, "delay_ms": round(delay_ms, 2), "gain_db": round(gain_db, 1)}


def apply_crossfeed(config) -> dict:
    params = compute_crossfeed_params(config.crossfeed, config.crossfeed_intensity)
    return {
        "status": "crossfeed_applied",
        "angle": config.crossfeed,
        "intensity": config.crossfeed_intensity,
        "delay_ms": params["delay_ms"],
        "gain_db": params["gain_db"],
        "label": params["label"],
    }


def apply_crosstalk_cancel(config) -> dict:
    """クロストーク打ち消しを適用（外部スピーカー用、逆位相混合）。

    原理: スピーカーでは左→右と右→左の自然な混合（ITD + ILD）が発生。
    クロストーク打ち消しは、この自然な混合を逆位相で打ち消すことで、
    ヘッドホンでもスピーカーのような定位を再現する。
    """
    params = CROSSTALK_CANCEL_PARAMS.get(config.crossfeed, CROSSTALK_CANCEL_PARAMS["none"])
    # クロストーク打ち消しは、クロスフィードと逆の処理（逆位相の混合を加える）
    # ただし、現在の DSP 構造ではクロスフィードと同じ Mixer で処理されるため、
    # クロスフィードのパラメータを逆位相（inverted: True）で適用することで打ち消しを実現
    return {
        "status": "crosstalk_cancel_applied",
        "intensity": config.crossfeed_intensity,
        "delay_ms": params["delay_ms"],
        "gain_db": params["gain_db"],
        "label": params["label"],
        "inverted": True,  # 逆位相で打ち消し
    }


# ─────────────────────────────────────────────────────────────────────────────
# 音量初期化・スケジューリング
# ─────────────────────────────────────────────────────────────────────────────
def init_vol(v: float):
    """CamillaDSP への接続を試行し、確立でき次第 main_volume を設定する。

    CamillaDSP を `-s/--statefile` 付きで起動した場合、起動時に statefile から
    main_volume が自動復元されるため、Python 側で fade-in 等の複雑な処理は不要。
    """
    for _ in range(200):  # 最大 10 秒待機
        time.sleep(0.05)
        try:
            c = CamillaClient("127.0.0.1", 1234)
            c.connect()
            c.volume.set_main_volume(v)
            c.disconnect()
            return
        except Exception:
            pass


def schedule_init_vol(v: float):
    """init_vol をバックグラウンドスレッドで実行."""
    thread = threading.Thread(target=init_vol, args=(v,), daemon=True)
    thread.start()


# ─────────────────────────────────────────────────────────────────────────────
# DSP 再起動・設定適用フロー
# ─────────────────────────────────────────────────────────────────────────────
def restart_dsp(config, generate_yaml_func, normalize_func, ensure_prereqs_func, save_config_func) -> dict:
    """DSP 再起動フロー（/api/dsp_restart 相当）。

    Args:
        config: AudioConfig オブジェクト
        generate_yaml_func: generate_camilladsp_yaml 関数
        normalize_func: normalize_config_for_device 関数
        ensure_prereqs_func: ensure_dsp_prerequisites 関数
        save_config_func: save_last_config 関数

    Returns:
        dict: {"status": "success", ...} または {"status": "error", ...}
    """
    try:
        normalized = normalize_func(config)
        ensure_prereqs_func(normalized)
        yp = generate_yaml_func(normalized)
        result = subprocess.run(
            ["bash", SWITCH_AUDIO_SCRIPT, "dsp", normalized.device, yp],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "message": "switch_audio failed",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        schedule_init_vol(normalized.volume)
        save_config_func(normalized.model_dump())
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def apply_audio(config, generate_yaml_func, normalize_func, ensure_prereqs_func,
                config_requires_restart_func, load_last_config_func, save_config_func) -> dict:
    """DSP 設定適用フロー（/api/apply 相当）。

    Args:
        config: AudioConfig オブジェクト
        generate_yaml_func: generate_camilladsp_yaml 関数
        normalize_func: normalize_config_for_device 関数
        ensure_prereqs_func: ensure_dsp_prerequisites 関数
        config_requires_restart_func: config_requires_restart 関数
        load_last_config_func: load_last_config 関数
        save_config_func: save_last_config 関数

    Returns:
        dict: {"status": "success"} または {"status": "error", "message": ...}
    """
    # volume 強制復帰: config.volume の値に関わらず、last_config.volume を必ず採用
    try:
        last_cfg = load_last_config_func()
    except Exception:
        last_cfg = None
    if last_cfg and "volume" in last_cfg:
        try:
            last_vol = float(last_cfg["volume"])
            config = config.model_copy(update={"volume": last_vol})
        except Exception:
            pass

    try:
        requested_mode = config.mode
        last_config = load_last_config_func()
        config = normalize_func(config, requested_mode=requested_mode)
        ensure_prereqs_func(config)
        needs_restart = config_requires_restart_func(config, last_config)

        if config.mode == "dsp":
            # Phase 2-A: DSP の稼働状態を最初に確認。
            # HANDOVER0907 §3 根治: needs_restart=False でも DSP が未起動なら起動する。
            try:
                _check = CamillaClient("127.0.0.1", 1234)
                _check.connect()
                _current_vol = float(_check.volume.main_volume())
                _check.disconnect()
            except Exception:
                _current_vol = None  # DSP 未起動
            _dsp_running = _current_vol is not None

            # Phase 2-D: needs_restart=False かつ DSP 稼働中 の場合でも、
            # main_volume=0.0 (= DSP 音量未設定異常) のときは last_config.volume を
            # 再適用して「Apply後に音量が変わる/Apply前に戻らない」症状を防ぐ。
            # 通常時 (main_volume != 0.0) は何もしない (音量・モード維持)。
            if needs_restart or not _dsp_running:
                yp = generate_yaml_func(config)
                subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, config.mode, config.device, yp])
                if not _dsp_running or _current_vol == 0.0:
                    schedule_init_vol(config.volume)
            elif _current_vol == 0.0:
                # Phase 2-D: DSP 稼働中で main_volume=0.0 のときだけ volume を再適用
                schedule_init_vol(config.volume)
            # needs_restart=False かつ DSP 稼働中かつ main_volume != 0.0 の場合は何もしない
        else:
            if needs_restart:
                subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, config.mode, config.device, "none"])

        save_config_func(config.model_dump())
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_dsp_params(params, last_config, generate_yaml_func, normalize_func) -> dict:
    """DSP パラメータのみ更新フロー（/api/dsp_update 相当）。

    ALSA Loopback / MPD output は変更せず、CamillaDSP の YAML のみ更新して
    ホットリロードする。音は途切れない。

    Args:
        params: DspParams オブジェクト (music_type, eq_output, crossfeed, 等)
        last_config: 既存の last_config dict
        generate_yaml_func: generate_camilladsp_yaml 関数
        normalize_func: normalize_config_for_device 関数

    Returns:
        dict: {"status": "success", "path": ...} または {"status": "error", "message": ...}
    """
    try:
        # 既存 last_config に dial 値のみマージ
        merged = {
            **last_config,
            "music_type": params.music_type,
            "eq_output": params.eq_output,
            "crossfeed": params.crossfeed,
            "crossfeed_intensity": params.crossfeed_intensity,
            "hum_noise": params.hum_noise,
            "reverb": params.reverb,
            "reverb_intensity": params.reverb_intensity,
        }
        # mode / device / volume は変えない
        merged_mode = merged.get("mode", "dsp")
        merged_device = merged.get("device", "none")
        merged_volume = float(merged.get("volume", -8.0))

        # YAML 再生成
        from backend.main import AudioConfig as BackendAudioConfig
        full_cfg = BackendAudioConfig(
            mode=merged_mode,
            device=merged_device,
            volume=merged_volume,
            music_type=params.music_type,
            eq_output=params.eq_output,
            crossfeed=params.crossfeed,
            crossfeed_intensity=params.crossfeed_intensity,
            hum_noise=params.hum_noise,
            reverb=params.reverb,
            reverb_intensity=params.reverb_intensity,
        )
        normalized = normalize_func(full_cfg, requested_mode=merged_mode)
        yp = generate_yaml_func(normalized)

        # ファイルを書き換えて、CamillaDSP に ConfigReload を送信
        with open(yp, "w") as f:
            f.write(generate_yaml_func(normalized))

        return {"status": "success", "path": yp}
    except Exception as e:
        return {"status": "error", "message": str(e)}
