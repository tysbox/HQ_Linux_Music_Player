"""アルバムアート解決ロジックの共通実装.

DSP / DMP の両バックエンドから利用されるアルバムアート取得戦略を集約する。

優先順位:
  1. ローカルファイル（Folder.jpg / folder.jpg / cover.jpg / Cover.jpg）
  2. MPD readpicture / albumart
  3. iTunes Search API（artist + album）
  4. SVG placeholder

戻り値は ArtResult dataclass として返す。
呼び出し側で FastAPI Response 等に変換することを想定しているため、
本モジュールは Web フレームワークに依存しない。
"""

import os
import urllib.parse
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse


# SVG プレースホルダのバイト列（呼び出し側で Content-Type を変えるだけで再利用可能）
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">'
    '<rect width="300" height="300" fill="#1f2937"/>'
    '<text x="50%" y="50%" fill="#4b5563" font-size="16" '
    'font-family="sans-serif" text-anchor="middle" dy=".3em">No Artwork</text>'
    "</svg>"
)


@dataclass
class ArtResult:
    """アート解決結果.

    source: "local" / "mpd" / "itunes" / "placeholder"
    media_type: e.g. "image/jpeg", "image/png", "image/svg+xml"
    content: bytes（SVG の場合は str を bytes に encode したものを入れる）
    redirect_url: iTunes 経由のリダイレクト先（URL 文字列）
    """

    source: str
    media_type: str
    content: bytes
    redirect_url: Optional[str] = None


def _check_local_art(filepath: str) -> Optional[str]:
    """ローカルアルバムアートのパスを探す.

    HTTP URI の場合は path 部分のみ取り出して dirname を推定する。
    """
    if filepath.startswith("http"):
        try:
            filepath = urllib.parse.unquote(urlparse(filepath).path)
        except Exception:
            pass
    dirname = os.path.dirname(filepath) if os.path.exists(filepath) else filepath
    for name in ("Folder.jpg", "folder.jpg", "cover.jpg", "Cover.jpg"):
        path = os.path.join(dirname, name)
        if os.path.exists(path):
            return path
    return None


def _read_local(path: str) -> Optional[ArtResult]:
    try:
        with open(path, "rb") as f:
            data = f.read()
        return ArtResult(source="local", media_type="image/jpeg", content=data)
    except Exception:
        return None


def _read_mpd(file: str, mpd_readpicture, mpd_albumart) -> Optional[ArtResult]:
    for fetcher in (mpd_readpicture, mpd_albumart):
        try:
            picture = fetcher(file)
            if picture and "binary" in picture:
                return ArtResult(
                    source="mpd",
                    media_type=picture.get("type", "image/jpeg"),
                    content=picture["binary"],
                )
        except Exception:
            continue
    return None


def _itunes_search(artist: str, album: str, http_get) -> Optional[ArtResult]:
    """iTunes Search API を呼んでアート URL を返す.

    http_get: requests.get 互換関数（テスト時にモックしやすいよう注入）
    """
    if not artist or not album or artist == "Unknown":
        return None
    try:
        response = http_get(
            f"https://itunes.apple.com/search?term={artist}+{album}&entity=album&limit=1",
            timeout=3,
        )
        results = response.json().get("results")
        if results:
            url = results[0].get("artworkUrl100", "").replace("100x100", "600x600")
            if url:
                # iTunes はリダイレクト URL を返す形にする
                return ArtResult(
                    source="itunes",
                    media_type="image/jpeg",
                    content=b"",
                    redirect_url=url,
                )
    except Exception:
        return None
    return None


def _placeholder() -> ArtResult:
    return ArtResult(
        source="placeholder",
        media_type="image/svg+xml",
        content=PLACEHOLDER_SVG.encode("utf-8"),
    )


def resolve_art(
    file: str,
    artist: str = "",
    album: str = "",
    *,
    mpd_readpicture=None,
    mpd_albumart=None,
    http_get=None,
) -> ArtResult:
    """アルバムアートを解決する.

    file: MPD が返す URI (file タグの値)
    artist, album: iTunes フォールバック用（artist + album で検索）
    mpd_readpicture / mpd_albumart: テスト時にモックしやすいよう注入可能
    http_get: requests.get 互換関数。
        明示的に渡した場合はその関数を使う。
        None のままなら iTunes フォールバックを試みない（テスト・CLI 用途）。
        自動解決したい場合は use_default_http=True を指定する。

    優先順位: local → mpd → itunes → placeholder
    """
    # 1. ローカルファイル
    local_path = _check_local_art(file)
    if local_path:
        result = _read_local(local_path)
        if result:
            return result

    # 2. MPD
    if mpd_readpicture is not None and mpd_albumart is not None:
        result = _read_mpd(file, mpd_readpicture, mpd_albumart)
        if result:
            return result

    # 3. iTunes（http_get が明示的に渡された場合のみ）
    if http_get is not None:
        result = _itunes_search(artist, album, http_get)
        if result:
            return result

    # 4. placeholder
    return _placeholder()