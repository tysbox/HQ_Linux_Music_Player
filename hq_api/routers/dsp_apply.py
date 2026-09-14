"""DSP 設定適用ルータ（Phase X-3-3）.

backend/dsp.* モジュールから関数を import して使用:
- POST /api/dsp_restart
- POST /api/apply
- POST /api/dsp_update

注:
- DSP 固有機能（CamillaDSP / ALSA Loopback / switch_audio.sh）に直接作用
- 実行すると CamillaDSP が再起動され、再生が瞬間的に途切れる
- 慎重に利用すること

実装方針:
- YAML 生成・状態管理・適用ロジックは backend.dsp.* から import
- 副作用（subprocess / ファイル書き込み）は backend.dsp 側関数を呼ぶ
"""
import os
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# backend.dsp モジュールから必要関数を import
from backend.dsp.yaml_generator import generate_camilladsp_yaml
from backend.dsp.state_manager import (
    load_last_config,
    save_last_config,
    config_requires_restart,
    normalize_config_for_device,
    ensure_dsp_prerequisites,
    LAST_CONFIG_PATH,
)
from backend.dsp.apply_logic import (
    restart_dsp as restart_dsp_impl,
    apply_audio as apply_audio_impl,
    update_dsp_params as update_dsp_params_impl,
    SWITCH_AUDIO_SCRIPT,
)

# AudioConfig は backend.main から import（Pydantic モデル定義のため）
from backend.main import AudioConfig

router = APIRouter()


@router.post("/api/dsp_restart")
def restart_dsp(cfg: AudioConfig):
    """DSP:8000 と完全互換の CamillaDSP 再起動.

    副作用: CamillaDSP プロセスの再起動（数秒間再生停止の可能性）
    """
    return restart_dsp_impl(
        cfg,
        generate_camilladsp_yaml,
        normalize_config_for_device,
        ensure_dsp_prerequisites,
        save_last_config,
    )


@router.post("/api/apply")
def apply_audio(config: AudioConfig):
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
    with DSP_LOCK:
        return apply_audio_impl(
            config,
            generate_camilladsp_yaml,
            normalize_config_for_device,
            ensure_dsp_prerequisites,
            config_requires_restart,
            load_last_config,
            save_last_config,
        )


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
    with DSP_LOCK:
        try:
            # 既存 last_config に dial 値のみマージ
            last = load_last_config()
            merged = {
                **last,
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
            normalized = normalize_config_for_device(full_cfg, requested_mode=merged_mode)
            yp = generate_camilladsp_yaml(normalized)

            # ファイルを書き換えて、CamillaDSP に ConfigReload を送信
            with open(yp, "w") as f:
                f.write(generate_camilladsp_yaml(normalized))
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
            save_last_config(merged)
            return {"status": "success", "path": yp}
        except Exception as e:
            return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})
