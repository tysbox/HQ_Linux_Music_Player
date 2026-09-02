"""MPD クライアント共通実装.

DSP / DMP 両バックエンドから共有される MPD I/O 層。
async 専用（メインのイベントループ上で await する）。
"""

from .client import (
    MPD_HOST,
    MPD_PORT,
    mpd_connection,
    get_client,
)

__all__ = [
    "MPD_HOST",
    "MPD_PORT",
    "mpd_connection",
    "get_client",
]
