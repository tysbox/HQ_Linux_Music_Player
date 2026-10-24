#!/usr/bin/env python3
"""Phase 2 (Info機能 = LISTENING WIKI) の単体テスト.

Bisen Android の 3 ソース統合 (MusicBrainz + Discogs + Wikipedia) 移植の検証。
実 API は叩かない (全て fixture)。非破壊。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_phase2_info -v
"""
import asyncio
import os
import sys
import tempfile
import unittest
from unittest import mock

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from hq_api.routers import info as info_mod  # noqa: E402
from hq_api.ws import levels as levels_mod  # noqa: E402
from hq_api.ws import status as status_mod  # noqa: E402


class _Resp:
    def __init__(self, payload, code=200):
        self._payload = payload
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


# ─────────────────────────────────────────────────────────────────────────────
# MetadataParser 移植の検証
# ─────────────────────────────────────────────────────────────────────────────
class TestParsers(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(info_mod._sanitize("Song (Remastered)"), "Song")
        self.assertEqual(info_mod._sanitize("Unknown Artist"), "")
        self.assertEqual(info_mod._sanitize("file$1"), "")
        self.assertEqual(info_mod._sanitize("various"), "")

    def test_normalize_title(self):
        self.assertEqual(
            info_mod._normalize_title("Song (2011 Remaster)"), "Song")

    def test_classify_dedup(self):
        t = {}
        info_mod._classify_credits(t, "producers", "Davis, M.")
        # "Miles Davis" のハッシュ "davis, m" は既存文字列 "davis, m." に
        # 含まれるため重複排除される (Bisen getCreditHash と同一の挙動)
        info_mod._classify_credits(t, "producers", "Miles Davis")
        info_mod._classify_credits(t, "producers", "Teo Macero")
        self.assertEqual(t["producers"], "Davis, M., Teo Macero")

    def test_parse_relations_categories(self):
        detail = {"relations": [
            {"type": "producer", "target-type": "artist",
             "artist": {"name": "Teo Macero"}},
            {"type": "engineer", "target-type": "artist",
             "artist": {"name": "Fred Plaut"}},
            {"type": "instrument", "target-type": "artist",
             "attributes": ["trumpet"], "artist": {"name": "Miles Davis"}},
            {"type": "writer", "target-type": "artist",
             "artist": {"name": "Miles Davis"}},
            # work-target の関係は "artist" キーを持たない → 除外 (Bisen と同一)
            {"target-type": "work", "type": "producer",
             "work": {"title": "Some Work"}},
        ]}
        t = {}
        info_mod._parse_relations(detail, t)
        self.assertEqual(t["producers"], "Teo Macero")
        self.assertEqual(t["engineers"], "Fred Plaut")
        self.assertEqual(t["performers"], "Miles Davis (trumpet)")
        self.assertEqual(t["composers"], "Miles Davis")

    def test_infobox_facts(self):
        wikitext = ("{{Infobox album\n| name = Kind of Blue\n"
                    "| producer = [[Teo Macero]]\n| studio = [[30th Street Studio]]"
                    "<ref>x</ref>\n| recorded = 1959\n| genre = Jazz\n}}")
        t = {}
        info_mod._parse_infobox_facts(wikitext, t)
        self.assertEqual(t["producers"], "Teo Macero")
        self.assertEqual(t["studios"], "30th Street Studio")
        self.assertEqual(t["recordedAt"], "1959")
        self.assertEqual(t["genre"], "Jazz")

    def test_ranked_merge_precedence(self):
        target = {}
        info_mod._ranked_merge(target, {"producers": "Wiki Guy"}, info_mod.RANK_WIKI)
        info_mod._ranked_merge(target, {"producers": "Discogs Guy"}, info_mod.RANK_DISCOGS)
        info_mod._ranked_merge(target, {"producers": "MB Guy"}, info_mod.RANK_MB)
        self.assertEqual(target["producers"], "MB Guy")
        # 低ランクは高ランクを上書きしない
        info_mod._ranked_merge(target, {"producers": "Album Guy"}, info_mod.RANK_ALBUM)
        self.assertEqual(target["producers"], "MB Guy")
        # 空値は上書きしない
        info_mod._ranked_merge(target, {"producers": ""}, info_mod.RANK_MB)


# ─────────────────────────────────────────────────────────────────────────────
# Discogs 移植の検証
# ─────────────────────────────────────────────────────────────────────────────
DISCOGS_MASTER = {
    "extraartists": [
        {"name": "Teo Macero", "role": "Producer"},
        {"name": "Fred Plaut", "role": "Recording Engineer"},
        {"name": "Bill Evans", "role": "Piano"},
        {"name": "Paul Chambers", "role": "Bass"},
        {"name": "Jimmy Cobb", "role": "Drums"},
        {"name": "John Coltrane", "role": "Saxophone"},
    ],
    "artists": [{"name": "Miles Davis", "anv": ""}],
    "labels": [{"name": "Columbia", "catno": "CL 1355"}],
    "formats": [{"name": "Vinyl", "descriptions": ["LP", "Mono"]}],
    "genres": ["Jazz"],
    "styles": ["Modal"],
    "year": 1959,
    "country": "US",
    "master_id": 12345,
    "id": 67890,
    "uri": "https://www.discogs.com/master/12345",
}


class TestDiscogs(unittest.TestCase):
    def test_normalize_role(self):
        f = info_mod._discogs_normalize_role
        self.assertEqual(f("Producer"), "producer")
        self.assertEqual(f("Mixed By"), "mixing_engineer")
        self.assertEqual(f("Trumpet"), "trumpet")
        self.assertEqual(f("Electric Bass"), "bass")
        self.assertEqual(f("Violin"), "violin")
        self.assertEqual(f("Artwork"), "artwork")
        self.assertEqual(f("Weird Role"), "other")

    def test_extract_credits(self):
        c = info_mod._discogs_extract_credits(DISCOGS_MASTER)
        # "Recording Engineer" は Bisen と同じ判定順序で "engineer" に分類される
        self.assertEqual(c["producer"], "Teo Macero")
        self.assertEqual(c["engineer"], "Fred Plaut")
        self.assertEqual(c["keyboards"], "Bill Evans")
        self.assertEqual(c["bass"], "Paul Chambers")
        self.assertEqual(c["drums"], "Jimmy Cobb")
        self.assertEqual(c["saxophone"], "John Coltrane")
        self.assertEqual(c["artist"], "Miles Davis")
        self.assertEqual(c["label"], "Columbia (CL 1355)")
        self.assertIn("Vinyl", c["format"])
        self.assertEqual(c["genre"], "Jazz")
        self.assertEqual(c["year"], "1959")
        self.assertEqual(c["discogs_release_id"], "67890")

    def test_score_match(self):
        r = {"artist": "Miles Davis", "title": "Kind of Blue",
             "master_id": 12345, "year": 1959}
        score = info_mod._discogs_score_match(
            r, "Miles Davis", "So What", "Kind of Blue")
        # artist 40 + album 20 + master 10 + year 5 = 75
        self.assertEqual(score, 75)
        low = info_mod._discogs_score_match(
            {"artist": "Someone Else", "title": "Unrelated",
             "master_id": 0, "year": 0},
            "Miles Davis", "So What", "Kind of Blue")
        self.assertEqual(low, 0)

    def test_levenshtein(self):
        self.assertEqual(info_mod._levenshtein("kitten", "sitting"), 3)
        self.assertEqual(info_mod._levenshtein("abc", "abc"), 0)


# ─────────────────────────────────────────────────────────────────────────────
# 統合パイプライン (モック) の検証
# ─────────────────────────────────────────────────────────────────────────────
MB_SEARCH = {"recordings": [{
    "id": "mbid-1", "score": 99, "title": "So What", "length": 562000,
    "artist-credit": [{"artist": {"name": "Miles Davis"}, "joinphrase": ""}],
}]}
MB_REC_DETAIL = {
    "id": "mbid-1", "title": "So What",
    "artist-credit": [{"artist": {"name": "Miles Davis"}, "joinphrase": ""}],
    "relations": [
        {"type": "producer", "target-type": "artist",
         "artist": {"name": "Teo Macero"}},
        {"type": "instrument", "target-type": "artist",
         "attributes": ["trumpet"], "artist": {"name": "Miles Davis"}},
    ],
    "releases": [{"id": "rel-1", "title": "Kind of Blue"}],
}
MB_RELEASE = {
    "id": "rel-1", "title": "Kind of Blue", "date": "1959-08-17",
    "country": "US",
    "label-info": [{"label": {"name": "Columbia"}}],
    "url-rels": [
        {"type": "discogs",
         "target": "https://www.discogs.com/master/12345-Kind-Of-Blue"},
    ],
    "relations": [],
}
WIKI_ALBUM_SEARCH = {"query": {"search": [{"title": "Kind of Blue"}]}}
WIKI_ALBUM_PARSE = {"parse": {"wikitext":
    "{{Infobox album| producer = Teo Macero| studio = 30th Street Studio}}"}}
WIKI_ALBUM_EXTRACT = {"query": {"pages": [
    {"extract": "Kind of Blue is a studio album by Miles Davis."}]}}
WIKI_BIO_SEARCH = {"query": {"search": [
    {"title": "Miles Davis",
     "snippet": "Miles Dewey Davis III was an American jazz trumpeter"}]}}
WIKI_BIO_EXTRACT = {"query": {"pages": [
    {"extract": "Miles Davis was an American jazz trumpeter, bandleader, "
                "and composer."}]}}


def _mock_metadata_get(url, params=None, headers=None, timeout=None):
    """URL ディスパッチ式の fixture 応答 (実 API 叩かない)。
    注: urllib.parse.quote はスペースを %20 にする点に注意。"""
    def _has_miles(u):
        return any(t in u for t in ("Miles+Davis", "Miles_Davis",
                                    "Miles%20Davis"))

    if "musicbrainz.org" in url:
        if "/recording/mbid-1" in url:
            return _Resp(MB_REC_DETAIL)
        if "/recording" in url:
            return _Resp(MB_SEARCH)
        if "/release/rel-1" in url:
            return _Resp(MB_RELEASE)
        return _Resp({"recordings": []})
    if "wikipedia.org" in url:
        if "action=parse" in url:
            return _Resp(WIKI_ALBUM_PARSE)
        if "prop=extracts" in url:
            if _has_miles(url):
                return _Resp(WIKI_BIO_EXTRACT)
            return _Resp(WIKI_ALBUM_EXTRACT)
        # 検索: アルバム記事クエリ ("Kind of Blue ... album") を先に判別
        if "Kind%20of%20Blue" in url or "Kind+of+Blue" in url:
            return _Resp(WIKI_ALBUM_SEARCH)
        if "musician" in url or "band" in url or "singer" in url:
            return _Resp({"query": {"search": []}})
        if _has_miles(url):
            return _Resp(WIKI_BIO_SEARCH)
        return _Resp(WIKI_ALBUM_SEARCH)
    if "discogs" in url:
        if "/masters/" in url or "/releases/" in url:
            return _Resp(DISCOGS_MASTER)
        return _Resp({"results": []})
    return _Resp({})


class TestFullPipeline(unittest.TestCase):
    """_fetch_credits: Tier 1-5 の統合とランク優先の検証。"""

    def _fetch(self):
        with mock.patch.object(info_mod.requests, "get",
                               side_effect=_mock_metadata_get), \
             mock.patch.object(info_mod.time, "sleep", lambda s: None):
            return info_mod._fetch_credits(
                "Miles Davis", "So What", "Kind of Blue", 562.0)

    def test_full_pipeline_success(self):
        result = self._fetch()
        self.assertEqual(result["status"], "success")
        c = result["credits"]
        # Tier 1: MB search
        self.assertEqual(c["trackTitle"], "So What")
        self.assertEqual(c["artistName"], "Miles Davis")
        self.assertEqual(c["trackLengthMs"], 562000)
        # Tier 2: MB recording relations (rank MB=3)
        self.assertEqual(c["producers"], "Teo Macero")
        self.assertEqual(c["performers"], "Miles Davis (trumpet)")
        # Tier 3: MB release (label は Discogs rank2 が "Columbia (CL 1355)"
        # で上書きする = Bisen と同一のランク挙動)
        self.assertEqual(c["albumTitle"], "Kind of Blue")
        self.assertEqual(c["label"], "Columbia (CL 1355)")
        self.assertEqual(c["releaseDate"], "1959-08-17")
        self.assertEqual(c["releaseCountry"], "US")
        # Tier 4: Wikipedia
        self.assertTrue(c.get("wikiSummary", "").startswith("Kind of Blue"))
        self.assertIn("jazz trumpeter", c.get("artistBio", ""))
        # Tier 5: Discogs (MB 権威リンク master 12345)
        self.assertEqual(c["keyboards"], "Bill Evans")
        self.assertEqual(c["bass"], "Paul Chambers")
        self.assertEqual(c["drums"], "Jimmy Cobb")
        self.assertEqual(c["saxophone"], "John Coltrane")
        self.assertEqual(c["discogs_release_id"], "67890")

    def test_inc_params_correct(self):
        """recording 詳細の inc は Bisen と同一 (artist-rels 系)。
        旧実装の "artist-relations" (400 Bad Request の原因) でないこと。"""
        calls = []

        def spy_get(url, params=None, headers=None, timeout=None):
            calls.append((url, params))
            return _mock_metadata_get(url, params, headers, timeout)

        with mock.patch.object(info_mod.requests, "get",
                               side_effect=spy_get), \
             mock.patch.object(info_mod.time, "sleep", lambda s: None):
            info_mod._fetch_credits("Miles Davis", "So What", "Kind of Blue", 562.0)
        rec_inc = [p for (u, p) in calls
                   if "/recording/mbid-1" in u][0]["inc"]
        self.assertEqual(
            rec_inc, "artist-rels+work-rels+work-level-rels+place-rels+releases")
        self.assertNotIn("artist-relations", rec_inc)

    def test_mb_empty_yields_minimal_credits(self):
        """MB 検索 0 件 → artistName のみの最小 credits (Bisen resolve と同一)。
        WikiModal は欠損フィールドを "Not catalogued" 表示するため
        status は success のまま扱う。"""
        def empty_get(url, params=None, headers=None, timeout=None):
            if "musicbrainz.org" in url:
                return _Resp({"recordings": []})
            return _Resp({})
        with mock.patch.object(info_mod.requests, "get",
                               side_effect=empty_get), \
             mock.patch.object(info_mod.time, "sleep", lambda s: None):
            result = info_mod._fetch_credits("Nobody", "Nothing", "", 0)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["credits"]["artistName"], "Nobody")
        self.assertNotIn("trackTitle", result["credits"])

    def test_idlike_and_unknown_abort(self):
        result = info_mod._fetch_credits("Unknown Artist", "track$1", "", 0)
        self.assertEqual(result["status"], "not_found")


class TestEndpoint(unittest.TestCase):
    """/api/info/credits エンドポイント (キャッシュ・検証)。"""

    def _get(self, artist="Miles Davis", title="So What"):
        return info_mod.get_credits(
            artist=artist, title=title, album="Kind of Blue", duration=562.0)

    def test_endpoint_caches_result(self):
        with tempfile.TemporaryDirectory(prefix="test_mb2_") as tmp:
            with mock.patch.object(info_mod, "CACHE_DIR", tmp), \
                 mock.patch.object(info_mod.requests, "get",
                                   side_effect=_mock_metadata_get) as get, \
                 mock.patch.object(info_mod.time, "sleep", lambda s: None):
                first = self._get()
                self.assertEqual(first["status"], "success")
                self.assertEqual(first["cached"], False)
                calls_after_first = get.call_count
                second = self._get()
                self.assertEqual(second["cached"], True)
                self.assertEqual(get.call_count, calls_after_first)
                self.assertEqual(len(os.listdir(tmp)), 1)

    def test_endpoint_missing_params_422(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            info_mod.get_credits(artist="", title="x")
        self.assertEqual(ctx.exception.status_code, 422)


# ─────────────────────────────────────────────────────────────────────────────
# levels / status (Phase 2 Step 2-1/2-2) の検証 — 前実装から維持
# ─────────────────────────────────────────────────────────────────────────────
class TestWsLevels(unittest.TestCase):
    def test_read_levels_returns_floats(self):
        class _Levels:
            @staticmethod
            def playback_peak():
                return ["-12.5", "-13.0"]

            @staticmethod
            def playback_rms():
                return [-20.0, -21.0]

        class _FakeClient:
            levels = _Levels()

        result = levels_mod._read_levels(_FakeClient())
        self.assertEqual(result["peak"], [-12.5, -13.0])
        self.assertEqual(result["rms"], [-20.0, -21.0])

    def test_poll_interval_default(self):
        self.assertAlmostEqual(levels_mod.POLL_INTERVAL, 0.1, places=2)


class TestSignalTruth(unittest.TestCase):
    def test_full_status_includes_audio(self):
        class _FakeMpdClient:
            async def status(self):
                return {
                    "state": "play", "audio": "44100:16:2",
                    "elapsed": "10.5", "duration": "200",
                    "playlistlength": "5",
                }

            async def currentsong(self):
                return {}

        data = asyncio.run(status_mod._get_full_status(_FakeMpdClient()))
        self.assertEqual(data["audio"], "44100:16:2")
        for key in ("state", "current_track", "position", "duration",
                    "queue_length", "random", "repeat", "song_id"):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()




