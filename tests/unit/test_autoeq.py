#!/usr/bin/env python3
"""AutoEq パーサ (backend/dsp/autoeq.py) の単体テスト.

Bisen customProfileStorage.ts parseAutoEqText() の Python 移植検証 +
移植改善 (種別 PK/LSC/HSC の解析) の検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_autoeq -v

非破壊: 実 PROFILES_DIR (~/.config/audiophile/profiles) は書き換えない
"""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

# プロジェクトルートをパスに追加
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp import profiles as profiles_mod  # noqa: E402
from backend.dsp.autoeq import (  # noqa: E402
    parse_autoeq_text,
    save_autoeq_profile,
    validate_autoeq_profile,
)

# Bisen customProfileStorage.ts のドキュメント記載例 (docstring のサンプル)
BISEN_SAMPLE = """\
Preamp: -5.4 dB
Filter 1: ON PK Fc 32 Hz Gain 4.8 dB Q 1.41
Filter 2: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.71
Filter 3: ON PK Fc 1400 Hz Gain -1.8 dB Q 2.2
"""

# oratory1990 風の現実的サンプル (種別 3 種混在・正ゲイン合計 10.3dB < 上限 20)
REALISTIC_SAMPLE = """\
Preamp: -5.4 dB
# コメント行 (無視される)
Filter 1: ON PK Fc 32 Hz Gain 4.8 dB Q 1.41
Filter 2: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.71
Filter 3: ON PK Fc 1400 Hz Gain -1.8 dB Q 2.20

Filter 4: ON HSC Fc 10000 Hz Gain -1.0 dB Q 0.71
この行はノイズ (無視される)
"""


class TestParseAutoEqText(unittest.TestCase):
    """parse_autoeq_text の解析検証."""

    def test_parse_bisen_sample(self):
        """Bisen ドキュメント記載例が正しく解析される."""
        p = parse_autoeq_text(BISEN_SAMPLE, name="Bisen Sample")
        self.assertIsNotNone(p)
        self.assertEqual(p["id"], "bisen-sample")
        self.assertEqual(p["type"], "headphone")
        self.assertEqual(p["purpose"], "device_correction")
        self.assertAlmostEqual(p["preamp_db"], -5.4, places=1)
        self.assertEqual(len(p["bands"]), 3)
        b0 = p["bands"][0]
        self.assertEqual(b0, {"type": "peaking", "freq": 32, "q": 1.41, "gain": 4.8})
        b1 = p["bands"][1]
        self.assertEqual(b1["type"], "lowshelf")
        self.assertAlmostEqual(b1["gain"], 5.5, places=1)

    def test_type_capture_improvement(self):
        """移植改善: PK/LSC/HSC が種別として正しく採用される (Bisen は全て peaking 扱い)."""
        p = parse_autoeq_text(REALISTIC_SAMPLE, name="Type Test")
        self.assertIsNotNone(p)
        types = [b["type"] for b in p["bands"]]
        self.assertEqual(types, ["peaking", "lowshelf", "peaking", "highshelf"])

    def test_comments_and_noise_ignored(self):
        """コメント行・空行・ノイズ行は無視される."""
        p = parse_autoeq_text(REALISTIC_SAMPLE, name="Noise Test")
        self.assertIsNotNone(p)
        self.assertEqual(len(p["bands"]), 4)  # 4 行のみ有効

    def test_empty_text_returns_none(self):
        """空テキスト → None."""
        self.assertIsNone(parse_autoeq_text(""))
        self.assertIsNone(parse_autoeq_text("   \n \n"))

    def test_no_filter_lines_returns_none(self):
        """Filter 行が 1 つも無いテキスト → None (Bisen 仕様)."""
        self.assertIsNone(parse_autoeq_text("Preamp: -3.0 dB\n# no filters here\n"))

    def test_band_limit_10(self):
        """バンドは最大 10 個に制限される (Bisen 仕様)."""
        lines = ["Preamp: -2.0 dB"]
        for i in range(12):
            lines.append(f"Filter {i+1}: ON PK Fc {100*(i+1)} Hz Gain 1.0 dB Q 1.0")
        p = parse_autoeq_text("\n".join(lines), name="Limit Test")
        self.assertIsNotNone(p)
        self.assertEqual(len(p["bands"]), 10)

    def test_missing_preamp_defaults_zero(self):
        """Preamp 行なし → preamp_db 0.0."""
        p = parse_autoeq_text(
            "Filter 1: ON PK Fc 1000 Hz Gain 2.0 dB Q 1.0", name="No Preamp")
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["preamp_db"], 0.0, places=1)


class TestAutoEqValidationAndSave(unittest.TestCase):
    """解析結果のスキーマ検証と永続化の検証."""

    def test_parsed_profile_passes_schema(self):
        """現実的サンプルの解析結果がスキーマ + セマンティック検証を通過する."""
        p = parse_autoeq_text(REALISTIC_SAMPLE, name="Realistic Test")
        self.assertIsNotNone(p)
        valid, errors = validate_autoeq_profile(p)
        self.assertTrue(valid, f"validation errors: {errors}")

    def test_save_and_load_roundtrip(self):
        """保存 → load_profile で同一内容が読める (アトミック書込・冪等再保存)."""
        p = parse_autoeq_text(REALISTIC_SAMPLE, name="Roundtrip Test")
        self.assertIsNotNone(p)
        with tempfile.TemporaryDirectory(prefix="test_autoeq_") as tmp:
            with mock.patch.object(
                    profiles_mod, "PROFILES_DIR", pathlib.Path(tmp)):
                # 1 回目の保存
                saved_id = save_autoeq_profile(p)
                self.assertEqual(saved_id, p["id"])
                # 2 回目の保存 (再インポート冪等: 上書きされるだけ)
                saved_id2 = save_autoeq_profile(p)
                self.assertEqual(saved_id2, p["id"])
                # 読み出し一致
                loaded = profiles_mod.load_profile(p["id"])
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded["preamp_db"], p["preamp_db"])
                self.assertEqual(loaded["bands"], p["bands"])
                self.assertEqual(loaded["name"], p["name"])
        # 実 PROFILES_DIR に書き込まれていないこと (非破壊確認)
        self.assertFalse(
            os.path.exists(os.path.join(
                os.path.expanduser("~/.config/audiophile/profiles"),
                "roundtrip-test.json")))

    def test_invalid_profile_not_saved(self):
        """検証失敗プロファイル (正ゲイン合計 > 60dB) は保存されない.

        2026-10-12 改定: device_correction の総ブースト上限は 60dB。
        (旧 20dB 仕様のテストから更新。sound_color の 20dB 検証は
        test_profiles.py が担う)
        """
        lines = ["Preamp: -2.0 dB"]
        for i in range(10):
            lines.append(f"Filter {i+1}: ON PK Fc {100*(i+1)} Hz Gain 7.0 dB Q 1.0")
        p = parse_autoeq_text("\n".join(lines), name="Too Much Boost")
        self.assertIsNotNone(p)
        valid, errors = validate_autoeq_profile(p)
        self.assertFalse(valid)  # 合計 +70dB > 上限 60dB
        with tempfile.TemporaryDirectory(prefix="test_autoeq_") as tmp:
            with mock.patch.object(
                    profiles_mod, "PROFILES_DIR", pathlib.Path(tmp)):
                self.assertIsNone(save_autoeq_profile(p))
                self.assertEqual(os.listdir(tmp), [])  # 何も書かれていない


class TestSlugify(unittest.TestCase):
    """ID 生成 (決定性・日本語名) の検証."""

    def test_slug_deterministic(self):
        """同名 → 同 ID (再インポート冪等)。Bisen のタイムスタンプ乱数方式と違い決定的."""
        p1 = parse_autoeq_text(BISEN_SAMPLE, name="My Headphone")
        p2 = parse_autoeq_text(BISEN_SAMPLE, name="My Headphone")
        self.assertEqual(p1["id"], p2["id"])

    def test_slug_from_mixed_case_name(self):
        """大文字・記号混在の名前 → スキーマ準拠 ID."""
        p = parse_autoeq_text(BISEN_SAMPLE, name="Audio-Technica ATH-M50x")
        self.assertEqual(p["id"], "audio-technica-ath-m50x")

    def test_japanese_name_gets_hash_id(self):
        """日本語名 (スラグ化不能) → ハッシュベースの一意 ID."""
        p = parse_autoeq_text(BISEN_SAMPLE, name="ソニー ヘッドホン")
        self.assertRegex(p["id"], r"^autoeq-[0-9a-f]{8}$")


if __name__ == "__main__":
    unittest.main()
