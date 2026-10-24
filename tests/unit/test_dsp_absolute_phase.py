#!/usr/bin/env python3
"""絶対位相 (Absolute Phase) ON/OFF の単体テスト.

CamillaDSP の `Gain` フィルタの `inverted: true` を使う。
既に `inverted` はコード中に随所にある (balance / headroom / rev_out 等
は inverted: False) ため、スキーマ的には追加確認が不要だが、
**配置位置**が正しくなければ 功能しないため将其処を検証する。

設計要件:
  1. OFF のとき何も追加しない (既存設定・位相が不変)
  2. ON のとき最終段 (全 DSP 通過後) に Gain{inverted: true} が入る
  3. 両チャンネル (channels: [0,1]) を同時に反転する
     — 片側だけ反転するとステレオ像が倒れ、絶対位相でなくなる
  4. reverb 有無のどちらでも最終段に来ること
     (reverb 有無で最終段が final_headroom / mix と変わるため)

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_absolute_phase -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

import yaml

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ not in os.sys.path:
    os.sys.path.insert(0, _PROJ)

from backend.dsp.yaml_generator import generate_camilladsp_yaml  # noqa: E402

CAMILLADSP_BIN = shutil.which("camilladsp") or "/usr/local/bin/camilladsp"


def _cfg(**over):
    base = dict(
        mode="dsp", device="plughw:1,0", volume=-5.0, music_type="none",
        eq_output="none", crossfeed="none", crossfeed_intensity=0, hum_noise="none",
        reverb="none", reverb_intensity=0, tilt=0.0, balance=0.0,
        eq_left=[], eq_right=[], loudness_ref=80.0, loudness_enabled=False,
        absolute_phase=False, ctc="none", ctc_intensity=50,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestAbsolutePhaseToggle(unittest.TestCase):
    """ON/OFF の振舞い."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hqm-absph-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        # 呼び出しごとに一意な out_path を使う。同一パスを使い回すと
        # 原子書き込みの都合でテスト間の状態が混入する。
        self._seq = 0

    def _gen(self, **over):
        self._seq += 1
        out = os.path.join(self.tmp, f"c{self._seq}.yml")
        generate_camilladsp_yaml(_cfg(**over), out_path=out)
        with open(out, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_off_adds_nothing(self):
        d = self._gen(absolute_phase=False)
        self.assertNotIn("absolute_phase", d["filters"])

    def test_off_is_byte_identical_to_legacy(self):
        """OFF なら旧実装と同一（フィルタ/順序とも変わらない）。"""
        d = self._gen(absolute_phase=False)
        for p in d["pipeline"]:
            self.assertNotIn("absolute_phase", p.get("names") or [])

    def test_on_adds_inverted_gain(self):
        d = self._gen(absolute_phase=True)
        self.assertIn("absolute_phase", d["filters"])
        f = d["filters"]["absolute_phase"]
        self.assertEqual(f["type"], "Gain")
        self.assertIs(f["parameters"]["inverted"], True)
        # 利得を変えない（0 dB）— 位相だけ反転させる
        self.assertEqual(f["parameters"]["gain"], 0.0)

    def test_on_is_last_stage(self):
        """全 DSP を通過した最終段に置かれていること。"""
        d = self._gen(absolute_phase=True)
        self.assertEqual(d["pipeline"][-1].get("names"), ["absolute_phase"])

    def test_on_applies_to_both_channels(self):
        """片側だけの反転は絶対位相ではなく定位補正になる。"""
        d = self._gen(absolute_phase=True)
        self.assertEqual(d["pipeline"][-1]["channels"], [0, 1])

    def test_on_with_reverb_still_last(self):
        """reverb 有効時も最終段に来ること。

        NOTE: reverb_intensity を明示指定する。0 だと IR 段が
        成立せず fallback 経路に入るため、WET 構成を検証できない。
        """
        d = self._gen(absolute_phase=True, reverb="hall", reverb_intensity=50)
        self.assertEqual(d["pipeline"][-1].get("names"), ["absolute_phase"])
        names = [p.get("name") for p in d["pipeline"]]
        self.assertIn("split", names, f"WET split が無い: {d['pipeline']}")
        self.assertIn("mix", names, f"WET mix が無い: {d['pipeline']}")
        # WET (rev) より後ろにあること
        wet_idx = next(i for i, p in enumerate(d["pipeline"])
                       if p.get("names") and "rev" in p["names"])
        self.assertGreater(len(d["pipeline"]) - 1, wet_idx)

    def test_toggle_is_idempotent(self):
        """ON/OFF を往復しても設定が壊れないこと。"""
        a = self._gen(absolute_phase=True)
        b = self._gen(absolute_phase=False)
        c = self._gen(absolute_phase=True)
        self.assertEqual(a, c)
        self.assertNotEqual(
            [p.get("names") for p in a["pipeline"]],
            [p.get("names") for p in b["pipeline"]],
        )

    def test_default_missing_attribute_is_off(self):
        """AudioConfig にフィールドが無い旧 config でも OFF として扱うこと。"""
        cfg = _cfg()
        del cfg.absolute_phase
        out = os.path.join(self.tmp, "legacy.yml")
        generate_camilladsp_yaml(cfg, out_path=out)
        with open(out, encoding="utf-8") as f:
            d = yaml.safe_load(f)
        self.assertNotIn("absolute_phase", d["filters"])


@unittest.skipUnless(os.path.exists(CAMILLADSP_BIN), "camilladsp バイナリ不在のため skip")
class TestAgainstRealCamillaDSP(unittest.TestCase):
    """実機 camilladsp --check で検証."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hqm-absphchk-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _gen(self, **over):
        out = os.path.join(self.tmp, "g.yml")
        generate_camilladsp_yaml(_cfg(**over), out_path=out)
        with open(out, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _check(self, data):
        p = os.path.join(self.tmp, "c.yml")
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False)
        r = subprocess.run([CAMILLADSP_BIN, "--check", p], capture_output=True, text=True)
        return r.stdout + r.stderr

    def test_on_is_valid_config(self):
        msg = self._check(self._gen(absolute_phase=True))
        self.assertIn("Config is valid", msg, msg)

    def test_off_is_valid_config(self):
        msg = self._check(self._gen(absolute_phase=False))
        self.assertIn("Config is valid", msg, msg)

    def test_valid_with_reverb(self):
        msg = self._check(self._gen(absolute_phase=True, reverb="hall", reverb_intensity=50))
        self.assertIn("Config is valid", msg, msg)

    def test_valid_with_ctc(self):
        msg = self._check(self._gen(absolute_phase=True, ctc="ctc"))
        self.assertIn("Config is valid", msg, msg)


if __name__ == "__main__":
    unittest.main()
