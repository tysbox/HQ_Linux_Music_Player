#!/usr/bin/env python3
"""DSP YAML スナップショットテスト（Stage 0-4: 非破壊テスト基盤）

現行の5構成で生成される YAML の filters/pipeline/mixers が
固定値（スナップショット）と一致することを検証する。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_yaml_snapshot -v

非破壊: テスト実行で稼働中の /tmp/camilladsp/active_dsp.yml を書き換えない
"""
import os
import sys
import tempfile
import unittest

# プロジェクトルートをパスに追加
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.yaml_generator import generate_camilladsp_yaml  # noqa: E402
from backend.main import AudioConfig  # noqa: E402

import yaml


# ─────────────────────────────────────────────────────────────────────────────
# 期待されるスナップショット（Stage 0 時点の現行実装から生成）
# ─────────────────────────────────────────────────────────────────────────────
SNAPSHOTS = {
    "none": {
        "description": "全機能無効 (none)",
        "config": {
            "mode": "dsp",
            "device": "plughw:1,0",
            "volume": -12.0,
            "music_type": "none",
            "eq_output": "none",
            "crossfeed": "none",
            "crossfeed_intensity": 5,
            "hum_noise": "none",
            "reverb": "none",
            "reverb_intensity": 5,
        },
    },
    "eq_only": {
        "description": "EQのみ有効",
        "config": {
            "mode": "dsp",
            "device": "plughw:1,0",
            "volume": -12.0,
            "music_type": "classical",
            "eq_output": "studio-monitors",
            "crossfeed": "none",
            "crossfeed_intensity": 5,
            "hum_noise": "none",
            "reverb": "none",
            "reverb_intensity": 5,
        },
    },
    "reverb_only": {
        "description": "Reverbのみ有効",
        "config": {
            "mode": "dsp",
            "device": "plughw:1,0",
            "volume": -12.0,
            "music_type": "none",
            "eq_output": "none",
            "crossfeed": "none",
            "crossfeed_intensity": 5,
            "hum_noise": "none",
            "reverb": "hall",
            "reverb_intensity": 35,
        },
    },
    "crossfeed_only": {
        "description": "Crossfeedのみ有効",
        "config": {
            "mode": "dsp",
            "device": "plughw:1,0",
            "volume": -12.0,
            "music_type": "none",
            "eq_output": "none",
            "crossfeed": "standard",
            "crossfeed_intensity": 50,
            "hum_noise": "none",
            "reverb": "none",
            "reverb_intensity": 5,
        },
    },
    "all_enabled": {
        "description": "全機能有効",
        "config": {
            "mode": "dsp",
            "device": "plughw:1,0",
            "volume": -12.0,
            "music_type": "classical",
            "eq_output": "studio-monitors",
            "crossfeed": "standard",
            "crossfeed_intensity": 50,
            "hum_noise": "60hz",
            "reverb": "hall",
            "reverb_intensity": 35,
        },
    },
}


def _generate_yaml_dict(config_dict: dict) -> dict:
    """設定辞書から YAML を生成し、辞書として返す（ファイル書き込みなし）。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
        tmp_path = f.name
    try:
        cfg = AudioConfig(**config_dict)
        generate_camilladsp_yaml(cfg, out_path=tmp_path)
        with open(tmp_path) as f:
            return yaml.safe_load(f)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


class TestDspYamlSnapshot(unittest.TestCase):
    """DSP YAML スナップショットテスト."""

    def _assert_yaml_structure(self, name: str, y: dict):
        """YAML の filters/pipeline/mixers 構造を検証."""
        self.assertIn("filters", y, f"{name}: filters キーが存在しない")
        self.assertIn("pipeline", y, f"{name}: pipeline キーが存在しない")
        self.assertIn("mixers", y, f"{name}: mixers キーが存在しない")

    def test_none_snapshot(self):
        """全機能無効のスナップショット."""
        y = _generate_yaml_dict(SNAPSHOTS["none"]["config"])
        self._assert_yaml_structure("none", y)
        # filters: dummy のみ
        self.assertEqual(set(y["filters"].keys()), {"dummy"})
        # pipeline: dummy filter のみ
        self.assertEqual(len(y["pipeline"]), 1)
        self.assertEqual(y["pipeline"][0]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][0]["names"]), {"dummy"})
        # mixers: 空
        self.assertEqual(y["mixers"], {})

    def test_eq_only_snapshot(self):
        """EQのみ有効のスナップショット."""
        y = _generate_yaml_dict(SNAPSHOTS["eq_only"]["config"])
        self._assert_yaml_structure("eq_only", y)
        # filters: m_0, m_1, m_2, o_0, o_1, o_2, headroom
        expected_filters = {"m_0", "m_1", "m_2", "o_0", "o_1", "o_2", "headroom"}
        self.assertEqual(set(y["filters"].keys()), expected_filters)
        # pipeline: 1つのFilter で全バンド
        self.assertEqual(len(y["pipeline"]), 1)
        self.assertEqual(y["pipeline"][0]["type"], "Filter")
        names = set(y["pipeline"][0]["names"])
        self.assertEqual(names, expected_filters)
        # mixers: 空
        self.assertEqual(y["mixers"], {})

    def test_reverb_only_snapshot(self):
        """Reverbのみ有効のスナップショット."""
        y = _generate_yaml_dict(SNAPSHOTS["reverb_only"]["config"])
        self._assert_yaml_structure("reverb_only", y)
        # filters: rev, rev_out, final_headroom
        expected_filters = {"rev", "rev_out", "final_headroom"}
        self.assertEqual(set(y["filters"].keys()), expected_filters)
        # pipeline: split -> Filter(rev,rev_out) -> mix -> Filter(final_headroom)
        self.assertEqual(len(y["pipeline"]), 4)
        self.assertEqual(y["pipeline"][0]["type"], "Mixer")
        self.assertEqual(y["pipeline"][0]["name"], "split")
        self.assertEqual(y["pipeline"][1]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][1]["names"]), {"rev", "rev_out"})
        self.assertEqual(y["pipeline"][2]["type"], "Mixer")
        self.assertEqual(y["pipeline"][2]["name"], "mix")
        self.assertEqual(y["pipeline"][3]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][3]["names"]), {"final_headroom"})
        # mixers: split + mix
        self.assertEqual(set(y["mixers"].keys()), {"split", "mix"})

    def test_crossfeed_only_snapshot(self):
        """Crossfeedのみ有効のスナップショット."""
        y = _generate_yaml_dict(SNAPSHOTS["crossfeed_only"]["config"])
        self._assert_yaml_structure("crossfeed_only", y)
        # filters: cf_shade, cf_gain_cross (Stage 4: 4-channel wiring with shading)
        expected_filters = {"cf_shade", "cf_gain_cross"}
        self.assertEqual(set(y["filters"].keys()), expected_filters)
        # pipeline: split4 -> Filter(cf_shade, cf_gain_cross) -> sum4
        self.assertEqual(len(y["pipeline"]), 3)
        self.assertEqual(y["pipeline"][0]["type"], "Mixer")
        self.assertEqual(y["pipeline"][0]["name"], "split4")
        self.assertEqual(y["pipeline"][1]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][1]["names"]), {"cf_shade", "cf_gain_cross"})
        self.assertEqual(y["pipeline"][2]["type"], "Mixer")
        self.assertEqual(y["pipeline"][2]["name"], "sum4")
        # mixers: split4 + sum4
        self.assertEqual(set(y["mixers"].keys()), {"split4", "sum4"})

    def test_all_enabled_snapshot(self):
        """全機能有効のスナップショット."""
        y = _generate_yaml_dict(SNAPSHOTS["all_enabled"]["config"])
        self._assert_yaml_structure("all_enabled", y)
        # filters: rumble_cut, hum, m_0, m_1, m_2, o_0, o_1, o_2, rev, rev_out, final_headroom
        # Stage 4: cf_shade, cf_gain_cross added for crossfeed 4-channel wiring
        expected_filters = {"rumble_cut", "hum", "m_0", "m_1", "m_2", "o_0", "o_1", "o_2", "rev", "rev_out", "final_headroom", "cf_shade", "cf_gain_cross"}
        self.assertEqual(set(y["filters"].keys()), expected_filters)
        # Pipeline structure with both crossfeed (split4/sum4) and reverb (split/mix):
        # split4 -> Filter(cf_shade, cf_gain_cross) -> sum4 -> split -> Filter(music+hum) -> Filter(rev) -> mix -> Filter(final_headroom)
        self.assertEqual(len(y["pipeline"]), 8)
        self.assertEqual(y["pipeline"][0]["type"], "Mixer")
        self.assertEqual(y["pipeline"][0]["name"], "split4")
        self.assertEqual(y["pipeline"][1]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][1]["names"]), {"cf_shade", "cf_gain_cross"})
        self.assertEqual(y["pipeline"][2]["type"], "Mixer")
        self.assertEqual(y["pipeline"][2]["name"], "sum4")
        self.assertEqual(y["pipeline"][3]["type"], "Mixer")
        self.assertEqual(y["pipeline"][3]["name"], "split")
        self.assertEqual(y["pipeline"][4]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][4]["names"]), {"rumble_cut", "hum", "m_0", "m_1", "m_2", "o_0", "o_1", "o_2"})
        self.assertEqual(y["pipeline"][5]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][5]["names"]), {"rev", "rev_out"})
        self.assertEqual(y["pipeline"][6]["type"], "Mixer")
        self.assertEqual(y["pipeline"][6]["name"], "mix")
        self.assertEqual(y["pipeline"][7]["type"], "Filter")
        self.assertEqual(set(y["pipeline"][7]["names"]), {"final_headroom"})
        # mixers: split4, sum4, split, mix
        self.assertEqual(set(y["mixers"].keys()), {"split4", "sum4", "split", "mix"})


if __name__ == "__main__":
    unittest.main()
