"""DSP 読み取り専用ルータ（Phase 3a-5: Task 1）.

backend/main.py から以下を移植（**GET のみ**、副作用なし）:
- GET /api/config       - 永続化 DSP 設定
- GET /api/presets      - プリセット一覧
- GET /api/art          - アルバムアート（iTunes リダイレクト）

注:
- POST /api/apply, /api/presets/save, /api/dsp_restart, /api/volume は
  副作用があるため Phase 3c 後に追加移植する
- これらは読み取り系なので hq_api に追加しても既存 DSP:8000 に影響なし
"""
import json
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

router = APIRouter()

# 設定ファイルパス（DSP 側と共有）
LAST_CONFIG_PATH = os.path.expanduser("~/.config/audiophile/last_config.json")
PRESETS_PATH = os.path.expanduser("~/.config/audiophile/presets.json")


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


def _load_last_config() -> dict:
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


def _load_presets() -> dict:
    try:
        with open(PRESETS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


@router.get("/api/config")
def get_audio_config():
    """DSP:8000 と同一の JSON を返す（GET のみ）."""
    return _load_last_config()


@router.get("/api/presets")
def get_presets():
    """DSP:8000 と同一の JSON を返す（GET のみ）."""
    return _load_presets()


@router.get("/api/art")
async def get_art(
    file: str = Query(..., description="曲ファイルパス"),
    artist: str = Query("", description="アーティスト名"),
    album: str = Query("", description="アルバム名"),
):
    """アルバムアート取得。DSP:8000 と同一の挙動。

    優先順位:
    1. resolve_art() の iTunes フォールバック結果
    2. 解決できなければプレースホルダ

    注: hq_api では iTunes HTTP 取得を行わない（DSP 側機能）。
        http_get=None を渡すことで iTunes フォールバックをスキップする。
    """
    from hqmplayer_core.art import resolve_art

    result = await resolve_art(
        file=file,
        artist=artist,
        album=album,
        mpd_readpicture=None,
        mpd_albumart=None,
        http_get=None,  # iTunes フォールバック無効化
    )
    if result.redirect_url:
        return RedirectResponse(url=result.redirect_url, status_code=307)
    # バイナリコンテンツ or プレースホルダ
    from fastapi.responses import Response
    if result.content is not None:
        return Response(content=result.content, media_type=result.media_type or "image/jpeg")
    # フォールバック: 422 (DSP 側でも ?file 単体では 422 を返す)
    raise HTTPException(
        status_code=422,
        detail="file, artist, album の少なくとも 1 つと、MPD 接続 (DSP 側) が必要"
    )
