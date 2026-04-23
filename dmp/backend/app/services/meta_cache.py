"""
UPnP HTTPトラック用メタデータキャッシュ（共有モジュール・永続化対応）

MPDはHTTPストリームのタグをキューに追加した時点では読めない。
フロントエンドからトラックを追加する際にメタデータを渡し、
ここにキャッシュしておくことで queue / websocket / history の
表示を統一する。再起動後もJSONファイルに永続化する。
"""

import json
import os
from pathlib import Path
from typing import Optional

_CACHE_FILE = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "audiophile-dmp" / "meta_cache.json"

# key: URI, value: {"title": ..., "artist": ..., "album": ..., "artwork_url": ...}
_cache: dict[str, dict] = {}


def _ensure_dir() -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> None:
    global _cache
    try:
        if _CACHE_FILE.exists():
            with _CACHE_FILE.open("r", encoding="utf-8") as f:
                _cache = json.load(f)
    except Exception:
        _cache = {}


def _save() -> None:
    try:
        _ensure_dir()
        with _CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except Exception:
        pass


# 起動時に読み込み
_load()


def store(uri: str, title: Optional[str], artist: Optional[str],
          album: Optional[str], artwork_url: Optional[str]) -> None:
    """UPnP HTTPトラックのメタデータをキャッシュに保存（永続化）"""
    if not (uri.startswith("http://") or uri.startswith("https://")):
        return
    if not title:
        return
    _cache[uri] = {
        "title":       title,
        "artist":      artist,
        "album":       album,
        "artwork_url": artwork_url,
    }
    _save()


def enrich(song: dict) -> dict:
    """
    MPDのsong辞書にキャッシュメタデータを補完して返す。
    titleがなければキャッシュから補完する（MPDが読めなかった場合）。
    """
    uri = song.get("file", "")
    if not (uri.startswith("http://") or uri.startswith("https://")):
        return song
    if uri not in _cache:
        return song

    cached = _cache[uri]
    song = dict(song)
    # タイトルが空 or URIそのものの場合のみ補完
    if not song.get("title") and cached.get("title"):
        song["title"] = cached["title"]
    if (not song.get("artist") or song.get("artist") == "Unknown Artist") and cached.get("artist"):
        song["artist"] = cached["artist"]
    if (not song.get("album") or song.get("album") == "Unknown Album") and cached.get("album"):
        song["album"] = cached["album"]
    if cached.get("artwork_url") and not song.get("artwork_url"):
        song["artwork_url"] = cached["artwork_url"]
    return song
