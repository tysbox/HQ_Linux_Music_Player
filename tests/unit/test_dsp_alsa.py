"""backend.dsp.alsa (ALSA 検出の単一ソース) の単体テスト.

v3.1: yaml_generator.py と hq_api/routers/dsp.py の二重実装を
backend/dsp/alsa.py に集約したことの品質保証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_alsa -v
"""
import unittest
from unittest.mock import patch

from backend.dsp import alsa


class TestAlsaCardDetection(unittest.TestCase):
    def tearDown(self):
        alsa.reset_cache()

    def test_detect_returns_none_when_aplay_missing(self):
        with patch.object(alsa.shutil, "which", return_value=None):
            self.assertEqual(alsa.detect_alsa_cards(force=True), (None, None))

    def test_detect_parses_usb_and_pch(self):
        sample = "\n".join([
            "card 1: PCH [HDA Intel PCH], device 0: ALC298 Analog [ALC298 Analog]",
            "card 2: AUDIO [USB Audio], device 0: USB Audio [USB Audio]",
            "card 3: HDMI [HDA Intel HDMI], device 3: HDMI 0 [HDMI 0]",
        ])
        fake = unittest.mock.MagicMock(stdout=sample)
        with patch.object(alsa.shutil, "which", return_value="/usr/bin/aplay"), \
             patch.object(alsa.subprocess, "run", return_value=fake):
            usb, pch = alsa.detect_alsa_cards(force=True)
        self.assertEqual(usb, "2")
        self.assertEqual(pch, "1")  # HDMI 行は除外されること

    def test_detect_cache_hit_within_ttl(self):
        calls = {"n": 0}

        def fake_run(*a, **k):
            calls["n"] += 1
            return unittest.mock.MagicMock(stdout="")

        with patch.object(alsa.shutil, "which", return_value="/usr/bin/aplay"), \
             patch.object(alsa.subprocess, "run", side_effect=fake_run):
            alsa.detect_alsa_cards(force=True)
            alsa.detect_alsa_cards()  # キャッシュヒット (subprocess 不要)
            alsa.detect_alsa_cards()
        self.assertEqual(calls["n"], 1)

    def test_extract_alsa_card_number(self):
        self.assertEqual(alsa.extract_alsa_card_number("plughw:2,0"), "2")
        self.assertEqual(alsa.extract_alsa_card_number("hw:1,0"), "1")
        self.assertIsNone(alsa.extract_alsa_card_number("bluealsa"))
        self.assertIsNone(alsa.extract_alsa_card_number(""))

    def test_is_usb_device(self):
        fake = unittest.mock.MagicMock(stdout="card 2: AUDIO [USB Audio], device 0: USB Audio")
        with patch.object(alsa.shutil, "which", return_value="/usr/bin/aplay"), \
             patch.object(alsa.subprocess, "run", return_value=fake):
            self.assertTrue(alsa.is_usb_device("plughw:2,0"))
            self.assertFalse(alsa.is_usb_device("plughw:1,0"))
            self.assertFalse(alsa.is_usb_device("bluealsa"))

    def test_parse_playback_formats_ignores_capture_formats(self):
        stream_info = """\
Playback:
  Formats: S16_LE S24_LE
Capture:
  Formats: S32_LE
"""
        self.assertEqual(
            alsa.parse_playback_formats(stream_info),
            ("S24_LE", "S16_LE"),
        )

    def test_get_supported_playback_formats_reads_stream_files(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            card_dir = Path(temp_dir) / "card2"
            card_dir.mkdir()
            (card_dir / "stream0").write_text(
                "Playback:\n  Formats: S16_LE S24_3LE S32_LE\n",
                encoding="utf-8",
            )

            self.assertEqual(
                alsa.get_supported_playback_formats("2", temp_dir),
                ("S32_LE", "S24_3LE", "S16_LE"),
            )

    def test_preferred_playback_format_downgrades_to_best_supported(self):
        self.assertEqual(
            alsa.preferred_playback_format(("S24_LE", "S16_LE")),
            "S24_4_LE",
        )
        self.assertEqual(
            alsa.preferred_playback_format(("S16_LE",)),
            "S16_LE",
        )
        self.assertEqual(alsa.preferred_playback_format(None), "S32_LE")


if __name__ == "__main__":
    unittest.main()
