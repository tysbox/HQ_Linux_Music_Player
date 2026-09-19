#!/usr/bin/env python3
"""DSP ゲインマージンテスト（Stage 2-4: ゲインマージン検査）

全プリセット×強度組み合わせで最大ゲイン ≤ 0dB を検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_gain_margin -v
"""
import sys
import tempfile
import unittest

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.yaml_generator import generate_camilladsp_yaml
from backend.main import AudioConfig
from backend.dsp.analysis import max_gain_of_config
import yaml


class TestDspGainMargin(unittest.TestCase):
    """ゲインマージン検査テスト。"""

    def _gen_and_check(self, config_dict: dict, label: str) -> float:
        """設定から YAML 生成し、最大ゲインを返す。"""
        cfg = AudioConfig(**config_dict)
        with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
            tmp_path = f.name
        try:
            generate_camilladsp_yaml(cfg, out_path=tmp_path)
            with open(tmp_path) as f:
                y = yaml.safe_load(f)
            return max_gain_of_config(y["filters"])
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def test_all_configs_under_0db(self):
        """全代表構成で最大ゲイン ≤ 0dB であること。"""
        configs = [
            ("none", {
                "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                "music_type": "none", "eq_output": "none",
                "crossfeed": "none", "crossfeed_intensity": 5,
                "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            }),
            ("eq_only", {
                "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                "music_type": "classical", "eq_output": "studio-monitors",
                "crossfeed": "none", "crossfeed_intensity": 5,
                "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            }),
            ("reverb_only", {
                "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                "music_type": "none", "eq_output": "none",
                "crossfeed": "none", "crossfeed_intensity": 5,
                "hum_noise": "none", "reverb": "hall", "reverb_intensity": 35,
            }),
            ("crossfeed_only", {
                "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                "music_type": "none", "eq_output": "none",
                "crossfeed": "standard", "crossfeed_intensity": 50,
                "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
            }),
            ("all_enabled", {
                "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                "music_type": "classical", "eq_output": "studio-monitors",
                "crossfeed": "standard", "crossfeed_intensity": 50,
                "hum_noise": "60hz", "reverb": "hall", "reverb_intensity": 35,
            }),
        ]

        for label, config_dict in configs:
            with self.subTest(label=label):
                max_gain = self._gen_and_check(config_dict, label)
                self.assertLessEqual(max_gain, 1e-9,
                    msg=f"{label}: max_gain = {max_gain:.2f} dB > 0dB (クリッピングリスク)")

    def test_music_type_all_variants(self):
        """全 music_type でゲイン ≤ 0dB。"""
        for music_type in ["none", "jazz", "classical", "electronic", "vocal"]:
            with self.subTest(music_type=music_type):
                config_dict = {
                    "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                    "music_type": music_type, "eq_output": "studio-monitors",
                    "crossfeed": "none", "crossfeed_intensity": 5,
                    "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
                }
                max_gain = self._gen_and_check(config_dict, f"music_{music_type}")
                self.assertLessEqual(max_gain, 1e-9,
                    msg=f"music_type={music_type}: max_gain = {max_gain:.2f} dB > 0dB")

    def test_eq_output_all_variants(self):
        """全 eq_output でゲイン ≤ 0dB。"""
        for eq_output in ["none", "studio-monitors", "JBL-Speakers", "planar-magnetic", "loud-speaker", "Tube-Warmth", "Crystal-Clarity"]:
            with self.subTest(eq_output=eq_output):
                config_dict = {
                    "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                    "music_type": "none", "eq_output": eq_output,
                    "crossfeed": "none", "crossfeed_intensity": 5,
                    "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
                }
                max_gain = self._gen_and_check(config_dict, f"eq_{eq_output}")
                self.assertLessEqual(max_gain, 1e-9,
                    msg=f"eq_output={eq_output}: max_gain = {max_gain:.2f} dB > 0dB")

    def test_crossfeed_all_variants(self):
        """全 crossfeed でゲイン ≤ 0dB。"""
        for crossfeed in ["none", "light", "standard"]:
            for intensity in [0, 25, 50, 75, 100]:
                with self.subTest(crossfeed=crossfeed, intensity=intensity):
                    config_dict = {
                        "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                        "music_type": "none", "eq_output": "none",
                        "crossfeed": crossfeed, "crossfeed_intensity": intensity,
                        "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
                    }
                    max_gain = self._gen_and_check(config_dict, f"cf_{crossfeed}_{intensity}")
                    self.assertLessEqual(max_gain, 1e-9,
                        msg=f"crossfeed={crossfeed}/{intensity}: max_gain = {max_gain:.2f} dB > 0dB")

    def test_reverb_all_variants(self):
        """全 reverb でゲイン ≤ 0dB。"""
        for reverb in ["none", "hall", "large_hall"]:
            for intensity in [0, 25, 50, 75, 100]:
                with self.subTest(reverb=reverb, intensity=intensity):
                    config_dict = {
                        "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                        "music_type": "none", "eq_output": "none",
                        "crossfeed": "none", "crossfeed_intensity": 5,
                        "hum_noise": "none", "reverb": reverb, "reverb_intensity": intensity,
                    }
                    max_gain = self._gen_and_check(config_dict, f"rev_{reverb}_{intensity}")
                    self.assertLessEqual(max_gain, 1e-9,
                        msg=f"reverb={reverb}/{intensity}: max_gain = {max_gain:.2f} dB > 0dB")

    def test_hum_noise_all_variants(self):
        """全 hum_noise でゲイン ≤ 0dB。"""
        for hum_noise in ["none", "60hz", "120hz"]:
            with self.subTest(hum_noise=hum_noise):
                config_dict = {
                    "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
                    "music_type": "none", "eq_output": "none",
                    "crossfeed": "none", "crossfeed_intensity": 5,
                    "hum_noise": hum_noise, "reverb": "none", "reverb_intensity": 5,
                }
                max_gain = self._gen_and_check(config_dict, f"hum_{hum_noise}")
                self.assertLessEqual(max_gain, 1e-9,
                    msg=f"hum_noise={hum_noise}: max_gain = {max_gain:.2f} dB > 0dB")


if __name__ == "__main__":
    import os
    unittest.main()
