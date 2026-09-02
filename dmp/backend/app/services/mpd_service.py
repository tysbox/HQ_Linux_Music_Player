"""MPD 接続 — 後方互換のための再エクスポート.

Phase 1a で実体は hqmplayer_core.mpd.client に統合済み。
既存の `from app.services.mpd_service import mpd_connection` などの import パスを
壊さないため、ここで re-export する。

_song_to_track および Track モデル変換は Phase 1b で hqmplayer_core.meta へ
統合予定。Phase 1a では元の実装を残している。
"""

from app.models.track import Track
from hqmplayer_core.mpd import (
    MPD_HOST,
    MPD_PORT,
    mpd_connection,
    get_client,
)


def _song_to_track(song: dict) -> Track:
    """
    MPDのsong辞書をTrackモデルに変換。
    【Fix 6】URIがhttpで始まる場合はUPnPソースと判定。

    Phase 1a: 既存実装を残している（Phase 1b で hqmplayer_core.meta へ移動予定）。
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


__all__ = [
    "MPD_HOST",
    "MPD_PORT",
    "mpd_connection",
    "get_client",
    "_song_to_track",
    "Track",
]
