"""Now Playing 整形ロジックの共通実装.

DSP / DMP の両バックエンドから利用される Now Playing 整形。
HTTP ストリーム（UPnP など）の URI クエリに含まれる title / artist / album を
フォールバックとして抽出する処理を集約する。

FastAPI 等の Web フレームワークには依存しない（純粋ロジック）。
"""

from typing import Optional
from urllib.parse import urlparse, parse_qs


def _extract_from_url_query(file_url: str) -> dict:
    """URI のクエリ文字列から title / artist / albumartist / album を抽出.

    UPnP 由来の http(s)://... URI に ?title=...&artist=... が埋め込まれている
    場合があり、MPD がタグを取得できなかった際のフォールバックとして使う。
    """
    result = {}
    if not file_url or not file_url.startswith("http"):
        return result
    try:
        q = parse_qs(urlparse(file_url).query)
        if "title" in q:
            result["title"] = q["title"][0]
        if "artist" in q:
            result["artist"] = q["artist"][0]
        elif "albumartist" in q:
            result["artist"] = q["albumartist"][0]
        if "album" in q:
            result["album"] = q["album"][0]
    except Exception:
        # クエリ解析の失敗は握りつぶす（フォールバック処理なので失敗しても致命的ではない）
        pass
    return result


def _clean_artist(artist: str) -> str:
    """'A; B' / 'A, B' のような複合アーティスト表記から先頭だけを取り出す."""
    if not artist:
        return artist
    return artist.split(";")[0].split(",")[0].strip()


def format_now_playing(status: dict, song: dict) -> dict:
    """MPD の status / currentsong を Now Playing 用の dict に整形する.

    DSP backend の /api/now_playing および WebSocket push の両方に対応する
    統一整形ロジック。URI のクエリ文字列からのフォールバック抽出も含む。
    """
    file_url = song.get("file", "")
    title = song.get("title", "Unknown")
    artist = song.get("artist", "Unknown")
    album = song.get("album", "Unknown")

    # HTTP URI でタグが取れていない場合、クエリからフォールバック抽出
    if "http" in file_url and (title == "Unknown" or artist == "Unknown"):
        fallback = _extract_from_url_query(file_url)
        title = fallback.get("title", title)
        artist = fallback.get("artist", artist)
        if "album" in fallback:
            album = fallback["album"]

    return {
        "song_id": status.get("songid", ""),
        "title": title,
        "artist": _clean_artist(artist),
        "album": album,
        "file": file_url,
        "state": status.get("state", "stop"),
        "audio": status.get("audio", ""),
        "elapsed": float(status.get("elapsed", 0) or 0),
        "duration": float(status.get("duration", 0) or 0),
    }