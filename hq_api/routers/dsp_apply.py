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

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
        _dsp_main._schedule_init_vol(normalized.volume, fade_in=True, wait_for_restart=True)
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
    """
    if not _HAS_BACKEND:
        raise HTTPException(
            status_code=503,
            detail=f"backend.main を import できません: {_IMPORT_ERROR}",
        )
    try:
        requested_mode = config.mode
        last_config = _dsp_main._load_last_config() if os.path.exists(_dsp_main.LAST_CONFIG_PATH) else None
        config = _dsp_main._normalize_config_for_device(config, requested_mode=requested_mode)
        _dsp_main._ensure_dsp_prerequisites(config)
        needs_restart = _dsp_main._config_requires_restart(config, last_config)
        if config.mode == "dsp":
            saved_volume = float(last_config.get("volume", config.volume)) if last_config else config.volume
            config = AudioConfig(**{**config.model_dump(), "volume": saved_volume})
            if needs_restart:
                yp = _dsp_main.generate_camilladsp_yaml(config)
                import subprocess
                subprocess.Popen(["bash", _dsp_main.SWITCH_AUDIO_SCRIPT, config.mode, config.device, yp])
                _dsp_main._schedule_init_vol(config.volume, fade_in=True, wait_for_restart=True)
            else:
                _dsp_main._schedule_init_vol(config.volume)
        else:
            if needs_restart:
                import subprocess
                subprocess.Popen(["bash", _dsp_main.SWITCH_AUDIO_SCRIPT, config.mode, config.device, "none"])
        _dsp_main._save_last_config(config.model_dump())
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})
