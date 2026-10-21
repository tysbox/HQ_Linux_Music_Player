#!/usr/bin/env python3
"""ISO 226 ラウドネス補正（CamillaDSP 純正 Loudness フィルタ）の単体テスト.

2026-10-02: 旧実装（独自モデル: delta = loudness_ref + volume から
Lowshelf/Highshelf を生成）を CamillaDSP 4.1.3 内蔵の `Loudness` フィルタへ
置き換える際に追加。

検証の要点:
  1. dB SPL → reference_level 変換が CamillaDSP の許容域 (0 <= x < 20) に収まる
     （20 以上は "Reference level must be less than 20" で起動失敗する）
  2. 生成される YAML が実機 CamillaDSP の schema に適合する
  3. volume 操作で EQ が変わらない（Coupling の解消）
  4. loudness_enabled=False では何も入らない（既存動作の維持）

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_loudness -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ not in os.sys.path:
    os.sys.path.insert(0, _PROJ)

from backend.dsp.loudness import (  # noqa: E402
    DB_SPL_MAX,
    DB_SPL_MIN,
    DEFAULT_HIGH_BOOST,
    DEFAULT_LOW_BOOST,
    REFERENCE_LEVEL_MAX,
    build_loudness_filter,
    build_volume_filter,
    spl_to_reference_level,
)
from backend.dsp.yaml_generator import generate_camilladsp_yaml  # noqa: E402
from types import SimpleNamespace  # noqa: E402

CAMILLADSP_BIN = shutil.which("camilladsp") or "/usr/local/bin/camilladsp"


def _cfg(**over):
    base = dict(
        mode="dsp", device="plughw:1,0", volume=-5.0, music_type="none",
        eq_output="none", crossfeed="none", crossfeed_intensity=0, hum_noise="none",
        reverb="none", reverb_intensity=0, tilt=0.0, balance=0.0,
        eq_left=[], eq_right=[], loudness_ref=80.0, loudness_enabled=True,
        ctc="none", ctc_intensity=50,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestSplConversion(unittest.TestCase):
    """dB SPL → CamillaDSP reference_level の変換."""

    def test_maps_to_expected_values(self):
        # 20 dB SPL -> 0.0, 60 -> 10.0, 80 -> 15.0, 100 -> 20.0
        self.assertAlmostEqual(spl_to_reference_level(20.0), 0.0, places=3)
        self.assertAlmostEqual(spl_to_reference_level(60.0), 10.0, places=3)
        self.assertAlmostEqual(spl_to_reference_level(80.0), 15.0, places=3)

    def test_always_within_camilladsp_range(self):
        """CamillaDSP は reference_level >= 20 を拒否する。範囲外入力でも収まること。"""
        for ref in [-100.0, 0.0, 20.0, 40.0, 80.0, 100.0, 140.0, 1000.0]:
            with self.subTest(loudness_ref=ref):
                level = spl_to_reference_level(ref)
                self.assertGreaterEqual(level, 0.0)
                self.assertLess(level, REFERENCE_LEVEL_MAX,
                                f"ref={ref} -> {level} は 20 未満でなければならない")

    def test_default_ref_is_in_range(self):
        """既定の loudness_ref=80.0 が CamillaDSP で有効であること。"""
        self.assertLess(spl_to_reference_level(80.0), 20.0)

    def test_monotonic(self):
        """大きい dB SPL ほど大きい reference_level になること。"""
        values = [spl_to_reference_level(r) for r in (20.0, 40.0, 60.0, 80.0, 100.0)]
        self.assertEqual(values, sorted(values))


class TestFilterBuilders(unittest.TestCase):
    """フィルタ定義の構造."""

    def test_loudness_filter_shape(self):
        f = build_loudness_filter(80.0)
        self.assertEqual(f["type"], "Loudness")
        p = f["parameters"]
        for key in ("reference_level", "high_boost", "low_boost", "fader", "attenuate_mid"):
            self.assertIn(key, p)
        self.assertIsInstance(p["attenuate_mid"], bool)
        self.assertIsInstance(p["high_boost"], float)
        self.assertIsInstance(p["low_boost"], float)

    def test_boosts_follow_legacy_direction(self):
        """旧実装(low 8 / high 4)の低域寄りを継承していること。"""
        self.assertEqual(DEFAULT_LOW_BOOST, 8.0)
        self.assertEqual(DEFAULT_HIGH_BOOST, 4.0)

    def test_volume_filter_uses_aux_fader(self):
        """Volume.fader は Aux1..Aux4 のみ (Main は不可)。"""
        f = build_volume_filter()
        self.assertEqual(f["type"], "Volume")
        self.assertIn(f["parameters"]["fader"], ("Aux1", "Aux2", "Aux3", "Aux4"))
        self.assertIsInstance(f["parameters"]["limit"], float,
                              "limit は f32(秒)。bool は不可")


class TestGeneratedConfig(unittest.TestCase):
    """generator が出す YAML の構造."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hqm-loud-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _gen(self, **over):
        out = os.path.join(self.tmp, "c.yml")
        generate_camilladsp_yaml(_cfg(**over), out_path=out)
        with open(out, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_uses_native_loudness_filter(self):
        """旧shelf 2本ではなく CamillaDSP 純正 Loudness フィルタを使うこと。"""
        d = self._gen()
        self.assertIn("loudness_iso226", d["filters"])
        self.assertEqual(d["filters"]["loudness_iso226"]["type"], "Loudness")
        # 旧実装の痕跡が消えていること
        self.assertNotIn("loud_low", d["filters"])
        self.assertNotIn("loud_high", d["filters"])

    def test_volume_filter_present_when_enabled(self):
        d = self._gen()
        self.assertIn("volume_stage", d["filters"])
        self.assertEqual(d["filters"]["volume_stage"]["type"], "Volume")

    def test_no_filters_when_disabled(self):
        d = self._gen(loudness_enabled=False)
        self.assertNotIn("loudness_iso226", d["filters"])
        self.assertNotIn("volume_stage", d["filters"])

    def test_decoupled_from_volume(self):
        """volume を変えてもラウドネス設定（EQ 曲線）が変わらないこと。
        これが今回の置換の主要目的。"""
        a = self._gen(volume=-5.0)
        b = self._gen(volume=-30.0)
        self.assertEqual(a["filters"]["loudness_iso226"], b["filters"]["loudness_iso226"])
        self.assertEqual(a["filters"]["volume_stage"], b["filters"]["volume_stage"])

    def test_reference_level_varies_with_ref(self):
        a = self._gen(loudness_ref=60.0)
        b = self._gen(loudness_ref=80.0)
        self.assertNotEqual(
            a["filters"]["loudness_iso226"]["parameters"]["reference_level"],
            b["filters"]["loudness_iso226"]["parameters"]["reference_level"],
        )

    def test_pipeline_ordering(self):
        """Volume が Loudness より先に適用されること。"""
        d = self._gen()
        for p in d["pipeline"]:
            names = p.get("names") or []
            if "volume_stage" in names and "loudness_iso226" in names:
                self.assertLess(names.index("volume_stage"), names.index("loudness_iso226"))
                return
        self.fail("volume_stage / loudness_iso226 を同一 pipeline 内で 발견 못")


@unittest.skipUnless(os.path.exists(CAMILLADSP_BIN), "camilladsp バイナリ不在のため skip")
class TestAgainstRealCamillaDSP(unittest.TestCase):
    """実機 CamillaDSP の --check で検証する。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hqm-loudchk-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _check(self, data) -> str:
        out = os.path.join(self.tmp, "c.yml")
        with open(out, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False)
        res = subprocess.run([CAMILLADSP_BIN, "--check", out],
                             capture_output=True, text=True)
        return (res.stdout + res.stderr)

    def _gen(self, **over):
        out = os.path.join(self.tmp, "gen.yml")
        generate_camilladsp_yaml(_cfg(**over), out_path=out)
        with open(out, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_generated_config_is_valid(self):
        msg = self._check(self._gen())
        self.assertIn("Config is valid", msg, msg)

    def test_generated_config_valid_across_ref_range(self):
        for ref in (20.0, 60.0, 80.0, 100.0):
            with self.subTest(loudness_ref=ref):
                msg = self._check(self._gen(loudness_ref=ref))
                self.assertIn("Config is valid", msg, msg)

    def test_legacy_value_80_would_have_been_invalid(self):
        """参考: dB SPL をそのまま渡すと CamillaDSP は拒否する。
        変換が必要であることの回帰ガード。"""
        data = self._gen()
        data["filters"]["loudness_iso226"]["parameters"]["reference_level"] = 80.0
        msg = self._check(data)
        self.assertNotIn("Config is valid", msg)
        self.assertIn("less than 20", msg)


if __name__ == "__main__":
    unittest.main()
