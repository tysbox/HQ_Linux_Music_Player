"""DSP 読み取り専用ルータ（Phase 3a-5: Task 1）.

backend/main.py から以下を移植（**GET のみ**、副作用なし）:
- GET /api/config       - 永続化 DSP 設定
- GET /api/presets      - プリセット一覧
- GET /api/art          - アルバムアート（iTunes リダイレクト + キャッシュ）

注:
- POST /api/apply, /api/presets/save, /api/dsp_restart, /api/volume は
  副作用があるため Phase 3c 後に追加移植する
- これらは読み取り系なので hq_api に追加しても既存 DSP:8000 に影響なし
"""
import json
import os
import hashlib
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter()

# 設定管理は backend.dsp.state_manager に一本化（Stage 1-4）
from backend.dsp.state_manager import (
    load_last_config as _load_last_config,
    load_presets as _load_presets,
    save_presets as _save_presets,
)

# アルバムアートキャッシュ設定
ART_CACHE_DIR = os.path.expanduser("~/.cache/audiophile/art")
ART_CACHE_TTL = 30 * 24 * 3600  # 30日
os.makedirs(ART_CACHE_DIR, exist_ok=True)


def _art_cache_key(artist: str, album: str) -> str:
    """アーティスト+アルバムからキャッシュキーを生成."""
    raw = f"{artist.lower().strip()}|{album.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_cached_art(artist: str, album: str) -> str | None:
    """キャッシュから iTunes リダイレクト URL を取得."""
    key = _art_cache_key(artist, album)
    cache_file = os.path.join(ART_CACHE_DIR, f"{key}.json")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file) as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) > ART_CACHE_TTL:
            return None
        return data.get("redirect_url")
    except Exception:
        return None


def _save_cached_art(artist: str, album: str, redirect_url: str):
    """iTunes リダイレクト URL をキャッシュに保存."""
    key = _art_cache_key(artist, album)
    cache_file = os.path.join(ART_CACHE_DIR, f"{key}.json")
    try:
        with open(cache_file, "w") as f:
            json.dump({"redirect_url": redirect_url, "timestamp": time.time()}, f)
    except Exception:
        pass


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
    """アルバムアート取得。DSP:8000 と完全互換（Phase X-1 + キャッシュ対応）.

    優先順位:
    1. ローカルファイル（Folder.jpg / cover.jpg）
    2. MPD readpicture / albumart
    3. iTunes Search API（キャッシュ優先、なければ requests.get で取得）
    4. SVG プレースホルダ
    """
    from hqmplayer_core.art import resolve_art
    from hqmplayer_core.mpd import mpd_connection
    import requests

    async def _mpd_readpicture(uri):
        async with mpd_connection() as c:
            try:
                return await c.readpicture(uri)
            except Exception:
                return None

    async def _mpd_albumart(uri):
        async with mpd_connection() as c:
            try:
                return await c.albumart(uri)
            except Exception:
                return None

    # キャッシュから iTunes リダイレクト URL を確認（artist/album がある場合のみ）
    if artist and album:
        cached_url = _get_cached_art(artist, album)
        if cached_url:
            return RedirectResponse(url=cached_url, status_code=307)

    result = await resolve_art(
        file=file,
        artist=artist,
        album=album,
        mpd_readpicture=_mpd_readpicture,
        mpd_albumart=_mpd_albumart,
        http_get=requests.get,  # Phase X-1: iTunes フォールバック有効化
    )
    if result.source == "itunes" and result.redirect_url:
        # キャッシュに保存
        if artist and album:
            _save_cached_art(artist, album, result.redirect_url)
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


# ─────────────────────────────────────────────────────────────────────────────
# プリセット保存・削除（Phase 3: backend/main.py から移植）
# ─────────────────────────────────────────────────────────────────────────────
class PresetSave(BaseModel):
    name: str
    config: dict


@router.post("/api/presets/save")
def save_preset(body: PresetSave):
    """DSP:8000 と完全互換のプリセット保存."""
    if not body.name.strip():
        return {"status": "error", "message": "名前を入力してください"}
    presets = _load_presets()
    presets[body.name.strip()] = body.config
    _save_presets(presets)
    return {"status": "success", "presets": presets}


@router.delete("/api/presets/{name}")
def delete_preset(name: str):
    """DSP:8000 と完全互換のプリセット削除."""
    presets = _load_presets()
    if name in presets:
        del presets[name]
        _save_presets(presets)
    return {"status": "success", "presets": presets}


# ─────────────────────────────────────────────────────────────────────────────
# プロファイル API（Stage 3-4）
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dsp/profiles")
def list_dsp_profiles():
    """プロファイル一覧取得（Stage 3-4: 機器補正プロファイル）.

    Returns:
        list[dict]: プロファイル概要リスト (id, name, type, source, purpose)
    """
    from backend.dsp.profiles import list_profiles
    return list_profiles()


@router.get("/api/dsp/profiles/{profile_id}")
def get_dsp_profile(profile_id: str):
    """プロファイル詳細取得.

    Args:
        profile_id: プロファイル ID

    Returns:
        プロファイル全体、存在しない場合は 404
    """
    from backend.dsp.profiles import load_profile
    from fastapi import HTTPException
    profile = load_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    return profile
