"""/ws/all — 統合 WebSocket (Phase X-2 + ADR-003).

DSP の /ws/now_playing と DMP の /ws/status を 1 接続で受信。
フロントエンド (unified-shell) の切替コストを最小化。

メッセージ形式:
{
  "type": "now_playing" | "status" | "ready",
  "data": { ... }
}
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hqmplayer_core.mpd import mpd_connection
from hqmplayer_core.meta import format_now_playing

logger = logging.getLogger(__name__)

router = APIRouter()


async def _emit_loop(ws: WebSocket, stop_event: asyncio.Event):
    """/ws/now_playing 相当のデータを 2 秒間隔で送信."""
    last_song_id: Optional[str] = None
    last_state: Optional[str] = None
    while not stop_event.is_set():
        try:
            async with mpd_connection() as c:
                st = await c.status()
                so = await c.currentsong()
            data = format_now_playing(st, so)
            song_id = data.get("song_id", "")
            state = data.get("state", "")
            if song_id != last_song_id or state != last_state:
                await ws.send_json({"type": "now_playing", "data": data})
                last_song_id = song_id
                last_state = state
        except WebSocketDisconnect:
            stop_event.set()
            return
        except Exception as e:
            logger.debug("emit loop: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


@router.websocket("/ws/all")
async def websocket_all(ws: WebSocket):
    """/ws/now_playing と /ws/status を統合した push を提供."""
    await ws.accept()
    logger.info("/ws/all 接続確立")

    # 接続直後に ready を送信
    try:
        await ws.send_json({"type": "ready", "data": {"port": 8002, "version": "0.1.0-phase3b"}})
    except Exception:
        return

    stop_event = asyncio.Event()
    # 2 秒 polling タスクを起動
    emit_task = asyncio.create_task(_emit_loop(ws, stop_event))

    # クライアントからの受信ループ（切断検知用）
    try:
        while True:
            msg = await ws.receive_text()
            # クライアントからの ping 等は無視
            if msg == "ping":
                await ws.send_json({"type": "pong", "data": {}})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("ws_all receive error: %s", e)
    finally:
        stop_event.set()
        emit_task.cancel()
        try:
            await emit_task
        except (asyncio.CancelledError, Exception):
            pass
        logger.info("/ws/all 切断")
