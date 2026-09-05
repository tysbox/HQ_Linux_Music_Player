"""メタデータ整形・補完の共通実装.

DSP / DMP 両バックエンドから共有される song 整形・Now Playing 整形ロジック。
FastAPI 等の Web フレームワークには依存しない（純粋ロジック）。

Phase 1b で実装:
- enrich.py: MPD song dict → Track 変換
- formatting.py: Now Playing dict 整形（URI クエリフォールバック含む）

Phase 1c で実装:
- cache.py: HTTP ストリームメタデータの永続キャッシュ（DSP/DMP 共通）
"""

from .enrich import (
    Track,
    song_to_track,
    _song_to_track,
    _detect_source,
    _fallback_title,
    _normalize_track_number,
    _normalize_disc_number,
    _normalize_duration,
)
from .formatting import format_now_playing
from .cache import store as cache_store, enrich as cache_enrich, get as cache_get, clear as cache_clear, size as cache_size

__all__ = [
    "Track",
    "song_to_track",
    "_song_to_track",
    "_detect_source",
    "_fallback_title",
    "_normalize_track_number",
    "_normalize_disc_number",
    "_normalize_duration",
    "format_now_playing",
    # Phase 1c: meta_cache
    "cache_store",
    "cache_enrich",
    "cache_get",
    "cache_clear",
    "cache_size",
]