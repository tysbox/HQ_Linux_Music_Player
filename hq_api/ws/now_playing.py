"""/ws/now_playing — DSP 互換 WebSocket (Phase X-2, イベント駆動化).

backend/main.py の ws_now_playing を移植・改良。
MPD idle() イベント駆動で、曲変化・シーク・状態変更を即時 push する。
ポーリング (1秒間隔) を廃止し、レイテンシを大幅削減。
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hqmplayer_core.mpd import mpd_connection, mpd_idle_connection
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
    """Now Playing WebSocket — DSP:8000 と完全互換 (イベント駆動版).

    MPD idle() で player/mixer/playlist/options 変更を検知し、
    変化時に format_now_playing() 結果を即時 push。
    position の差分が 5秒以上 (= seek 発生) の場合も即時 push して
    フロントエンドのシークバー UI を即時同期する。

    ポーリング間隔: なし (イベント駆動)
    """
    await ws_manager.connect(ws)
    last_song_id: Optional[str] = None
    last_state: Optional[str] = None
    last_position: float = -1.0

    try:
        # 初期状態を送信
        async with mpd_connection() as c:
            st = await c.status()
            so = await c.currentsong()
        initial_data = format_now_playing(st, so)
        await ws.send_json(initial_data)
        last_song_id = initial_data.get("song_id", "")
        last_state = initial_data.get("state", "")
        last_position = float(initial_data.get("elapsed", 0) or 0)

        # idle() イベントループで変更を監視
        # NOTE: 共有ロックを占有しない独立接続を使う。
        # 共有接続で idle 待機すると /health 等がデッドロックする。
        async with mpd_idle_connection() as idle_client:
            async for changed in idle_client.idle(["player", "mixer", "playlist", "options"]):
                try:
                    async with mpd_connection() as client:
                        st = await client.status()
                        so = await client.currentsong()
                    data = format_now_playing(st, so)
                    song_id = data.get("song_id", "")
                    state = data.get("state", "")
                    position = float(data.get("elapsed", 0) or 0)

                    song_changed = song_id != last_song_id
                    state_changed = state != last_state
                    # seek detection: position jumped > 5s backwards or > 8s forwards
                    seek_detected = (
                        last_position >= 0 and (
                            position < last_position - 5  # backwards
                            or position > last_position + 8  # forwards (allow for normal play drift)
                        )
                    )

                    if song_changed or state_changed or seek_detected:
                        await ws.send_json(data)
                        last_song_id = song_id
                        last_state = state
                        last_position = position

                except Exception as e:
                    logger.warning("ws_now_playing iteration error: %s", e)
                    await asyncio.sleep(1)

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.warning("ws_now_playing error: %s", e)
        try:
            ws_manager.disconnect(ws)
        except Exception:
            pass
