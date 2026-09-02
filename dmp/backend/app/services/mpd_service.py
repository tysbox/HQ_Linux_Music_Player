"""MPD 接続 — 後方互換のための再エクスポート.

Phase 1a で実体は hqmplayer_core.mpd.client に統合済み。
既存の `from app.services.mpd_service import mpd_connection` などの import パスを
壊さないため、ここで re-export する。

Phase 1b: _song_to_track を hqmplayer_core.meta 経由に変更。
戻り値は DMP 側の Pydantic Track モデル（Pydantic 互換）へ変換して返す。
"""

from app.models.track import Track
from hqmplayer_core.mpd import (
    MPD_HOST,
    MPD_PORT,
    mpd_connection,
    get_client,
)
from hqmplayer_core.meta import song_to_track as _core_song_to_track


def _song_to_track(song: dict) -> Track:
    """MPDのsong辞書をTrackモデルに変換.

    Phase 1b: 実体は hqmplayer_core.meta.song_to_track にある。
    戻り値を DMP 側の Pydantic Track へ変換して、呼び出し側の互換性を保つ。
    """
    core_track = _core_song_to_track(song)
    # hqmplayer_core.meta.Track（Pydantic 非依存） → dmp Pydantic Track
    return Track(**core_track.to_dict())


__all__ = [
    "MPD_HOST",
    "MPD_PORT",
    "mpd_connection",
    "get_client",
    "_song_to_track",
    "Track",
]
