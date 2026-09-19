#!/usr/bin/env python3
"""CTC 応答テスト（Stage 7-5: 打ち消し量の計算）

CTC モード有効時の打ち消し量を検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_ctc_response -v
"""
import sys
import tempfile
import unittest
import yaml

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.yaml_generator import generate_camilladsp_yaml
from backend.main import AudioConfig


class TestCtcResponse(unittest.TestCase):
    """CTC 応答テスト。"""

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

    def test_ctc_mode_creates_ctc_wiring(self):
        """CTC モードで CTC 配線が生成される。"""
        config_dict = {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "none", "crossfeed_intensity": 5,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
            "loudness_ref": 80.0, "loudness_enabled": False,
            "ctc": "ctc", "ctc_intensity": 50,
        }
        y = self._gen_and_check(config_dict)
        
        # CTC 用の mixers: split4, sum4
        self.assertIn("split4", y.get("mixers", {}), "CTC 用 split4 ミキサーが存在しない")
        self.assertIn("sum4", y.get("mixers", {}), "CTC 用 sum4 ミキサーが存在しない")

        # CTC 用フィルタ: ctc_lr, ctc_rl, ctc_gain
        self.assertIn("ctc_lr", y.get("filters", {}), "ctc_lr フィルタが存在しない")
        self.assertIn("ctc_rl", y.get("filters", {}), "ctc_rl フィルタが存在しない")
        self.assertIn("ctc_gain", y.get("filters", {}), "ctc_gain フィルタが存在しない")

        # CTC 用フィルタのパラメータ確認
        ctc_lr = y["filters"]["ctc_lr"]
        self.assertEqual(ctc_lr["type"], "Conv")
        self.assertEqual(ctc_lr["parameters"]["type"], "Wav")
        
        ctc_gain = y["filters"]["ctc_gain"]
        self.assertEqual(ctc_gain["type"], "Gain")

        # パイプライン順序: split4 → Filter(ctc) → sum4
        pipeline_names = [p.get("name") for p in y["pipeline"] if p.get("name")]
        self.assertIn("split4", pipeline_names)
        self.assertIn("sum4", pipeline_names)
        self.assertTrue(pipeline_names.index("split4") < pipeline_names.index("sum4"))

    def test_ctc_excludes_crossfeed(self):
        """CTC 有効時は crossfeed が無視される。"""
        config_dict = {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "standard", "crossfeed_intensity": 50,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
            "loudness_ref": 80.0, "loudness_enabled": False,
            "ctc": "ctc", "ctc_intensity": 50,
        }
        y = self._gen_and_check(config_dict)
        
        # CTC が優先され、crossfeed 用の cf ミキサーは存在しない
        self.assertNotIn("cf", y.get("mixers", {}), "CTC 有効時は cf ミキサーが存在してはならない")
        # CTC 用の split4/sum4 が存在
        self.assertIn("split4", y.get("mixers", {}))
        self.assertIn("sum4", y.get("mixers", {}))

    def test_ctc_intensity_scales_gain(self):
        """CTC 強度に応じてゲインがスケールされる。"""
        # intensity=0 → -24dB, intensity=50 → -15dB, intensity=100 → -6dB
        test_cases = [
            (0, -24.0),
            (25, -19.5),
            (50, -15.0),
            (75, -10.5),
            (100, -6.0),
        ]
        
        for intensity, expected_gain in test_cases:
            with self.subTest(intensity=intensity):
                config_dict = {
                    "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                    "music_type": "none", "eq_output": "none",
                    "crossfeed": "none", "crossfeed_intensity": 5,
                    "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
                    "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
                    "loudness_ref": 80.0, "loudness_enabled": False,
                    "ctc": "ctc", "ctc_intensity": intensity,
                }
                y = self._gen_and_check(config_dict)
                gain = y["filters"]["ctc_gain"]["parameters"]["gain"]
                self.assertEqual(gain, expected_gain,
                    f"intensity={intensity}: expected {expected_gain}dB, got {gain}dB")

    def test_ctc_with_reverb_both_active(self):
        """CTC と reverb 同時有効時、両方の配線が共存。"""
        config_dict = {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "none", "crossfeed_intensity": 5,
            "hum_noise": "none", "reverb": "hall", "reverb_intensity": 35,
            "tilt": 0.0, "balance": 0.0, "eq_left": [], "eq_right": [],
            "loudness_ref": 80.0, "loudness_enabled": False,
            "ctc": "ctc", "ctc_intensity": 50,
        }
        y = self._gen_and_check(config_dict)

        # CTC 用の mixers
        self.assertIn("split4", y["mixers"])
        self.assertIn("sum4", y["mixers"])
        # reverb 用の mixers
        self.assertIn("split", y["mixers"])
        self.assertIn("mix", y["mixers"])
        
        # パイプライン順序確認
        pipeline_names = [p.get("name") for p in y["pipeline"] if p.get("name")]
        self.assertIn("split4", pipeline_names)
        self.assertIn("sum4", pipeline_names)
        self.assertIn("split", pipeline_names)
        self.assertIn("mix", pipeline_names)


if __name__ == "__main__":
    import os
    import tempfile
    import yaml
    unittest.main()
