import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from mpd.asyncio import MPDClient
from app.services.mpd_service import MPD_HOST, MPD_PORT, _song_to_track
from app.services.history_service import add_to_history
from app.services import meta_cache
from app.models.track import Track

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


async def _get_full_status(client: MPDClient) -> dict:
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

    idle_client   = MPDClient()
    status_client = MPDClient()

    try:
        await idle_client.connect(MPD_HOST, MPD_PORT)
        await status_client.connect(MPD_HOST, MPD_PORT)

        # 接続直後に現在のステータスを送信
        initial = await _get_full_status(status_client)
        await websocket.send_text(json.dumps(initial))

        prev_song_id = initial.get("song_id")

        # idle監視ループ
        # mpd.asyncio.MPDClient.idle(...) は非同期イテレータを返すため
        # `async for` で変更通知を受け取る
        async for changed in idle_client.idle(["player", "mixer", "playlist", "options"]):

            status_data = await _get_full_status(status_client)
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
        try:
            idle_client.disconnect()
        except Exception:
            pass
        try:
            status_client.disconnect()
        except Exception:
            pass
