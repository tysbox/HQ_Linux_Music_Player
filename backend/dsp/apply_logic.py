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


_APPLY_INFLIGHT: dict | None = None
_APPLY_LOCK = threading.Lock()


def apply_audio(config, generate_yaml_func, normalize_func, ensure_prereqs_func,
                config_requires_restart_func, load_last_config_func, save_config_func) -> dict:
    """DSP 設定適用フロー（/api/apply 相当）。

    同一設定の連続 Apply は合体し、CamillaDSP 再起動は1回だけにする。
    06:52 のような「同一秒に4つの switch_audio.sh が並走し、起動直後の
    CamillaDSP を kill し合って underrun の嵐になる」事象の再発防止。

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
    global _APPLY_INFLIGHT
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

        # 同一設定の連続 Apply は合体 (DSP 再起動の嵐を防止)。
        # needs_restart=False なら何もしないので即 return。
        if not needs_restart:
            save_config_func(config.model_dump())
            return {"status": "success", "restarted": False, "applied": True}
        with _APPLY_LOCK:
            if _APPLY_INFLIGHT == config.model_dump():
                return {"status": "success", "restarted": False, "deduped": True, "applied": True}
            _APPLY_INFLIGHT = config.model_dump()

        try:
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
            with _APPLY_LOCK:
                _APPLY_INFLIGHT = None
            return {"status": "success", "restarted": needs_restart, "applied": True}
        except Exception as e:
            with _APPLY_LOCK:
                _APPLY_INFLIGHT = None
            return {"status": "error", "message": str(e), "applied": False}
    except Exception as e:
        return {"status": "error", "message": str(e), "applied": False}
