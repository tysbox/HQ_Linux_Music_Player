#!/usr/bin/env python3
"""IR 検証テスト（Stage 5-6: IR検証）

IR ファイルのレート/ch/長さ/ピーク/RT60 を検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_ir_validation -v
"""
import os
import sys
import unittest
from pathlib import Path

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

import numpy as np
from scipy.io import wavfile

from scripts.make_ir import estimate_rt60


IR_DIR = Path(os.path.expanduser("~/.config/camilladsp/ir/"))


class TestIrValidation(unittest.TestCase):
    """IR ファイル検証テスト。"""

    def test_all_ir_files_valid(self):
        """全 IR ファイルが仕様を満たす。"""
        ir_files = list(IR_DIR.glob("*.wav"))
        self.assertGreater(len(ir_files), 0, "IR ファイルが存在しない")
        
        for wav_file in sorted(ir_files):
            with self.subTest(file=wav_file.name):
                sr, ir = wavfile.read(wav_file)
                
                # サンプルレート 192kHz
                self.assertEqual(sr, 192000, f"{wav_file.name}: sample rate must be 192000Hz")
                
                # ステレオ 2ch
                if ir.ndim == 1:
                    ir = np.column_stack((ir, ir))
                self.assertEqual(ir.shape[1], 2, f"{wav_file.name}: must be stereo (2ch)")
                
                # float32 または int16
                self.assertIn(ir.dtype, [np.float32, np.int16, np.int32],
                    f"{wav_file.name}: dtype must be float32 or int16")
                
                # float32 に変換
                if ir.dtype != np.float32:
                    ir = ir.astype(np.float32) / (32768.0 if ir.dtype == np.int16 else 1.0)
                
                # 長さ: 1.0s 以上 3.0s 以下
                duration = len(ir) / sr
                self.assertGreaterEqual(duration, 1.0, f"{wav_file.name}: duration >= 1.0s")
                self.assertLessEqual(duration, 3.0, f"{wav_file.name}: duration <= 3.0s")
                
                # ピーク <= -6dBFS
                peak = np.max(np.abs(ir))
                peak_db = 20 * np.log10(peak + 1e-12)
                self.assertLessEqual(peak_db, -5.5, f"{wav_file.name}: peak {peak_db:.1f}dBFS > -6dBFS")
                
                # RT60 推定 (合成済みのものは目標値近く)
                rt60 = estimate_rt60(ir, sr)
                self.assertGreater(rt60, 0.1, f"{wav_file.name}: RT60 {rt60:.3f}s too short")
                self.assertLess(rt60, 5.0, f"{wav_file.name}: RT60 {rt60:.3f}s too long")
                
                # JSON サイドカー存在チェック（合成済みのみ）
                json_path = wav_file.with_suffix(".json")
                if json_path.exists():
                    import json
                    with open(json_path) as f:
                        meta = json.load(f)
                    self.assertTrue(meta.get("synthesized"), f"{wav_file.name}: must be synthesized=true")
                    self.assertIn("rt60_estimated", meta)
                    self.assertIn("peak_dbfs", meta)
    
    def test_synthetic_ir_rt60_accuracy(self):
        """合成 IR の RT60 精度確認。"""
        for preset_id in ["studio", "hall", "large_hall"]:
            with self.subTest(preset=preset_id):
                json_path = IR_DIR / f"{preset_id}.json"
                wav_path = IR_DIR / f"{preset_id}.wav"
                self.assertTrue(json_path.exists(), f"{preset_id}.json missing")
                self.assertTrue(wav_path.exists(), f"{preset_id}.wav missing")
                
                import json
                with open(json_path) as f:
                    meta = json.load(f)
                
                target_rt60 = meta.get("rt60_target")
                estimated_rt60 = meta.get("rt60_estimated")
                
                self.assertIsNotNone(target_rt60, f"{preset_id}: rt60_target missing")
                self.assertIsNotNone(estimated_rt60, f"{preset_id}: rt60_estimated missing")
                
                # 許容誤差 ±15%
                error = abs(estimated_rt60 - target_rt60) / target_rt60
                self.assertLess(error, 0.15, 
                    f"{preset_id}: RT60 error {error*100:.1f}% > 15% (target={target_rt60}s, est={estimated_rt60:.3f}s)")


if __name__ == "__main__":
    from pathlib import Path
    unittest.main()
