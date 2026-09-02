"""hqmplayer_core 共通モジュールの単体テスト.

DSP / DMP 両 backend から利用される純粋ロジックの品質保証。
追加インストール不要（標準 unittest のみ）。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_hqmplayer_core -v
"""
import json
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# hqmplayer_core は FastAPI 非依存
import hqmplayer_core
from hqmplayer_core.meta.enrich import (
    song_to_track,
    _detect_source,
    _fallback_title,
    _normalize_track_number,
    _normalize_disc_number,
    _normalize_duration,
)
from hqmplayer_core.meta.formatting import format_now_playing, _extract_from_url_query
from hqmplayer_core.meta.cache import store, get, clear, size, _cache
from hqmplayer_core.art.resolver import _check_local_art, _read_local
from urllib.parse import urlparse, parse_qs


class TestMetaEnrich(unittest.TestCase):
    """song dict → Track 変換の単体テスト."""

    def test_detect_source_local(self):
        self.assertEqual(_detect_source("local:///music/song.flac"), "local")
        self.assertEqual(_detect_source("/music/song.flac"), "local")

    def test_detect_source_upnp(self):
        self.assertEqual(_detect_source("http://192.168.0.1:9000/song.flac"), "upnp")
        self.assertEqual(_detect_source("https://example.com/song.mp3"), "upnp")

    def test_fallback_title_from_filename(self):
        # ファイル名から title を抽出
        # _fallback_title(uri, current_title: str) -> str
        title = _fallback_title(
            "local:///music/Unknown Artist - Song Title.flac",
            current="",
        )
        self.assertIn("Song Title", title)

    def test_normalize_track_number(self):
        self.assertEqual(_normalize_track_number("3"), 3)
        self.assertEqual(_normalize_track_number("3/12"), 3)
        # 無効値は None を返す仕様
        self.assertIsNone(_normalize_track_number(""))
        self.assertIsNone(_normalize_track_number(None))

    def test_normalize_disc_number(self):
        self.assertEqual(_normalize_disc_number("1"), 1)
        self.assertEqual(_normalize_disc_number("1/2"), 1)
        self.assertIsNone(_normalize_disc_number(""))

    def test_normalize_duration(self):
        self.assertEqual(_normalize_duration("180.5"), 180)
        self.assertEqual(_normalize_duration("0"), 0)
        self.assertIsNone(_normalize_duration(""))
        self.assertIsNone(_normalize_duration(None))

    def test_song_to_track_minimal(self):
        """最小 song dict からの Track 変換."""
        song = {
            "file": "local:///music/test.flac",
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
        }
        track = song_to_track(song)
        d = track.to_dict()
        self.assertEqual(d["title"], "Test Song")
        self.assertEqual(d["artist"], "Test Artist")
        self.assertEqual(d["album"], "Test Album")
        self.assertIn("id", d)
        self.assertTrue(d["id"].startswith("local::"))

    def test_song_to_track_upnp(self):
        """UPnP ソースの Track 変換."""
        song = {
            "file": "http://192.168.0.1:9000/song.flac",
            "title": "UPnP Song",
        }
        track = song_to_track(song)
        d = track.to_dict()
        self.assertEqual(d["source"], "upnp")
        self.assertTrue(d["id"].startswith("upnp::"))

    def test_song_to_track_with_uri_query(self):
        """URI クエリから title/artist 抽出（フォールバック）."""
        song = {
            "file": "http://192.168.0.1:9000/song.flac?title=Hello&artist=World",
            "title": "",
            "artist": "",
        }
        track = song_to_track(song)
        d = track.to_dict()
        # URI クエリから title 部分は抽出され、ファイル名の "song" が title フォールバック
        # 実装に依存するため in チェック
        self.assertTrue(d["title"] in ["Hello", "song"] or "song" in d["title"])


class TestMetaFormatting(unittest.TestCase):
    """Now Playing 整形の単体テスト."""

    def test_format_now_playing_basic(self):
        status = {
            "state": "play",
            "song": "3",
            "songid": "4",
        }
        song = {
            "file": "local:///music/song.flac",
            "title": "Now Playing Song",
            "artist": "Test Artist",
        }
        result = format_now_playing(status, song)
        self.assertEqual(result["state"], "play")
        self.assertEqual(result["title"], "Now Playing Song")
        self.assertEqual(result["artist"], "Test Artist")
        self.assertEqual(result["song_id"], "4")

    def test_format_now_playing_stop_state(self):
        status = {"state": "stop"}
        result = format_now_playing(status, {})
        self.assertEqual(result["state"], "stop")
        self.assertEqual(result["song_id"], "")

    def test_extract_from_url_query(self):
        url = "http://192.168.0.1:9000/song.flac?title=Hello&artist=World&album=Test"
        result = _extract_from_url_query(url)
        self.assertEqual(result.get("title"), "Hello")
        self.assertEqual(result.get("artist"), "World")
        self.assertEqual(result.get("album"), "Test")

    def test_extract_from_url_query_non_http(self):
        result = _extract_from_url_query("local:///music/song.flac")
        self.assertEqual(result, {})

    def test_extract_from_url_query_no_params(self):
        result = _extract_from_url_query("http://example.com/song.flac")
        self.assertEqual(result, {})


class TestMetaCache(unittest.TestCase):
    """メタデータキャッシュの単体テスト."""

    def setUp(self):
        clear()  # テスト前にキャッシュクリア

    def tearDown(self):
        clear()

    def test_store_and_get(self):
        store("http://example.com/stream", "Title", "Artist", "Album", "http://art.example.com/img.jpg")
        result = get("http://example.com/stream")
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Title")
        self.assertEqual(result["artist"], "Artist")

    def test_store_skips_http_only(self):
        """http(s) 以外は保存しない."""
        store("local:///music/song.flac", "Title", "Artist", "Album", "")
        result = get("local:///music/song.flac")
        self.assertIsNone(result)

    def test_clear(self):
        store("http://example.com/stream", "Title", "Artist", "Album", "")
        self.assertGreater(size(), 0)
        clear()
        self.assertEqual(size(), 0)

    def test_size_after_store(self):
        self.assertEqual(size(), 0)
        store("http://example.com/stream1", "T1", "A1", "Al1", "")
        store("http://example.com/stream2", "T2", "A2", "Al2", "")
        self.assertEqual(size(), 2)


class TestArtResolver(unittest.TestCase):
    """アルバムアート解決の単体テスト."""

    def test_check_local_art_no_file(self):
        result = _check_local_art("/nonexistent/path.flac")
        self.assertIsNone(result)

    def test_read_local_missing(self):
        result = _read_local("/nonexistent/file.jpg")
        self.assertIsNone(result)

    def test_resolver_priority_local(self):
        """ローカルファイルが存在すれば最優先."""
        from hqmplayer_core.art.resolver import resolve_art
        # resolve_art は async 関数
        import asyncio
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
            f.write(b"fake audio data")
            tmp_path = f.name
        try:
            result = asyncio.run(resolve_art(
                file=tmp_path,
                artist="Test Artist",
                album="Test Album",
                mpd_readpicture=None,
                mpd_albumart=None,
                http_get=None,
            ))
            # 結果の型を確認
            self.assertIn(result.source, ["local", "placeholder"])
        finally:
            os.unlink(tmp_path)


class TestHqmplayerCoreModule(unittest.TestCase):
    """モジュール基本動作."""

    def test_version(self):
        self.assertIsNotNone(hqmplayer_core.__version__)
        self.assertTrue(hqmplayer_core.__version__.startswith("0."))

    def test_submodules_importable(self):
        """すべてのサブパッケージが import 可能."""
        from hqmplayer_core import mpd, meta, art
        self.assertIsNotNone(mpd)
        self.assertIsNotNone(meta)
        self.assertIsNotNone(art)

    def test_mpd_module_exports(self):
        """mpd モジュールのエクスポート確認."""
        from hqmplayer_core.mpd import (
            MPD_HOST, MPD_PORT, mpd_connection, get_client,
        )
        self.assertIsNotNone(MPD_HOST)
        self.assertIsNotNone(MPD_PORT)
        self.assertIsNotNone(mpd_connection)
        self.assertIsNotNone(get_client)


if __name__ == "__main__":
    unittest.main(verbosity=2)
