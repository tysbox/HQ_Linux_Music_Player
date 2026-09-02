"""MPD クライアント共通実装.

DSP / DMP 両バックエンドから共有される MPD I/O 層。
非同期コンテキストマネージャ（mpd_connection）と同期 I/O ランブを提供する。
"""

from .client import (
    MPD_HOST,
    MPD_PORT,
    mpd_connection,
    get_client,
    sync_status,
    sync_currentsong,
    sync_idle,
    sync_readpicture,
    sync_albumart,
)

__all__ = [
    "MPD_HOST",
    "MPD_PORT",
    "mpd_connection",
    "get_client",
    "sync_status",
    "sync_currentsong",
    "sync_idle",
    "sync_readpicture",
    "sync_albumart",
]