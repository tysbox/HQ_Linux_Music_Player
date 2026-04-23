from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.mpd_service import mpd_connection, _song_to_track
from app.services.history_service import add_to_history
from app.services import meta_cache
from app.models.track import PlaybackStatus, QueueItem

router = APIRouter(prefix="/api/playback", tags=["playback"])


class AddToQueueRequest(BaseModel):
    uri: str
    play_now: bool = False  # Trueなら追加後すぐ再生


class SeekRequest(BaseModel):
    position: int  # 秒


@router.get("/status", response_model=PlaybackStatus)
async def get_status():
    """現在の再生状態を取得"""
    async with mpd_connection() as client:
        status = await client.status()
        current_song = None
        try:
            song = await client.currentsong()
            if song:
                song = meta_cache.enrich(song)
                current_song = _song_to_track(song)
        except Exception:
            pass

        # elapsed / duration の取得
        elapsed = int(float(status.get("elapsed", 0)))
        duration = int(float(status.get("duration", 0)))

        return PlaybackStatus(
            state=status.get("state", "stop"),
            current_track=current_song,
            position=elapsed,
            duration=duration,
            queue_length=int(status.get("playlistlength", 0)),
            volume=int(status.get("volume", 0)) if status.get("volume") else None,
            random=status.get("random") == "1",
            repeat=status.get("repeat") == "1",
        )


@router.post("/play")
async def play():
    async with mpd_connection() as client:
        await client.play()
    return {"ok": True}


@router.post("/pause")
async def pause():
    async with mpd_connection() as client:
        status = await client.status()
        if status.get("state") == "pause":
            await client.play()
        else:
            await client.pause(1)
    return {"ok": True}


@router.post("/stop")
async def stop():
    async with mpd_connection() as client:
        await client.stop()
    return {"ok": True}


@router.post("/next")
async def next_track():
    async with mpd_connection() as client:
        # 履歴に追加してから次へ
        try:
            song = await client.currentsong()
            if song:
                add_to_history(_song_to_track(song))
        except Exception:
            pass
        await client.next()
    return {"ok": True}


@router.post("/previous")
async def previous_track():
    async with mpd_connection() as client:
        await client.previous()
    return {"ok": True}


@router.post("/seek")
async def seek(req: SeekRequest):
    async with mpd_connection() as client:
        await client.seekcur(req.position)
    return {"ok": True}


@router.post("/random")
async def toggle_random():
    async with mpd_connection() as client:
        status = await client.status()
        current = status.get("random") == "1"
        await client.random(0 if current else 1)
    return {"random": not current}


@router.post("/repeat")
async def toggle_repeat():
    async with mpd_connection() as client:
        status = await client.status()
        current = status.get("repeat") == "1"
        await client.repeat(0 if current else 1)
    return {"repeat": not current}
