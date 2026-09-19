#!/usr/bin/env python3
"""DSP プロファイルテスト（Stage 3-2: ローダと検証）

スキーマ検証、ローダ、プロファイル→Biquad変換を検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_profiles -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.profiles import (
    validate_profile,
    load_profile,
    list_profiles,
    profile_to_biquads,
    ensure_profiles_dir,
)


# ─────────────────────────────────────────────────────────────────────────────
# テスト用サンプルプロファイル（各テストでコピーして使用）
# ─────────────────────────────────────────────────────────────────────────────
def _make_valid_profile() -> dict:
    return {
        "schema_version": 1,
        "id": "test-headphone",
        "type": "headphone",
        "name": "Test Headphone",
        "source": "Test measurement",
        "purpose": "device_correction",
        "preamp_db": -2.0,
        "bands": [
            {"type": "peaking", "freq": 100, "q": 0.7, "gain": 3.0},
            {"type": "peaking", "freq": 1000, "q": 1.0, "gain": -2.0},
            {"type": "lowshelf", "freq": 200, "q": 0.707, "gain": 2.0},
        ],
        "target_curve": "harman_2018",
        "notes": "Test profile"
    }


def _make_invalid_missing_field() -> dict:
    return {
        "schema_version": 1,
        "id": "test",
        "name": "Test",
        "source": "Test",
        "purpose": "device_correction",
        "preamp_db": 0.0,
        "bands": []
    }


def _make_invalid_q_zero() -> dict:
    return {
        "schema_version": 1,
        "id": "test",
        "type": "headphone",
        "name": "Test",
        "source": "Test",
        "purpose": "device_correction",
        "preamp_db": 0.0,
        "bands": [
            {"type": "peaking", "freq": 1000, "q": 0.0, "gain": 3.0},
        ]
    }


def _make_invalid_gain_zero() -> dict:
    return {
        "schema_version": 1,
        "id": "test",
        "type": "headphone",
        "name": "Test",
        "source": "Test",
        "purpose": "device_correction",
        "preamp_db": 0.0,
        "bands": [
            {"type": "peaking", "freq": 1000, "q": 1.0, "gain": 0.0},
        ]
    }


def _make_invalid_freq_out_of_range() -> dict:
    return {
        "schema_version": 1,
        "id": "test",
        "type": "headphone",
        "name": "Test",
        "source": "Test",
        "purpose": "device_correction",
        "preamp_db": 0.0,
        "bands": [
            {"type": "peaking", "freq": 100000, "q": 1.0, "gain": 3.0},
        ]
    }


def _make_invalid_excessive_boost() -> dict:
    return {
        "schema_version": 1,
        "id": "test",
        "type": "headphone",
        "name": "Test",
        "source": "Test",
        "purpose": "device_correction",
        "preamp_db": 0.0,
        "bands": [
            {"type": "peaking", "freq": 100, "q": 1.0, "gain": 10.0},
            {"type": "peaking", "freq": 200, "q": 1.0, "gain": 10.0},
            {"type": "peaking", "freq": 300, "q": 1.0, "gain": 10.0},
        ]
    }


def _make_invalid_preamp_db() -> dict:
    p = _make_valid_profile()
    p["preamp_db"] = 25.0
    return p


class TestProfileValidation(unittest.TestCase):
    """プロファイル検証テスト。"""

    def test_valid_profile_passes(self):
        """有効なプロファイルは検証を通過する。"""
        valid, errors = validate_profile(_make_valid_profile())
        self.assertTrue(valid, f"Valid profile rejected: {errors}")

    def test_missing_required_field_fails(self):
        """必須フィールド欠落は失敗する。"""
        valid, errors = validate_profile(_make_invalid_missing_field())
        self.assertFalse(valid)
        self.assertTrue(len(errors) > 0)

    def test_q_zero_rejected(self):
        """q=0 は peaking/notch/lowpass/highpass で拒否される。"""
        valid, errors = validate_profile(_make_invalid_q_zero())
        self.assertFalse(valid)
        # jsonschema の minimum=0.1 で検出されるか、独自検証で検出される
        self.assertTrue(len(errors) > 0)

    def test_gain_zero_for_peaking_rejected(self):
        """peaking で gain=0 は拒否される。"""
        valid, errors = validate_profile(_make_invalid_gain_zero())
        self.assertFalse(valid)
        self.assertTrue(any("non-zero gain" in e for e in errors))

    def test_freq_out_of_range_rejected(self):
        """周波数範囲外は拒否される。"""
        valid, errors = validate_profile(_make_invalid_freq_out_of_range())
        self.assertFalse(valid)
        self.assertTrue(any("Hz" in e for e in errors))

    def test_excessive_boost_rejected(self):
        """総ブースト > 20dB は拒否される。"""
        valid, errors = validate_profile(_make_invalid_excessive_boost())
        self.assertFalse(valid)
        self.assertTrue(any("Total positive gain" in e for e in errors))

    def test_preamp_db_range(self):
        """preamp_db 範囲外は拒否される。"""
        valid, errors = validate_profile(_make_invalid_preamp_db())
        self.assertFalse(valid)
        self.assertTrue(any("preamp_db" in e for e in errors))


class TestProfileLoader(unittest.TestCase):
    """プロファイルローダテスト。"""

    def setUp(self):
        ensure_profiles_dir()
        self.temp_dir = tempfile.mkdtemp()
        import backend.dsp.profiles as profiles_module
        self.original_profiles_dir = profiles_module.PROFILES_DIR
        profiles_module.PROFILES_DIR = Path(self.temp_dir)

    def tearDown(self):
        import backend.dsp.profiles as profiles_module
        profiles_module.PROFILES_DIR = self.original_profiles_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_nonexistent_returns_none(self):
        """存在しないプロファイルは None を返す。"""
        result = load_profile("nonexistent")
        self.assertIsNone(result)

    def test_load_valid_profile(self):
        """有効なプロファイルファイルを読み込める。"""
        path = Path(self.temp_dir) / "test-headphone.json"
        with open(path, "w") as f:
            json.dump(_make_valid_profile(), f)
        
        result = load_profile("test-headphone")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "test-headphone")
        self.assertEqual(result["name"], "Test Headphone")

    def test_load_invalid_profile_returns_none(self):
        """無効なプロファイルファイルは None を返す。"""
        path = Path(self.temp_dir) / "invalid.json"
        with open(path, "w") as f:
            json.dump(_make_invalid_q_zero(), f)
        
        result = load_profile("invalid")
        self.assertIsNone(result)

    def test_list_profiles(self):
        """プロファイル一覧が取得できる。"""
        path1 = Path(self.temp_dir) / "profile1.json"
        path2 = Path(self.temp_dir) / "profile2.json"
        with open(path1, "w") as f:
            json.dump(_make_valid_profile(), f)
        profile2 = _make_valid_profile()
        profile2["id"] = "profile2"
        profile2["name"] = "Profile 2"
        with open(path2, "w") as f:
            json.dump(profile2, f)
        
        profiles = list_profiles()
        self.assertEqual(len(profiles), 2)
        ids = {p["id"] for p in profiles}
        self.assertEqual(ids, {"test-headphone", "profile2"})


class TestProfileToBiquads(unittest.TestCase):
    """プロファイル→Biquad変換テスト。"""

    def test_conversion_basic(self):
        """基本的な変換が正しく動作する。"""
        biquads = profile_to_biquads(_make_valid_profile())
        self.assertEqual(len(biquads), 3)
        for bq in biquads:
            self.assertEqual(bq["type"], "Biquad")
            self.assertIn("parameters", bq)
            params = bq["parameters"]
            self.assertIn("type", params)
            self.assertIn("freq", params)
            self.assertIn("q", params)
            self.assertIn("gain", params)

    def test_type_mapping(self):
        """タイプマッピングが正しい（peaking→Peaking等）。"""
        biquads = profile_to_biquads(_make_valid_profile())
        types = [bq["parameters"]["type"] for bq in biquads]
        self.assertIn("Peaking", types)
        self.assertIn("LowShelf", types)

    def test_unknown_type_skipped(self):
        """未知タイプはスキップされる。"""
        profile = _make_valid_profile()
        profile["bands"].append({"type": "unknown", "freq": 1000, "q": 1.0, "gain": 3.0})
        biquads = profile_to_biquads(profile)
        self.assertEqual(len(biquads), 3)  # unknown は除外


if __name__ == "__main__":
    unittest.main()
