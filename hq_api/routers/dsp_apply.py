"""DSP 設定適用ルータ（Phase X-3-3）.

backend/main.py の以下の関数を hq_api に移植:
- POST /api/dsp_restart
- POST /api/apply

注:
- DSP 固有機能（CamillaDSP / ALSA Loopback / switch_audio.sh）に直接作用
- 実行すると CamillaDSP が再起動され、再生が瞬間的に途切れる
- 慎重に利用すること

実装方針:
- YAML 生成ロジックは backend/main.py に存在するため、import して re-use
- 副作用（subprocess / ファイル書き込み）は backend 側関数を呼ぶ
"""
import os
import sys
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# backend ディレクトリを sys.path に追加（backend.main を import するため）
_BACKEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "backend"
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# backend.main から必要関数を import（副作用関数を re-use）
try:
    import backend.main as _dsp_main  # noqa: E402
    _HAS_BACKEND = True
except Exception as _e:
    _HAS_BACKEND = False
    _IMPORT_ERROR = str(_e)

router = APIRouter()


class AudioConfig(BaseModel):
    """DSP 設定の Pydantic モデル（backend.main.AudioConfig と同一）."""
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


@router.post("/api/dsp_restart")
def restart_dsp(cfg: AudioConfig):
    """DSP:8000 と完全互換の CamillaDSP 再起動.

    副作用: CamillaDSP プロセスの再起動（数秒間再生停止の可能性）
    """
    if not _HAS_BACKEND:
        raise HTTPException(
            status_code=503,
            detail=f"backend.main を import できません: {_IMPORT_ERROR}",
        )
    try:
        normalized = _dsp_main._normalize_config_for_device(cfg)
        _dsp_main._ensure_dsp_prerequisites(normalized)
        yp = _dsp_main.generate_camilladsp_yaml(normalized)
        import subprocess
        result = subprocess.run(
            ["bash", _dsp_main.SWITCH_AUDIO_SCRIPT, "dsp", normalized.device, yp],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return JSONResponse(
                status_code=422,
                content={
                    "status": "error",
                    "message": "switch_audio failed",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
        _dsp_main._schedule_init_vol(normalized.volume, fade_in=True)
        _dsp_main._save_last_config(normalized.model_dump())
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})


@router.post("/api/apply")
def apply_audio(config: AudioConfig, bt: BackgroundTasks):
    """DSP:8000 と完全互換の DSP 設定適用.

    副作用:
    - 必要に応じて CamillaDSP / ALSA Loopback を再起動
    - ~/.config/audiophile/last_config.json を更新
    - ボリューム fade-in

    2026-09-06 課題 2: DSP_LOCK で /api/dsp_update /api/volume と同時実行を直列化。
    2026-09-06 課題 3: volume 強制復帰。
    ユーザー指示: "Apply ボタンでエフェクト変更後、再起動や生成ファイル変更で
    プレイ開始時は Vol 位置に関係なく (-8 であろうと -20 であろうと) 直前の音量に戻る"
    → config.volume の値に関わらず、last_config.volume を必ず採用する。
    効果: 起動時 / Apply / デバイス切替 / DSP 再生成 / ALSA 切替のいずれでも
    直前の音量で再生開始される (ダイヤル位置と無関係)。
    """
    from hq_api.main import DSP_LOCK
    if not _HAS_BACKEND:
        raise HTTPException(
            status_code=503,
            detail=f"backend.main を import できません: {_IMPORT_ERROR}",
        )
    with DSP_LOCK:
        # 2026-09-06 課題 3: volume 強制復帰 (最優先)
        # config.volume の値に関わらず、last_config.volume を必ず採用する。
        # ユーザーが /api/volume で設定した値 (= last_config.volume) を真の現在音量とする。
        try:
            last_cfg = _dsp_main._load_last_config() if os.path.exists(_dsp_main.LAST_CONFIG_PATH) else None
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
            last_config = _dsp_main._load_last_config() if os.path.exists(_dsp_main.LAST_CONFIG_PATH) else None
            config = _dsp_main._normalize_config_for_device(config, requested_mode=requested_mode)
            _dsp_main._ensure_dsp_prerequisites(config)
            needs_restart = _dsp_main._config_requires_restart(config, last_config)
            if config.mode == "dsp":
                # Phase 2-A: DSP の稼働状態を最初に確認。
                # HANDOVER0907 §3 根治: needs_restart=False でも DSP が未起動なら起動する。
                try:
                    from camilladsp import CamillaClient
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
                    yp = _dsp_main.generate_camilladsp_yaml(config)
                    import subprocess
                    subprocess.Popen(["bash", _dsp_main.SWITCH_AUDIO_SCRIPT, config.mode, config.device, yp])
                    if not _dsp_running or _current_vol == 0.0:
                        _dsp_main._schedule_init_vol(config.volume, fade_in=True)
                elif _current_vol == 0.0:
                    # Phase 2-D: DSP 稼働中で main_volume=0.0 のときだけ volume を再適用
                    _dsp_main._schedule_init_vol(config.volume, fade_in=True)
                # needs_restart=False かつ DSP 稼働中かつ main_volume != 0.0 の場合は何もしない
            else:
                if needs_restart:
                    import subprocess
                    subprocess.Popen(["bash", _dsp_main.SWITCH_AUDIO_SCRIPT, config.mode, config.device, "none"])
            _dsp_main._save_last_config(config.model_dump())
            return {"status": "success"}
        except Exception as e:
            return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})


class DspParams(BaseModel):
    """DSP パラメータのみ更新 (ALSA 切替なし、停止なし)."""
    music_type: str = "none"
    eq_output: str = "none"
    crossfeed: str = "none"
    crossfeed_intensity: int = 5
    hum_noise: str = "none"
    reverb: str = "none"
    reverb_intensity: int = 5


@router.post("/api/dsp_update")
def update_dsp_params(params: DspParams):
    """DSP パラメータのみ更新 — CamillaDSP ホットリロード (停止/ポーズなし).

    ユーザー要件: ダイヤル変更 = ユーザーが意図した変更。
    ALSA Loopback / MPD output は変更せず、CamillaDSP の YAML のみ更新して
    ホットリロードする。音は途切れない。

    2026-09-06 課題 2: DSP_LOCK で /api/apply /api/volume と同時実行を直列化。
    """
    from hq_api.main import DSP_LOCK
    if not _HAS_BACKEND:
        raise HTTPException(
            status_code=503,
            detail=f"backend.main を import できません: {_IMPORT_ERROR}",
        )
    with DSP_LOCK:
        try:
            # 既存 last_config に dial 値のみマージ
            last = _dsp_main._load_last_config() if os.path.exists(_dsp_main.LAST_CONFIG_PATH) else {}
            merged = {
                **last,
                "music_type":   params.music_type,
                "eq_output":    params.eq_output,
                "crossfeed":    params.crossfeed,
                "crossfeed_intensity": params.crossfeed_intensity,
                "hum_noise":    params.hum_noise,
                "reverb":       params.reverb,
                "reverb_intensity": params.reverb_intensity,
            }
            # mode / device / volume は変えない
            merged_mode = merged.get("mode", "dsp")
            merged_device = merged.get("device", "none")
            merged_volume = float(merged.get("volume", -8.0))

            # YAML 再生成 (YAML は再生成するが、CamillaDSP の volume は触らない)
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
            normalized = _dsp_main._normalize_config_for_device(full_cfg, requested_mode=merged_mode)
            yp = _dsp_main.generate_camilladsp_yaml(normalized)

            # ファイルを書き換えて、CamillaDSP に ConfigReload を送信
            with open(yp, "w") as f:
                f.write(_dsp_main.generate_camilladsp_yaml(normalized))
            # 2 重書き込み防止: 同じ関数で書かれている
            # CamillaDSP にリロード指示 (127.0.0.1:1234 は CamillaClient)
            try:
                from camilladsp import CamillaClient
                c = CamillaClient("127.0.0.1", 1234)
                c.connect()
                try:
                    c.reload_config()  # ファイルから再読み込み
                except AttributeError:
                    # 古い camilladsp ライブラリは c.general.reload() を使う
                    c.general.reload()
                c.disconnect()
            except Exception as e:
                # CamillaDSP 未起動でも設定ファイルは更新しておく
                logger.warning("dsp_update: CamillaDSP reload failed: %s", e)

            # 設定保存 (dial 値のみ上書き、volume/mode/device は保持)
            _dsp_main._save_last_config(merged)
            return {"status": "success", "path": yp}
        except Exception as e:
            return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})
