import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional
from mpd.asyncio import MPDClient
from app.models.track import Track

logger = logging.getLogger(__name__)

# .env ファイルがあれば読み込む（環境変数が優先）
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

MPD_HOST = os.getenv("MPD_HOST", "localhost")
try:
    MPD_PORT = int(os.getenv("MPD_PORT", "6600"))
except ValueError:
    MPD_PORT = 6600

_client: Optional[MPDClient] = None
_lock = asyncio.Lock()


@asynccontextmanager
async def mpd_connection():
    """
    【Fix 1】ロックをyield中も維持し、MPDコマンドの混線を防ぐ。
    python-mpd2は非同期セーフではないため、接続中は常に排他制御が必要。
    """
    global _client
    async with _lock:
        if _client is None:
            _client = MPDClient()
            await _client.connect(MPD_HOST, MPD_PORT)
            logger.info("MPD接続確立")
        try:
            await _client.ping()
        except Exception:
            logger.warning("MPD切断検出、再接続します")
            try:
                _client = MPDClient()
                await _client.connect(MPD_HOST, MPD_PORT)
            except Exception as e:
                _client = None
                raise ConnectionError(f"MPD再接続失敗: {e}")
        try:
            yield _client
        except Exception as e:
            logger.error(f"MPD操作エラー: {e}")
            raise


def _song_to_track(song: dict) -> Track:
    """
    MPDのsong辞書をTrackモデルに変換。
    【Fix 6】URIがhttpで始まる場合はUPnPソースと判定。
    """
    uri = song.get("file", "")

    # 【Fix 6】ソース判定
    if uri.startswith("http://") or uri.startswith("https://"):
        source = "upnp"
    else:
        source = "local"

    # タイトルのフォールバック
    title = song.get("title", "")
    if not title:
        title = uri.split("/")[-1].rsplit(".", 1)[0]

    # トラック番号の正規化（"1/10" → 1）
    track_num = None
    raw_track = song.get("track", "")
    if raw_track:
        try:
            track_num = int(str(raw_track).split("/")[0])
        except ValueError:
            pass

    # ディスク番号の正規化
    disc_num = None
    raw_disc = song.get("disc", "")
    if raw_disc:
        try:
            disc_num = int(str(raw_disc).split("/")[0])
        except ValueError:
            pass

    # duration
    duration = None
    raw_dur = song.get("duration", song.get("time", ""))
    if raw_dur:
        try:
            duration = int(float(str(raw_dur).split(":")[0]))
        except (ValueError, IndexError):
            pass

    return Track(
        id=f"{source}::{uri}",
        title=title,
        artist=song.get("artist", "Unknown Artist"),
        album=song.get("album", "Unknown Album"),
        album_artist=song.get("albumartist"),
        track_number=track_num,
        disc_number=disc_num,
        duration=duration,
        date=song.get("date"),
        genre=song.get("genre"),
        source=source,
        uri=uri,
        artwork_url=song.get("artwork_url"),
    )


async def get_client() -> MPDClient:
    """
    互換性のためのユーティリティ。既存のグローバルクライアントを返す。
    接続がない場合は接続を作成し、ping して再接続を試みる。
    """
    global _client
    async with _lock:
        if _client is None:
            _client = MPDClient()
            await _client.connect(MPD_HOST, MPD_PORT)
        try:
            await _client.ping()
        except Exception:
            try:
                _client = MPDClient()
                await _client.connect(MPD_HOST, MPD_PORT)
            except Exception as e:
                _client = None
                raise ConnectionError(f"MPD再接続失敗: {e}")
        return _client
