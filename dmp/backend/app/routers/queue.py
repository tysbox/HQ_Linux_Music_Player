from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.mpd_service import mpd_connection, _song_to_track
from app.services import meta_cache
from app.models.track import QueueItem

router = APIRouter(prefix="/api/queue", tags=["queue"])


class AddRequest(BaseModel):
    uri: str
    play_now: bool = False
    insert_next: bool = False
    # Optional track metadata (used for UPnP tracks that MPD can't tag)
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    artwork_url: Optional[str] = None


class MoveRequest(BaseModel):
    from_pos: int
    to_pos: int


@router.get("/")
async def get_queue():
    async with mpd_connection() as client:
        playlist = await client.playlistinfo()
        status = await client.status()
        current_song_id = status.get("songid")
        items = []
        for song in playlist:
            song = meta_cache.enrich(song)
            track = _song_to_track(song)
            items.append(QueueItem(
                position=int(song.get("pos", 0)),
                track=track,
                is_current=song.get("id") == current_song_id,
            ))
        return {"queue": items, "total": len(items)}


@router.post("/add")
async def add_to_queue(req: AddRequest):
    """
    【Fix 3】addidの戻り値(song_id)を使ってplayidで確実に再生。
    同じ曲が複数キューにある場合も誤動作しない。
    UPnP HTTPトラックのメタデータをキャッシュして queue 表示に使う。
    """
    uri = req.uri
    # Cache metadata for HTTP URIs (MPD cannot fetch tags for non-playing HTTP streams)
    meta_cache.store(uri, req.title, req.artist, req.album, req.artwork_url)

    async with mpd_connection() as client:
        if req.insert_next:
            status = await client.status()
            current_pos = int(status.get("song", -1))
            song_id = await client.addid(req.uri, current_pos + 1)
        else:
            song_id = await client.addid(req.uri)

        if req.play_now:
            await client.playid(song_id)

    return {"ok": True}


@router.post("/play/{position}")
async def play_at_position(position: int):
    async with mpd_connection() as client:
        await client.play(position)
    return {"ok": True}


@router.delete("/{position}")
async def remove_from_queue(position: int):
    async with mpd_connection() as client:
        await client.delete(position)
    return {"ok": True}


@router.post("/clear")
async def clear_queue():
    async with mpd_connection() as client:
        await client.clear()
    return {"ok": True}


@router.post("/move")
async def move_in_queue(req: MoveRequest):
    async with mpd_connection() as client:
        await client.move(req.from_pos, req.to_pos)
    return {"ok": True}


@router.post("/shuffle")
async def shuffle_queue():
    async with mpd_connection() as client:
        await client.shuffle()
    return {"ok": True}
