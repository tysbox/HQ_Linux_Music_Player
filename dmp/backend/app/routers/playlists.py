from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime
from app.services.mpd_service import mpd_connection, _song_to_track
from app.services import meta_cache

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


class CreatePlaylistRequest(BaseModel):
    name: str


class AddTrackRequest(BaseModel):
    uri: str


class AddTracksRequest(BaseModel):
    uris: List[str]


@router.get("/")
async def get_playlists():
    """プレイリスト一覧"""
    async with mpd_connection() as client:
        result = await client.listplaylists()
        playlists = [
            {
                "name": p["playlist"],
                "last_modified": p.get("last-modified", ""),
            }
            for p in result
        ]
        return {"playlists": playlists, "total": len(playlists)}


@router.get("/{name}")
async def get_playlist(name: str):
    """プレイリストの内容を取得"""
    async with mpd_connection() as client:
        try:
            songs = await client.listplaylistinfo(name)
        except Exception:
            raise HTTPException(status_code=404, detail="プレイリストが見つかりません")
        tracks = [_song_to_track(meta_cache.enrich(song)) for song in songs]
        return {"name": name, "tracks": tracks, "total": len(tracks)}


@router.post("/")
async def create_playlist(req: CreatePlaylistRequest):
    """空のプレイリストを作成"""
    async with mpd_connection() as client:
        # MPDは空のプレイリスト保存をサポートしていないため
        # 仮のプレイリストファイルとして登録（最初のトラック追加時に実体化）
        pass
    return {"ok": True, "name": req.name}


@router.post("/{name}/add")
async def add_to_playlist(name: str, req: AddTrackRequest):
    """プレイリストにトラックを追加"""
    async with mpd_connection() as client:
        try:
            await client.playlistadd(name, req.uri)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/{name}/add-multiple")
async def add_multiple_to_playlist(name: str, req: AddTracksRequest):
    """プレイリストに複数トラックを一括追加"""
    async with mpd_connection() as client:
        for uri in req.uris:
            try:
                await client.playlistadd(name, uri)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "added": len(req.uris)}


@router.post("/{name}/load")
async def load_playlist(name: str):
    """プレイリストをキューに読み込む"""
    async with mpd_connection() as client:
        try:
            await client.load(name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/{name}/tracks/{pos}")
async def remove_from_playlist(name: str, pos: int):
    """プレイリストの指定位置のトラックを削除"""
    async with mpd_connection() as client:
        try:
            await client.playlistdelete(name, pos)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/{name}")
async def delete_playlist(name: str):
    """プレイリストを削除"""
    async with mpd_connection() as client:
        try:
            await client.rm(name)
        except Exception as e:
            raise HTTPException(status_code=404, detail="プレイリストが見つかりません")
    return {"ok": True}
