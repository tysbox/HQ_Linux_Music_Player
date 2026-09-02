"""/ws/now_playing — DSP 互換 WebSocket (Phase X-2).

backend/main.py の ws_now_playing を移植。2 秒 polling で
曲 ID / state が変わったときだけ push する。
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hqmplayer_core.mpd import mpd_connection
from hqmplayer_core.meta import format_now_playing

logger = logging.getLogger(__name__)

router = APIRouter()


class WSManager:
    """複数クライアント管理."""

    def __init__(self):
        self.clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = WSManager()


@router.websocket("/ws/now_playing")
async def ws_now_playing(ws: WebSocket):
    """Now Playing WebSocket — DSP:8000 と完全互換.

    2 秒間隔の polling で status/currentsong を取得。
    song_id か state が変わったときだけ push（無駄な push を抑制）。
    """
    await ws_manager.connect(ws)
    last_song_id: Optional[str] = None
    last_state: Optional[str] = None

    try:
        while True:
            try:
                async with mpd_connection() as c:
                    st = await c.status()
                    so = await c.currentsong()
            except Exception:
                await asyncio.sleep(2)
                continue

            data = format_now_playing(st, so)
            song_id = data.get("song_id", "")
            state = data.get("state", "")

            if song_id != last_song_id or state != last_state:
                await ws.send_json(data)
                last_song_id = song_id
                last_state = state

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.warning("ws_now_playing error: %s", e)
        try:
            ws_manager.disconnect(ws)
        except Exception:
            pass
