#!/usr/bin/env python3
"""DSP 応答解析テスト（Stage 2-1, 2-2: 応答解析とゲイン計算）

RBJ biquad 応答、Gain/Delay/Conv の扱い、合成最大ゲイン算出を検証。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_analysis -v
"""
import numpy as np
import sys
import unittest

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.analysis import (
    rbj_coefficients,
    magnitude_response_db,
    filter_dict_to_response,
    combined_response_db,
    max_gain_of_config,
    SAMPLE_RATE,
)


class TestRbjCoefficients(unittest.TestCase):
    """RBJ 係数計算のテスト。"""

    def test_peaking_6db_at_1khz(self):
        """Peaking +6dB @ 1kHz が 1kHz で 6.0±0.1dB になる。"""
        b, a = rbj_coefficients("peaking", 1000.0, 0.707, 6.0)
        freqs = np.array([1000.0])
        resp = magnitude_response_db(b, a, freqs)
        self.assertAlmostEqual(resp[0], 6.0, delta=0.1,
            msg=f"Peaking +6dB@1kHz: expected 6.0dB, got {resp[0]:.4f}dB")

    def test_peaking_0db_flat(self):
        """Peaking 0dB はフラット応答（0dB）になる。"""
        b, a = rbj_coefficients("peaking", 1000.0, 0.707, 0.0)
        freqs = np.logspace(1, 4.3, 100)  # 10Hz〜20kHz
        resp = magnitude_response_db(b, a, freqs)
        self.assertTrue(np.allclose(resp, 0.0, atol=1e-10),
            msg=f"Peaking 0dB should be flat: max deviation = {np.max(np.abs(resp)):.2e}")

    def test_gain_filter(self):
        """Gain フィルタは全域で指定ゲインになる。"""
        fd = {"type": "Gain", "parameters": {"gain": -6.0}}
        freqs = np.logspace(1, 4.3, 100)
        resp = filter_dict_to_response(fd, freqs)
        self.assertTrue(np.allclose(resp, -6.0),
            msg=f"Gain -6dB should be flat: got {resp}")

    def test_delay_filter(self):
        """Delay フィルタは振幅不変（0dB）。"""
        fd = {"type": "Delay", "parameters": {"delay": 1.0, "unit": "ms"}}
        freqs = np.logspace(1, 4.3, 100)
        resp = filter_dict_to_response(fd, freqs)
        self.assertTrue(np.allclose(resp, 0.0),
            msg=f"Delay should be 0dB: got {resp}")

    def test_conv_filter(self):
        """Conv フィルタは振幅 0dB（別途処理）。"""
        fd = {"type": "Conv", "parameters": {"type": "Wav", "filename": "ir.wav"}}
        freqs = np.logspace(1, 4.3, 100)
        resp = filter_dict_to_response(fd, freqs)
        self.assertTrue(np.allclose(resp, 0.0),
            msg=f"Conv should be 0dB: got {resp}")

    def test_lowpass_filter(self):
        """Lowpass はカットオフ以上で減衰する。"""
        b, a = rbj_coefficients("lowpass", 1000.0, 0.707, 0.0)
        freqs = np.array([100.0, 1000.0, 10000.0])
        resp = magnitude_response_db(b, a, freqs)
        # 100Hz は通過帯域（約 0dB）、1kHz は -3dB、10kHz は大きく減衰
        self.assertGreater(resp[0], -1.0, "100Hz should be in passband")
        self.assertAlmostEqual(resp[1], -3.0, delta=0.5, msg="1kHz should be ~-3dB")
        self.assertLess(resp[2], -20.0, "10kHz should be attenuated")

    def test_highpass_filter(self):
        """Highpass はカットオフ以下で減衰する。"""
        b, a = rbj_coefficients("highpass", 1000.0, 0.707, 0.0)
        freqs = np.array([100.0, 1000.0, 10000.0])
        resp = magnitude_response_db(b, a, freqs)
        self.assertLess(resp[0], -20.0, "100Hz should be attenuated")
        self.assertAlmostEqual(resp[1], -3.0, delta=0.5, msg="1kHz should be ~-3dB")
        self.assertGreater(resp[2], -1.0, "10kHz should be in passband")

    def test_lowshelf_filter(self):
        """Lowshelf は低域をブースト/カットする。"""
        b, a = rbj_coefficients("lowshelf", 1000.0, 0.707, 6.0)
        freqs = np.array([100.0, 1000.0, 10000.0])
        resp = magnitude_response_db(b, a, freqs)
        self.assertAlmostEqual(resp[0], 6.0, delta=0.5, msg="100Hz should be boosted")
        self.assertAlmostEqual(resp[2], 0.0, delta=0.5, msg="10kHz should be flat")

    def test_highshelf_filter(self):
        """Highshelf は高域をブースト/カットする。"""
        b, a = rbj_coefficients("highshelf", 1000.0, 0.707, 6.0)
        freqs = np.array([100.0, 1000.0, 10000.0])
        resp = magnitude_response_db(b, a, freqs)
        self.assertAlmostEqual(resp[0], 0.0, delta=0.5, msg="100Hz should be flat")
        self.assertAlmostEqual(resp[2], 6.0, delta=0.5, msg="10kHz should be boosted")


class TestCombinedResponse(unittest.TestCase):
    """合成応答計算のテスト。"""

    def test_series_connection(self):
        """直列接続はゲインが加算される（dBスケール）。"""
        fd1 = {"type": "Gain", "parameters": {"gain": -3.0}}
        fd2 = {"type": "Gain", "parameters": {"gain": -4.0}}
        freqs = np.logspace(1, 4.3, 10)
        resp = combined_response_db([fd1, fd2], freqs)
        self.assertTrue(np.allclose(resp, -7.0),
            msg=f"Series gains should add: expected -7dB, got {resp[0]:.2f}dB")

    def test_peaking_plus_gain(self):
        """Peaking + Gain の合成。"""
        fd1 = {"type": "Biquad", "parameters": {"type": "Peaking", "freq": 1000, "q": 0.707, "gain": 6.0}}
        fd2 = {"type": "Gain", "parameters": {"gain": -2.0}}
        freqs = np.array([1000.0])
        resp = combined_response_db([fd1, fd2], freqs)
        self.assertAlmostEqual(resp[0], 4.0, delta=0.1,
            msg=f"Peaking +6dB + Gain -2dB = +4dB at 1kHz: got {resp[0]:.4f}dB")


class TestMaxGainOfConfig(unittest.TestCase):
    """設定からの最大ゲイン計算テスト。"""

    def test_empty_filters(self):
        """空フィルタは 0dB。"""
        max_gain = max_gain_of_config({})
        self.assertEqual(max_gain, 0.0)

    def test_only_gain_filters(self):
        """Gain フィルタのみの場合。"""
        filters = {
            "g1": {"type": "Gain", "parameters": {"gain": -3.0}},
            "g2": {"type": "Gain", "parameters": {"gain": -4.0}},
        }
        max_gain = max_gain_of_config(filters)
        self.assertAlmostEqual(max_gain, -7.0, places=1)

    def test_peaking_boost(self):
        """Peaking ブーストの最大ゲイン。"""
        filters = {
            "eq1": {"type": "Biquad", "parameters": {"type": "Peaking", "freq": 1000, "q": 0.707, "gain": 6.0}},
        }
        max_gain = max_gain_of_config(filters)
        self.assertAlmostEqual(max_gain, 6.0, delta=0.2)

    def test_mixed_filters(self):
        """混在フィルタの最大ゲイン。"""
        filters = {
            "headroom": {"type": "Gain", "parameters": {"gain": -4.0}},
            "eq1": {"type": "Biquad", "parameters": {"type": "Peaking", "freq": 1000, "q": 0.707, "gain": 6.0}},
            "eq2": {"type": "Biquad", "parameters": {"type": "Peaking", "freq": 3000, "q": 1.0, "gain": 3.0}},
        }
        max_gain = max_gain_of_config(filters)
        # -4 + 6 = +2dB が最大付近
        self.assertGreater(max_gain, 1.5)
        self.assertLess(max_gain, 3.0)


class TestSelfConsistency(unittest.TestCase):
    """自己整合性テスト（numpy 版と標準ライブラリ版の比較等）。"""

    def test_rbj_vs_manual_calculation(self):
        """既知の参照値と比較（Audio EQ Cookbook 例）。"""
        # RBJ Cookbook の例: fs=48000, fc=1000, Q=1, gain=6dB
        b, a = rbj_coefficients("peaking", 1000.0, 1.0, 6.0, fs=48000)
        freqs = np.array([1000.0])
        resp = magnitude_response_db(b, a, freqs, fs=48000)
        self.assertAlmostEqual(resp[0], 6.0, delta=0.1)

    def test_symmetry_peaking_boost_cut(self):
        """Peaking ブースト/カットは対称。"""
        b1, a1 = rbj_coefficients("peaking", 1000.0, 0.707, 6.0)
        b2, a2 = rbj_coefficients("peaking", 1000.0, 0.707, -6.0)
        freqs = np.logspace(1, 4.3, 1000)
        resp1 = magnitude_response_db(b1, a1, freqs)
        resp2 = magnitude_response_db(b2, a2, freqs)
        # ブーストとカットは鏡像関係
        self.assertTrue(np.allclose(resp1, -resp2, atol=1e-10),
            msg="Peaking boost/cut should be symmetric")


if __name__ == "__main__":
    unittest.main()
