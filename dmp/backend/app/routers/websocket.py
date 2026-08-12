import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.mpd_service import mpd_connection, _song_to_track, MPD_HOST, MPD_PORT
from app.services.history_service import add_to_history
from app.services import meta_cache
from app.models.track import Track

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


async def _get_full_status(client) -> dict:
    """共有MPD接続を使ってフルステータスを取得"""
    status = await client.status()
    current = None
    try:
        song = await client.currentsong()
        if song:
            song = meta_cache.enrich(song)
            track = _song_to_track(song)
            current = track.model_dump()
    except Exception:
        pass

    return {
        "type":          "status",
        "state":         status.get("state", "stop"),
        "current_track": current,
        "position":      int(float(status.get("elapsed", 0))),
        "duration":      int(float(status.get("duration", 0))),
        "queue_length":  int(status.get("playlistlength", 0)),
        "random":        status.get("random") == "1",
        "repeat":        status.get("repeat") == "1",
        "song_id":       status.get("songid"),  # 曲変化検知に使用
    }


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    await websocket.accept()
    logger.info("DMP WebSocket接続確立")

    # 接続直後に現在のステータスを送信（ロック付きで一時的に取得）
    async with mpd_connection() as status_client:
        initial = await _get_full_status(status_client)
    await websocket.send_text(json.dumps(initial))

    prev_song_id = initial.get("song_id")

    # idle監視用の専用クライアント（ロックなしで監視のみ）
    idle_client = None
    try:
        from mpd.asyncio import MPDClient
        idle_client = MPDClient()
        await idle_client.connect(MPD_HOST, MPD_PORT)

        # idle監視ループ
        async for changed in idle_client.idle(["player", "mixer", "playlist", "options"]):
            # 共有接続でステータス取得（ロック付き）
            async with mpd_connection() as client:
                status_data = await _get_full_status(client)
                status_data["changed"] = list(changed)

                # 【Fix 4】曲が変わったことをidle検知 → 履歴に自動追加
                current_song_id = status_data.get("song_id")
                if (
                    "player" in changed
                    and current_song_id != prev_song_id
                    and status_data.get("current_track")
                ):
                    try:
                        track = Track(**status_data["current_track"])
                        add_to_history(track)
                        logger.debug(f"履歴追加: {track.title}")
                    except Exception as e:
                        logger.warning(f"履歴追加失敗: {e}")

                prev_song_id = current_song_id

                # song_idはフロントエンドに送る必要がないため除去
                status_data.pop("song_id", None)
                await websocket.send_text(json.dumps(status_data))

    except WebSocketDisconnect:
        logger.info("DMP WebSocket切断")
    except Exception as e:
        logger.error(f"DMP WebSocketエラー: {e}")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(e)})
            )
        except Exception:
            pass
    finally:
        if idle_client:
            try:
                idle_client.disconnect()
            except Exception:
                pass
