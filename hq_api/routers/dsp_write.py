"""DSP 書き込み系ルータ（Phase X-3: 段階的移植）.

backend/dsp.* モジュールから関数を import して使用。リスクの低い順に:

1. POST /api/presets/save  ← ファイル I/O のみ ✅ X-3-1
2. POST /api/presets/{name} (DELETE)  ← ファイル I/O のみ ✅ X-3-1
3. POST /api/volume  ← CamillaClient 接続（中リスク）✅ X-3-2
"""
import json
import os
import time

from fastapi import APIRouter
from pydantic import BaseModel

from hqmplayer_core.mpd import mpd_connection
from backend.dsp.state_manager import (
    load_presets,
    save_presets,
    load_last_config,
    save_last_config,
    PRESETS_PATH,
    LAST_CONFIG_PATH,
)
from backend.dsp.apply_logic import (
    init_vol,
    schedule_init_vol,
    SWITCH_AUDIO_SCRIPT,
)
from hq_api.errors import service_unavailable, unprocessable_entity

router = APIRouter()


class PresetSave(BaseModel):
    name: str
    config: dict


@router.post("/api/presets/save")
def save_preset(body: PresetSave):
    """DSP:8000 と完全互換のプリセット保存."""
    if not body.name.strip():
        raise unprocessable_entity("名前を入力してください")
    presets = load_presets()
    presets[body.name.strip()] = body.config
    save_presets(presets)
    return {"status": "success", "presets": presets}


@router.delete("/api/presets/{name}")
def delete_preset(name: str):
    """DSP:8000 と完全互換のプリセット削除."""
    presets = load_presets()
    if name in presets:
        del presets[name]
        save_presets(presets)
    return {"status": "success", "presets": presets}


# ─────────────────────────────────────────────────────────────────────────────
# Phase X-3-2: CamillaClient 経由（中リスク）
# ─────────────────────────────────────────────────────────────────────────────
class VolumeControl(BaseModel):
    volume: float


@router.post("/api/volume")
def set_volume(vol: VolumeControl):
    """DSP:8000 と完全互換のボリューム設定.

    CamillaDSP のメイン音量を即座に変更。再生は途切れない。
    CamillaDSP 未起動時は最大 200 回 (各 50ms、計 10 秒) リトライして起動を待機。

    2026-09-06 課題 2: DSP_LOCK で /api/apply /api/dsp_update と同時実行を直列化。
    2026-09-15 追加: init_vol と同様の起動待機ロジックを追加 (P1-3 対策)。
    """
    from hq_api.main import DSP_LOCK
    with DSP_LOCK:
        import os as _os
        try:
            _retries = int(_os.getenv("CAMILLA_VOLUME_RETRIES", "40"))
        except ValueError:
            _retries = 40
        try:
            _interval = float(_os.getenv("CAMILLA_VOLUME_INTERVAL", "0.05"))
        except ValueError:
            _interval = 0.05
        _retries = max(1, min(_retries, 200))
        _host = _os.getenv("CAMILLA_HOST", "127.0.0.1")
        try:
            _port = int(_os.getenv("CAMILLA_PORT", "1234"))
        except ValueError:
            _port = 1234
        last_err: Exception | None = None
        # 起動待機リトライ (既定 40回 x 50ms = 2秒、移植時は env で調整)
        for attempt in range(_retries):
            try:
                from camilladsp import CamillaClient
                c = CamillaClient(_host, _port)
                c.connect()
                c.volume.set_main_volume(vol.volume)
                c.disconnect()
                # last_config.volume を更新 (DSP:8000 /api/volume と同じ挙動)。
                # HANDOVER0907 §3 の「Apply時に直前の音量に戻る」仕様を維持するため
                # ユーザー指定音量を永続化する。
                try:
                    cfg_data = load_last_config()
                    cfg_data["volume"] = float(vol.volume)
                    save_last_config(cfg_data)
                except Exception:
                    pass
                return {"status": "success", "attempts": attempt + 1}
            except Exception as e:
                last_err = e
                time.sleep(_interval)
        # 最終失敗 — 503 で返却 (CamillaDSP 未起動は 422 より 503 が適切)
        raise service_unavailable(f"CamillaDSP unreachable after {_retries} retries: {last_err}")


# Phase 2-A: 旧ローカル再実装は backend/main.py に一本化されたため削除済み。
