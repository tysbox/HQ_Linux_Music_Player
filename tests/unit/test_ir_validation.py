#!/usr/bin/env python3
"""IR 検証テスト (2026-10-03 v3.1 改訂: 本番使用 IR のみを検証)

旧テストの問題点:
  ~/.config/camilladsp/ir/ の *.wav をすべて一律仕様 (長さ 1.0-3.0s,
  RT60 > 0.1s) で検証していたため、実使用ファイルが恒常 FAIL していた:
    - reverb IR (st_nicolaes_church 7.99s 等、実空間の残響は 3s を超える)
    - CTC IR (ctc_lr/rl 0.05s、インパルス様で RT60 は本来 0 近傍)
  また未使用の legacy 合成 IR (studio/large_hall) も検証対象だった。

本テストの契約 (2026-10-03 時点の実運用と一致):
  - 検証対象は本番コードが参照する IR のみ:
      * reverb: backend.dsp.yaml_generator.REVERB_WET_TRIM_DB のキー
        (= GUI の REV_OPTS と同一: hall / jazz_club / large_bottle_hall /
        st_nicolaes_church)
      * ctc:   ctc_lr.wav / ctc_rl.wav (yaml_generator.py が直接参照)
  - reverb IR: 192kHz / stereo / 0.5-10.0s / peak <= -5.5dBFS / RT60 0.1-5.0s
  - CTC IR  : 192kHz / stereo / 0.005-0.5s / peak <= -5.5dBFS (RT60 は免除)
  - 未使用 IR (studio/large_hall 等の legacy) は検証対象外
  - プリセット→IR ファイルの存在チェック (GUI で選べるのに IR が無い事故の防止)

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_ir_validation -v
"""
import os
import sys
import unittest
from pathlib import Path

_PROJ = Path(__file__).resolve().parents[2]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

import numpy as np
from scipy.io import wavfile

from scripts.make_ir import estimate_rt60

# 本番使用プリセットは yaml_generator (単一ソース) から導出する。
# GUI (page.tsx REV_OPTS) と一致することを test_reverb_opts_match_gui で固定。
from backend.dsp.yaml_generator import REVERB_WET_TRIM_DB

IR_DIR = Path(os.path.expanduser("~/.config/camilladsp/ir/"))

# GUI (new-gui/app/page.tsx REV_OPTS) の reverb 選択肢。'none' 以外。
GUI_REV_OPTS = {"hall", "jazz_club", "large_bottle_hall", "st_nicolaes_church"}

# CTC 用 IR (yaml_generator.py が直接参照する固定名)
CTC_IRS = ("ctc_lr.wav", "ctc_rl.wav")


def _load_ir(wav_path: Path):
    """IR を (sr, float32 stereo) で読み込む共通ヘルパー。"""
    sr, ir = wavfile.read(wav_path)
    if ir.ndim == 1:
        ir = np.column_stack((ir, ir))
    if ir.dtype != np.float32:
        ir = ir.astype(np.float32) / (32768.0 if ir.dtype == np.int16 else 1.0)
    return sr, ir


class TestIrValidation(unittest.TestCase):
    """本番使用 IR ファイルの検証テスト。"""

    def _assert_format(self, wav_path: Path):
        """192kHz / stereo / float32|int16|int32 のフォーマット検証。"""
        sr, ir = wavfile.read(wav_path)
        self.assertEqual(sr, 192000, f"{wav_path.name}: sample rate must be 192000Hz")
        if ir.ndim == 1:
            ir = np.column_stack((ir, ir))
        self.assertEqual(ir.shape[1], 2, f"{wav_path.name}: must be stereo (2ch)")
        self.assertIn(
            ir.dtype, [np.float32, np.int16, np.int32],
            f"{wav_path.name}: dtype must be float32 or int16",
        )
        return sr, ir

    def test_reverb_preset_irs_valid(self):
        """本番 reverb IR (REVERB_WET_TRIM_DB キー) が仕様を満たす。

        実空間 IR は 3s を超え得る (st_nicolaes_church = 7.99s) ため、
        上限は 10.0s とする (旧 3.0s 上限は小型合成 IR 想定の過去仕様)。
        """
        self.assertGreater(len(REVERB_WET_TRIM_DB), 0, "reverb プリセット定義が空")

        for preset in sorted(REVERB_WET_TRIM_DB):
            wav_path = IR_DIR / f"{preset}.wav"
            with self.subTest(preset=preset):
                # GUI で選択可能なプリセットに IR が無いのは致命的
                self.assertTrue(wav_path.exists(), f"{preset}: IR ファイルが存在しない")
                sr, ir = self._assert_format(wav_path)

                duration = len(ir) / sr
                self.assertGreaterEqual(duration, 0.5, f"{preset}: duration >= 0.5s")
                self.assertLessEqual(duration, 10.0, f"{preset}: duration <= 10.0s")

                peak = np.max(np.abs(ir))
                peak_db = 20 * np.log10(peak + 1e-12)
                self.assertLessEqual(peak_db, -5.5, f"{preset}: peak {peak_db:.1f}dBFS > -6dBFS")

                rt60 = estimate_rt60(ir, sr)
                self.assertGreater(rt60, 0.1, f"{preset}: RT60 {rt60:.3f}s too short")
                self.assertLess(rt60, 5.0, f"{preset}: RT60 {rt60:.3f}s too long")

    def test_ctc_irs_valid(self):
        """CTC IR (ctc_lr/rl) はインパルス様の短い IR。

        長さ 0.005-0.5s・peak <= -5.5dBFS。
        RT60 検証は免除 (クロストークキャンセル用の短い伝達特性であり、
        室の残響ではないため RT60 は本来 0 近傍になる)。
        """
        for name in CTC_IRS:
            wav_path = IR_DIR / name
            with self.subTest(file=name):
                self.assertTrue(wav_path.exists(), f"{name}: IR ファイルが存在しない")
                sr, ir = self._assert_format(wav_path)

                duration = len(ir) / sr
                self.assertGreaterEqual(duration, 0.005, f"{name}: duration >= 0.005s")
                self.assertLessEqual(duration, 0.5, f"{name}: duration <= 0.5s")

                peak = np.max(np.abs(ir))
                peak_db = 20 * np.log10(peak + 1e-12)
                self.assertLessEqual(peak_db, -5.5, f"{name}: peak {peak_db:.1f}dBFS > -6dBFS")

    def test_reverb_opts_match_gui(self):
        """バックエンドの reverb テーブルと GUI 選択肢が一致すること。

        不一致があると「GUI で選べるのに IR が無い/使われない」事故になる。
        GUI 側の定義 (page.tsx REV_OPTS の 'none' 以外) と一致を固定する。
        """
        self.assertEqual(
            set(REVERB_WET_TRIM_DB.keys()), GUI_REV_OPTS,
            "REVERB_WET_TRIM_DB と GUI REV_OPTS が不一致。片方だけ追加されていないか確認",
        )


if __name__ == "__main__":
    unittest.main()

