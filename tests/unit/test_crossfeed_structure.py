#!/usr/bin/env python3
"""Crossfeed 4経路配線構造テスト（Stage 4: 構造検証）

現行の 2→4→2 4経路配線が正しく生成されることを検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_crossfeed_structure -v
"""
import sys
import os
import tempfile
import unittest
import yaml

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.yaml_generator import generate_camilladsp_yaml
from backend.main import AudioConfig


class TestCrossfeedStructure(unittest.TestCase):
    """クロスフィード 4経路配線の構造検証。"""

    def _gen_and_check(self, config_dict: dict) -> dict:
        """設定から YAML 生成し、辞書として返す。"""
        cfg = AudioConfig(**config_dict)
        with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
            tmp_path = f.name
        try:
            generate_camilladsp_yaml(cfg, out_path=tmp_path)
            with open(tmp_path) as f:
                return yaml.safe_load(f)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def test_crossfeed_none_has_no_crossfeed_mixer(self):
        """crossfeed=none のとき cf ミキサーが存在しない。"""
        config_dict = {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "none", "crossfeed_intensity": 5,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
            "loudness_ref": 80.0, "loudness_enabled": False,
        }
        y = self._gen_and_check(config_dict)
        self.assertNotIn("cf", y.get("mixers", {}),
            "crossfeed=none で cf mixer が存在してはならない")
        self.assertNotIn("split4", y.get("mixers", {}))
        self.assertNotIn("sum4", y.get("mixers", {}))
        self.assertNotIn("cf_shade", y.get("filters", {}))
        self.assertNotIn("cf_gain_cross", y.get("filters", {}))

    def test_crossfeed_standard_has_4ch_wiring(self):
        """crossfeed=standard で 4経路配線(split4/sum4)が生成される。"""
        config_dict = {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "standard", "crossfeed_intensity": 50,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
            "loudness_ref": 80.0, "loudness_enabled": False,
        }
        y = self._gen_and_check(config_dict)

        # split4 ミキサー: 2→4
        self.assertIn("split4", y.get("mixers", {}),
            "split4 ミキサーが存在しない")
        split4 = y["mixers"]["split4"]
        self.assertEqual(split4["channels"], {"in": 2, "out": 4})

        # sum4 ミキサー: 4→2
        self.assertIn("sum4", y.get("mixers", {}),
            "sum4 ミキサーが存在しない")
        sum4 = y["mixers"]["sum4"]
        self.assertEqual(sum4["channels"], {"in": 4, "out": 2})

        # パイプライン順序: split4 → Filter → sum4
        pipeline_names = [p.get("name") for p in y["pipeline"] if p.get("name")]
        self.assertIn("split4", pipeline_names)
        self.assertIn("sum4", pipeline_names)
        self.assertTrue(pipeline_names.index("split4") < pipeline_names.index("sum4"))

        # 交差経路用フィルタ
        self.assertIn("cf_shade", y.get("filters", {}),
            "cf_shade フィルタが存在しない")
        self.assertIn("cf_gain_cross", y.get("filters", {}),
            "cf_gain_cross フィルタが存在しない")

        # Filter ステージで cross 経路(ch 2,3) に適用
        filter_stages = [p for p in y["pipeline"] if p.get("type") == "Filter"]
        cross_filter = next((f for f in filter_stages if "cf_shade" in f.get("names", [])), None)
        self.assertIsNotNone(cross_filter, "cross 経路用フィルタステージが存在しない")
        self.assertEqual(set(cross_filter["names"]), {"cf_shade", "cf_gain_cross"})
        self.assertEqual(cross_filter["channels"], [2, 3])

    def test_crossfeed_angles_have_correct_gains(self):
        """各角度で正しいゲインが設定される。"""
        gain_map = {"15": -3.0, "30": -6.0, "60": -10.0, "90": -14.0, "light": -3.0, "standard": -6.0}

        for angle, expected_max_gain in gain_map.items():
            with self.subTest(angle=angle):
                config_dict = {
                    "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                    "music_type": "none", "eq_output": "none",
                    "crossfeed": angle, "crossfeed_intensity": 100,
                    "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
                    "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
                    "loudness_ref": 80.0, "loudness_enabled": False,
                }
                y = self._gen_and_check(config_dict)
                gain = y["filters"]["cf_gain_cross"]["parameters"]["gain"]
                self.assertEqual(gain, expected_max_gain,
                    f"angle={angle}: expected {expected_max_gain}dB, got {gain}dB")

    def test_crossfeed_intensity_scales_gain_only(self):
        """強度はゲインのみに適用、遅延は不変。"""
        config_dict = {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "standard", "crossfeed_intensity": 50,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
            "loudness_ref": 80.0, "loudness_enabled": False,
        }
        y = self._gen_and_check(config_dict)
        gain = y["filters"]["cf_gain_cross"]["parameters"]["gain"]
        # intensity=50 で標準(-6dB)の半分 = -3.0dB
        self.assertEqual(gain, -3.0)

    def test_crossfeed_with_reverb_both_active(self):
        """crossfeed と reverb 同時有効時、両方の配線が共存。"""
        config_dict = {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "standard", "crossfeed_intensity": 50,
            "hum_noise": "none", "reverb": "hall", "reverb_intensity": 35,
            "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
            "loudness_ref": 80.0, "loudness_enabled": False,
        }
        y = self._gen_and_check(config_dict)

        # crossfeed の mixers
        self.assertIn("split4", y["mixers"])
        self.assertIn("sum4", y["mixers"])
        # reverb の mixers
        self.assertIn("split", y["mixers"])
        self.assertIn("mix", y["mixers"])

        # パイプライン順序: split4 → Filter(cf) → sum4 → split → Filter(music) → Filter(rev) → mix → final_headroom
        pipeline_names = [p.get("name") for p in y["pipeline"] if p.get("name")]
        self.assertEqual(pipeline_names, ["split4", "sum4", "split", "mix"])


if __name__ == "__main__":
    import os
    unittest.main()
