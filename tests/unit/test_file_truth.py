#!/usr/bin/env python3
"""ファイル真理 (追加 Step / 決定 D-7) の単体テスト.

検証対象:
- hqmplayer_core.meta.filetruth:
  - ffprobe 未導入環境での静かな無効化 (R-11: available=False)
  - MPD URI → ローカルパス解決 (相対=music_directory 結合 / 絶対 / http 除外)
  - ffprobe JSON → 正規化 dict (FLAC / MP3 / DSD)
  - 表示文字列化 (format_file_truth): DSD64 / MP3 kbps / FLAC kHz-bit
  - キャッシュ (mtime 一致で再利用)
- hq_api/routers/info.py: GET /api/info/file_truth 応答形式

ffprobe が導入済みの環境では実ファイル解析も検証する (未導入なら
モックのみ — 両環境でテストは緑)。

実行:
  python3 -m unittest tests.unit.test_file_truth -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PROJ = Path(__file__).resolve().parents[2]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from hqmplayer_core.meta import filetruth


class ResolveLocalPathTest(unittest.TestCase):
    """MPD URI → ローカル絶対パス解決。"""

    def test_http_uri_excluded(self):
        """UPnP (http/https) は対象外 (ローカルファイルでない)。"""
        self.assertIsNone(filetruth._resolve_local_path("http://example.com/a.flac"))
        self.assertIsNone(filetruth._resolve_local_path("https://example.com/a.flac"))

    def test_empty_uri(self):
        self.assertIsNone(filetruth._resolve_local_path(""))

    def test_relative_joins_music_dir(self):
        """相対パスは music_directory と結合 (存在チェック付き)。"""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "sub" / "a.flac"
            f.parent.mkdir(exist_ok=True)
            f.write_bytes(b"x")
            with mock.patch.object(filetruth, "MUSIC_DIR", td):
                self.assertEqual(
                    filetruth._resolve_local_path("sub/a.flac"),
                    str(f))

    def test_relative_missing_returns_none(self):
        with mock.patch.object(filetruth, "MUSIC_DIR", "/nonexistent"):
            self.assertIsNone(filetruth._resolve_local_path("nope.flac"))

    def test_absolute_existing(self):
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tf:
            try:
                self.assertEqual(filetruth._resolve_local_path(tf.name), tf.name)
            finally:
                os.unlink(tf.name)

    def test_absolute_missing_returns_none(self):
        self.assertIsNone(filetruth._resolve_local_path("/nonexistent/a.flac"))


class ParseProbeTest(unittest.TestCase):
    """ffprobe JSON → 正規化 dict。"""

    def test_flac_parse(self):
        probe = {
            "format": {"format_name": "flac", "bit_rate": "2116000",
                       "duration": "180.5", "tags": {"TITLE": "T", "IGNORED": "x"}},
            "streams": [{
                "codec_type": "audio", "codec_name": "flac",
                "codec_long_name": "FLAC (Free Lossless Audio Codec)",
                "sample_rate": "96000", "bits_per_raw_sample": "24",
                "channels": 2,
            }],
        }
        t = filetruth._parse_probe(probe)
        self.assertEqual(t["codec"], "flac")
        self.assertFalse(t["is_dsd"])
        self.assertEqual(t["sample_rate_hz"], 96000)
        self.assertEqual(t["bits"], 24)
        self.assertEqual(t["channels"], 2)
        self.assertEqual(t["bit_rate"], 2116000)
        self.assertEqual(t["duration_s"], 180.5)
        # tags は ENCODER/LANGUAGE/TITLE/ARTIST/ALBUM のみ
        self.assertEqual(t["tags"], {"title": "T"})

    def test_dsf_parse(self):
        """DSD: .dsf は codec=dsd で返る → is_dsd=True。"""
        probe = {
            "format": {"format_name": "dsf", "duration": "200.1"},
            "streams": [{
                "codec_type": "audio", "codec_name": "dsd",
                "sample_rate": "2822400", "channels": 2,
            }],
        }
        t = filetruth._parse_probe(probe)
        self.assertTrue(t["is_dsd"])
        self.assertEqual(t["sample_rate_hz"], 2822400)
        self.assertIsNone(t["bits"])  # DSD にビット深度は無い

    def test_mp3_parse(self):
        probe = {
            "format": {"format_name": "mp3", "bit_rate": "320000"},
            "streams": [{
                "codec_type": "audio", "codec_name": "mp3",
                "sample_rate": "44100", "bit_rate": "320000", "channels": 2,
            }],
        }
        t = filetruth._parse_probe(probe)
        self.assertEqual(t["codec"], "mp3")
        self.assertEqual(t["bit_rate"], 320000)


class FormatFileTruthTest(unittest.TestCase):
    """表示文字列化 (format_file_truth)。"""

    def test_dsd64(self):
        self.assertEqual(
            filetruth.format_file_truth({"is_dsd": True, "sample_rate_hz": 2822400}),
            "DSD64 2.82MHz / 1-bit")

    def test_dsd128(self):
        self.assertEqual(
            filetruth.format_file_truth({"is_dsd": True, "sample_rate_hz": 5644800}),
            "DSD128 5.64MHz / 1-bit")

    def test_mp3_bitrate(self):
        """MP3 はビット深度ではなくビットレートが真理。"""
        self.assertEqual(
            filetruth.format_file_truth({"codec": "mp3", "bit_rate": 320000}),
            "MP3 320 kbps")

    def test_flac_resolution(self):
        self.assertEqual(
            filetruth.format_file_truth(
                {"codec": "flac", "sample_rate_hz": 96000, "bits": 24}),
            "FLAC 96kHz / 24-bit")

    def test_flac_441(self):
        """44.1kHz は「44.1kHz」表記 (.0 を落とす)。"""
        self.assertEqual(
            filetruth.format_file_truth(
                {"codec": "flac", "sample_rate_hz": 44100, "bits": 16}),
            "FLAC 44.1kHz / 16-bit")

    def test_empty(self):
        self.assertEqual(filetruth.format_file_truth(None), "")
        self.assertEqual(filetruth.format_file_truth({}), "")


class ProbeFileTest(unittest.TestCase):
    """probe_file の統合動作 (ffprobe 導入有無で両方を検証)。"""

    def test_ffprobe_unavailable_returns_none(self):
        """R-11: ffprobe 未導入なら None (例外ではなく静かな省略)。"""
        with mock.patch.object(filetruth, "ffprobe_available", return_value=False):
            self.assertIsNone(filetruth.probe_file("anything.flac"))

    def test_not_local_returns_none(self):
        with mock.patch.object(filetruth, "ffprobe_available", return_value=True):
            self.assertIsNone(filetruth.probe_file("http://x/y.flac"))

    def test_probe_with_mocked_ffprobe(self):
        """ffprobe 応答をモックし URI→解析→キャッシュまでを通し検証。"""
        flac_probe = {
            "format": {"format_name": "flac", "bit_rate": "905000"},
            "streams": [{
                "codec_type": "audio", "codec_name": "flac",
                "sample_rate": "44100", "bits_per_raw_sample": "16",
                "channels": 2,
            }],
        }
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "a.flac"
            f.write_bytes(b"x")
            cache_dir = Path(td) / "cache"
            with mock.patch.object(filetruth, "MUSIC_DIR", td), \
                 mock.patch.object(filetruth, "_CACHE_DIR", cache_dir), \
                 mock.patch.object(filetruth, "ffprobe_available", return_value=True), \
                 mock.patch.object(filetruth, "_run_ffprobe", return_value=flac_probe) as m:
                t1 = filetruth.probe_file("a.flac")
                self.assertIsNotNone(t1)
                self.assertEqual(t1["codec"], "flac")
                self.assertEqual(t1["sample_rate_hz"], 44100)
                # 2 回目はキャッシュから (_run_ffprobe は追加で呼ばれない)
                t2 = filetruth.probe_file("a.flac")
                self.assertEqual(t1, t2)
                self.assertEqual(m.call_count, 1)
                # キャッシュファイルが実在
                self.assertTrue(any(cache_dir.glob("*.json")))

    def test_probe_failure_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "a.flac"
            f.write_bytes(b"x")
            with mock.patch.object(filetruth, "MUSIC_DIR", td), \
                 mock.patch.object(filetruth, "ffprobe_available", return_value=True), \
                 mock.patch.object(filetruth, "_run_ffprobe", return_value=None):
                self.assertIsNone(filetruth.probe_file("a.flac"))


@unittest.skipUnless(filetruth.ffprobe_available(), "ffprobe 未導入")
class ProbeFileRealTest(unittest.TestCase):
    """実 ffprobe による検証 (導入環境のみ)。"""

    def test_real_flac(self):
        """実 FLAC ファイルを生成して解析 (ffmpeg が導入されていれば可能)。"""
        import shutil
        import subprocess
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg CLI 未導入")
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "a.wav"
            out = Path(td) / "a.flac"
            # 1 秒の 44.1kHz/16bit サイン波 WAV を Python で生成
            import wave
            import math
            with wave.open(str(wav), "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                frames = b"".join(
                    int(12000 * math.sin(2 * math.pi * 440 * i / 44100)).to_bytes(2, "little", signed=True) * 2
                    for i in range(44100))
                wf.writeframes(frames)
            subprocess.run(["ffmpeg", "-y", "-i", str(wav), str(out)],
                           check=True, capture_output=True)
            t = filetruth.probe_file(str(out))
            self.assertIsNotNone(t)
            self.assertEqual(t["codec"], "flac")
            self.assertEqual(t["sample_rate_hz"], 44100)
            self.assertEqual(t["bits"], 16)


class FileTruthEndpointTest(unittest.TestCase):
    """GET /api/info/file_truth の応答形式 (関数直呼び)。"""

    def test_unavailable_response(self):
        from hq_api.routers import info
        with mock.patch("hqmplayer_core.meta.filetruth.ffprobe_available",
                        return_value=False):
            out = info.get_file_truth("a.flac")
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], "ffprobe_not_installed")

    def test_not_local_response(self):
        from hq_api.routers import info
        with mock.patch("hqmplayer_core.meta.filetruth.ffprobe_available",
                        return_value=True), \
             mock.patch("hqmplayer_core.meta.filetruth.probe_file",
                        return_value=None):
            out = info.get_file_truth("http://x/y.flac")
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], "not_a_local_file")

    def test_available_response(self):
        from hq_api.routers import info
        truth = {"codec": "flac", "sample_rate_hz": 96000, "bits": 24,
                 "is_dsd": False, "bit_rate": None, "channels": 2}
        with mock.patch("hqmplayer_core.meta.filetruth.ffprobe_available",
                        return_value=True), \
             mock.patch("hqmplayer_core.meta.filetruth.probe_file",
                        return_value=truth):
            out = info.get_file_truth("a.flac")
        self.assertTrue(out["available"])
        self.assertEqual(out["truth"]["codec"], "flac")
        self.assertEqual(out["truth"]["sample_rate_hz"], 96000)


if __name__ == "__main__":
    unittest.main()
