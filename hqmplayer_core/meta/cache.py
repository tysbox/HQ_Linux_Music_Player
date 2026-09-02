"""UPnP HTTP トラック用メタデータキャッシュ（共通実装・永続化対応）.

MPD は HTTP ストリームのタグをキュー追加時点では読めないため、
フロントエンドから渡されたメタデータをキャッシュし、表示を統一する。
DSP / DMP 両バックエンドから共通利用される。

設計方針:
  - 永続化先は ~/.config/hqmplayer/meta_cache.json（再起動後も保持）
  - 旧パス (/tmp/dmp_meta_cache.json) からも起動時に 1 回だけマイグレーション
  - FastAPI 等の Web フレームワークには依存しない（純粋ロジック）
  - URI が http(s) のもののみ保存対象
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 新しい永続化先
_NEW_CACHE_FILE = os.path.expanduser("~/.config/hqmplayer/meta_cache.json")

# 旧パス（マイグレーション用・1 リリースだけ読みに行く）
_LEGACY_CACHE_FILES = (
    "/tmp/dmp_meta_cache.json",
    "/tmp/audiophile_meta_cache.json",
)

# key: URI, value: {"title": ..., "artist": ..., "album": ..., "artwork_url": ...}
_cache: dict[str, dict] = {}


def _ensure_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as e:
            logger.warning("メタキャッシュディレクトリ作成失敗: %s", e)


def _load() -> None:
    """起動時に新パス → 旧パスの順で読み込む.

    新パスが既にあれば旧パスは無視する。新パスがなければマイグレーションする。
    """
    global _cache
    try:
        if os.path.exists(_NEW_CACHE_FILE):
            with open(_NEW_CACHE_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
            logger.info("メタキャッシュ読込（新パス）: %d 件", len(_cache))
            return
    except Exception as e:
        logger.warning("メタキャッシュ新パス読込失敗: %s", e)
        _cache = {}

    # 旧パスからマイグレーション
    for legacy in _LEGACY_CACHE_FILES:
        try:
            if os.path.exists(legacy):
                with open(legacy, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
                logger.info(
                    "メタキャッシュを %s から %s へ %d 件マイグレーション",
                    legacy, _NEW_CACHE_FILE, len(_cache),
                )
                _save()
                # マイグレーション成功時は旧ファイルを削除（任意）
                try:
                    os.remove(legacy)
                except OSError:
                    pass
                return
        except Exception as e:
            logger.warning("メタキャッシュ旧パス読込失敗 (%s): %s", legacy, e)

    _cache = {}


def _save() -> None:
    try:
        _ensure_dir(_NEW_CACHE_FILE)
        with open(_NEW_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("メタキャッシュ保存失敗: %s", e)


# 起動時に読み込み
_load()


def store(
    uri: str,
    title: Optional[str],
    artist: Optional[str],
    album: Optional[str],
    artwork_url: Optional[str],
) -> None:
    """UPnP HTTP トラックのメタデータをキャッシュに保存（永続化）."""
    if not uri:
        return
    if not (uri.startswith("http://") or uri.startswith("https://")):
        return
    if not title:
        # タイトル無しではキャッシュ価値がない（MPD が読めなかった場合の最低保証がない）
        return
    _cache[uri] = {
        "title": title,
        "artist": artist,
        "album": album,
        "artwork_url": artwork_url,
    }
    _save()


def enrich(song: dict) -> dict:
    """MPD の song 字典 に メタデータを補完して返す.

    title が空の場合、または artist / album がデフォルト値 ('Unknown Artist' 等)
    の場合にキャッシュから補完する。
    """
    uri = song.get("file", "")
    if not (uri.startswith("http://") or uri.startswith("https://")):
        return song
    if uri not in _cache:
        return song

    cached = _cache[uri]
    song = dict(song)
    # タイトルが空の場合のみ補完
    if not song.get("title") and cached.get("title"):
        song["title"] = cached["title"]
    # artist / album は 'Unknown *' のときも補完する（MPD が取得できなかったケース）
    if (not song.get("artist") or song.get("artist") == "Unknown Artist") and cached.get("artist"):
        song["artist"] = cached["artist"]
    if (not song.get("album") or song.get("album") == "Unknown Album") and cached.get("album"):
        song["album"] = cached["album"]
    if cached.get("artwork_url") and not song.get("artwork_url"):
        song["artwork_url"] = cached["artwork_url"]
    return song


def get(uri: str) -> Optional[dict]:
    """キャッシュから単一のエントリを取得（なければ None）."""
    return _cache.get(uri)


def clear() -> None:
    """キャッシュをクリア（テスト・デバッグ用）."""
    global _cache
    _cache = {}
    _save()


def size() -> int:
    """現在のキャッシュサイズ."""
    return len(_cache)