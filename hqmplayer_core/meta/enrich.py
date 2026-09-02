"""MPD song dict → Track 変換の共通実装.

DSP / DMP の両バックエンドから利用される song 整形ロジック。
FastAPI 等の Web フレームワークには依存しない（純粋ロジック）。

設計方針:
  - Track モデルは Pydantic で定義し、Web 層に依存しない形を維持する
  - URI が http(s) で始まる場合は UPnP ソース、それ以外は local ソースとして扱う
  - タイトル / トラック番号 / ディスク番号 / duration を正規化する
"""

from typing import Optional


class Track:
    """Pydantic 依存を避けるための薄いデータクラス。

    既存の dmp/backend/app/models/track.py:Track と同等のフィールドを持つ。
    Pydantic が必要になった時点で dmp 側のモデルに切り替えるか、
    hqmplayer_core 側に pydantic 依存を許可する（Phase 2 で決定）。
    """

    __slots__ = (
        "id",
        "title",
        "artist",
        "album",
        "album_artist",
        "track_number",
        "disc_number",
        "duration",
        "date",
        "genre",
        "source",
        "uri",
        "artwork_url",
    )

    def __init__(
        self,
        *,
        id: str,
        title: str,
        artist: str,
        album: str,
        album_artist: Optional[str] = None,
        track_number: Optional[int] = None,
        disc_number: Optional[int] = None,
        duration: Optional[int] = None,
        date: Optional[str] = None,
        genre: Optional[str] = None,
        source: str = "local",
        uri: str,
        artwork_url: Optional[str] = None,
    ):
        self.id = id
        self.title = title
        self.artist = artist
        self.album = album
        self.album_artist = album_artist
        self.track_number = track_number
        self.disc_number = disc_number
        self.duration = duration
        self.date = date
        self.genre = genre
        self.source = source
        self.uri = uri
        self.artwork_url = artwork_url

    def to_dict(self) -> dict:
        """dmp 側の Pydantic Track へ変換するための dict 化。"""
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "track_number": self.track_number,
            "disc_number": self.disc_number,
            "duration": self.duration,
            "date": self.date,
            "genre": self.genre,
            "source": self.source,
            "uri": self.uri,
            "artwork_url": self.artwork_url,
        }


def _normalize_track_number(raw: str) -> Optional[int]:
    """トラック番号の正規化（"1/10" → 1）。"""
    if not raw:
        return None
    try:
        return int(str(raw).split("/")[0])
    except (ValueError, AttributeError):
        return None


def _normalize_disc_number(raw: str) -> Optional[int]:
    """ディスク番号の正規化。"""
    if not raw:
        return None
    try:
        return int(str(raw).split("/")[0])
    except (ValueError, AttributeError):
        return None


def _normalize_duration(raw_dur: str) -> Optional[int]:
    """duration の正規化（秒）。

    MPD は '363.346' のような小数秒で返す。
    一部 URI は '207:363' 形式（elapsed/duration のペア）を持つが、
    song dict の duration は単一の秒数のみなので ':' 形式は除外する。
    """
    if not raw_dur:
        return None
    if ":" in str(raw_dur):
        # 'elapsed:duration' 形式は song dict では通常現れないが念のため弾く
        return None
    try:
        return int(float(raw_dur))
    except (ValueError, TypeError):
        return None


def _detect_source(uri: str) -> str:
    """URI が http(s) で始まる場合は UPnP ソース。"""
    if uri.startswith("http://") or uri.startswith("https://"):
        return "upnp"
    return "local"


def _fallback_title(uri: str, current: str) -> str:
    """タイトルが空の場合 URI からファイル名を推定。"""
    if current:
        return current
    if not uri:
        return "Unknown"
    try:
        basename = uri.split("/")[-1].rsplit(".", 1)[0]
        return basename or "Unknown"
    except Exception:
        return "Unknown"


def song_to_track(song: dict) -> Track:
    """MPD の song 辞書を Track に変換する.

    URI スキームに応じて source を自動判定する。
    タイトルが空の場合は URI のファイル名部分をフォールバックとして使う。
    """
    uri = song.get("file", "")

    title = _fallback_title(uri, song.get("title", ""))

    return Track(
        id=f"{_detect_source(uri)}::{uri}",
        title=title,
        artist=song.get("artist", "Unknown Artist"),
        album=song.get("album", "Unknown Album"),
        album_artist=song.get("albumartist"),
        track_number=_normalize_track_number(song.get("track", "")),
        disc_number=_normalize_disc_number(song.get("disc", "")),
        duration=_normalize_duration(song.get("duration", song.get("time", ""))),
        date=song.get("date"),
        genre=song.get("genre"),
        source=_detect_source(uri),
        uri=uri,
        artwork_url=song.get("artwork_url"),
    )


# 後方互換のためのエイリアス（DMP 側の旧名）
_song_to_track = song_to_track