from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class Track(BaseModel):
    """ソースを問わず共通のトラックモデル（将来のQobuz追加に対応）"""
    id: str                          # "local::relative/path/to/file.flac"
    title: str
    artist: str
    album: str
    album_artist: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    duration: Optional[int] = None   # 秒
    date: Optional[str] = None
    genre: Optional[str] = None
    source: str = "local"            # 将来: "qobuz"
    uri: str                         # MPDに渡すパス
    artwork_url: Optional[str] = None


class QueueItem(BaseModel):
    position: int
    track: Track
    is_current: bool = False


class HistoryEntry(BaseModel):
    track: Track
    played_at: datetime


class Playlist(BaseModel):
    name: str
    tracks: list[Track] = []
    created_at: datetime
    updated_at: datetime


class PlaybackStatus(BaseModel):
    state: str                       # "play" | "pause" | "stop"
    current_track: Optional[Track] = None
    position: int = 0                # 秒
    duration: int = 0                # 秒
    queue_length: int = 0
    volume: Optional[int] = None
    random: bool = False
    repeat: bool = False
