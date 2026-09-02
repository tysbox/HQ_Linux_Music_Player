"""アルバムアート解決ロジックの共通実装.

DSP / DMP の両バックエンドから利用されるアルバムアート取得戦略を集約。
ローカルファイル → MPD → iTunes → SVG placeholder の優先順位で解決する。
Web フレームワーク（FastAPI）には依存しない（純粋ロジック）。
"""

from .resolver import (
    ArtResult,
    PLACEHOLDER_SVG,
    resolve_art,
    _check_local_art,
    _read_local,
    _read_mpd,
    _itunes_search,
    _placeholder,
)

__all__ = [
    "ArtResult",
    "PLACEHOLDER_SVG",
    "resolve_art",
    "_check_local_art",
    "_read_local",
    "_read_mpd",
    "_itunes_search",
    "_placeholder",
]