#!/usr/bin/env python3
"""FIR 全帯域キャリブレーション (追加 Step / 決定 D-5) の単体テスト.

検証対象:
- backend.dsp.fir: PEQ bands → min-phase FIR 生成 (firwin2 + minimum_phase)
  - 応答一致 (PEQ 合成応答 vs FIR 実応答 — 全帯域で ±0.5dB 以内)
  - 強度スケーリング (gain_scale が応答に線形反映)
  - min-phase 性 (エネルギーが先頭に集中 = pre-ringing 無し)
  - WAV 形式 (192kHz / stereo / float32 = CamillaDSP Conv 互換)
  - キャッシュ (同一パラメータで再生成せずパス一致)
  - bands 空 → None
- backend.dsp.yaml_generator: headphone_mode=fir で Conv 注入 /
  peq (既定) で従来 Biquad 列 (完全一致)
- backend.dsp.models: headphone_mode フィールド

実行:
  python3 -m unittest tests.unit.test_fir_calibration -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_PROJ = Path(__file__).resolve().parents[2]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

import numpy as np

from backend.dsp.analysis import rbj_coefficients, magnitude_response_db
from backend.dsp.fir import (
    FIR_IR_DIR,
    generate_fir_ir,
    fir_response_db,
    json_hash,
)
from backend.dsp.models import AudioConfig

# 同梱実プロファイル (10 バンド — lowshelf/peaking/highshelf 混在)
_AKG = json.loads((_PROJ / "config/profiles/akg-k371.json").read_text())


def _peq_response_db(bands, freqs, fs=192000.0, gain_scale=1.0):
    """PEQ bands の合成応答 (検証用の独立実装)。"""
    total = np.zeros_like(freqs, dtype=float)
    for b in bands:
        bq, a = rbj_coefficients(b["type"], b["freq"], b["q"],
                                 b["gain"] * gain_scale, fs)
        total += magnitude_response_db(bq, a, freqs, fs)
    return total


class FirGenerationTest(unittest.TestCase):
    """FIR 生成の数値検証 (実 WAV を書くため FIR_IR_DIR を一時 dir へ)。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = FIR_IR_DIR
        import backend.dsp.fir as firmod
        firmod.FIR_IR_DIR = Path(self._tmp)
        # generate_fir_ir はモジュール属性を直接参照するためパッチ
        self._firmod = firmod

    def tearDown(self):
        self._firmod.FIR_IR_DIR = self._orig_dir
        for f in Path(self._tmp).glob("hp_fir_*.wav"):
            f.unlink()
        os.rmdir(self._tmp)

    def _gen(self, profile=_AKG, scale=1.0):
        return generate_fir_ir(profile, gain_scale=scale)

    def test_response_matches_peq_full_band(self):
        """FIR 実応答が PEQ 合成応答に全帯域 (20Hz-20kHz) で一致すること。

        許容誤差 0.5dB: firwin2 の hamming window による遷移帯域の丸め込み
        (実測 max 0.36dB / mean 0.04dB — 8192 grid / 16385 taps)。
        """
        ir = self._gen()
        self.assertIsNotNone(ir)
        freqs = np.logspace(np.log10(20), np.log10(20000), 300)
        fir_db = fir_response_db(ir, freqs)
        peq_db = _peq_response_db(_AKG["bands"], freqs)
        err = np.abs(fir_db - peq_db)
        self.assertLessEqual(err.max(), 0.5,
                             f"max err {err.max():.3f} dB exceeds 0.5dB")
        self.assertLessEqual(err.mean(), 0.1,
                             f"mean err {err.mean():.3f} dB exceeds 0.1dB")

    def test_intensity_scaling_linear(self):
        """gain_scale=0.5 の FIR 応答が PEQ 50% 応答に一致すること。"""
        ir50 = self._gen(scale=0.5)
        freqs = np.logspace(np.log10(20), np.log10(20000), 200)
        fir_db = fir_response_db(ir50, freqs)
        peq_db = _peq_response_db(_AKG["bands"], freqs, gain_scale=0.5)
        err = np.abs(fir_db - peq_db)
        self.assertLessEqual(err.max(), 0.5)

    def test_min_phase_energy_concentration(self):
        """min-phase 性: 絶対値エネルギーの 90% が前半 10% に集中すること。

        線形位相 FIR ならエネルギー中心は中央 (50%) にある。
        min-phase では先頭集中 = pre-ringing 無し・因果的。
        """
        from scipy.io import wavfile
        ir = self._gen()
        sr, data = wavfile.read(str(ir))
        imp = np.abs(data[:, 0].astype(np.float64))
        cum = np.cumsum(imp) / imp.sum()
        at_10pct = cum[int(len(imp) * 0.1)]
        self.assertGreaterEqual(at_10pct, 0.90,
                                f"energy at 10% len = {at_10pct:.3f} (< 0.90)")

    def test_wav_format_camilladsp_compatible(self):
        """WAV 形式: 192kHz / stereo / float32 (既存 Reverb IR と同一)。"""
        from scipy.io import wavfile
        ir = self._gen()
        sr, data = wavfile.read(str(ir))
        self.assertEqual(sr, 192000)
        self.assertEqual(data.shape[1], 2)
        self.assertEqual(data.dtype, np.float32)
        # L/R 同一 (ヘッドホン補正は左右共通)
        self.assertTrue(np.array_equal(data[:, 0], data[:, 1]))

    def test_cache_same_params_same_path(self):
        """同一パラメータで再生成せず同一パスを返すこと (内容ハッシュ)。"""
        ir1 = self._gen()
        ir2 = self._gen()
        self.assertEqual(ir1, ir2)
        # 異なる強度は別パス
        ir3 = self._gen(scale=0.5)
        self.assertNotEqual(ir1, ir3)

    def test_empty_bands_returns_none(self):
        self.assertIsNone(generate_fir_ir({"bands": []}))
        self.assertIsNone(generate_fir_ir({}))

    def test_hash_stable_and_sensitive(self):
        """json_hash: 同一内容で安定・gain_scale 変化で変化すること。"""
        h1 = json_hash(_AKG, 1.0, 16385, 192000)
        h2 = json_hash(_AKG, 1.0, 16385, 192000)
        h3 = json_hash(_AKG, 0.5, 16385, 192000)
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 16)


class FirYamlInjectionTest(unittest.TestCase):
    """yaml_generator: headphone_mode による PEQ/FIR 切替検証。"""

    def setUp(self):
        import backend.dsp.fir as firmod
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = firmod.FIR_IR_DIR
        firmod.FIR_IR_DIR = Path(self._tmp)
        self._firmod = firmod

    def tearDown(self):
        self._firmod.FIR_IR_DIR = self._orig_dir
        for f in Path(self._tmp).glob("hp_fir_*.wav"):
            f.unlink()
        os.rmdir(self._tmp)

    def _generate(self, **kw):
        import yaml as pyyaml
        from backend.dsp.yaml_generator import generate_camilladsp_yaml
        base = dict(mode="dsp", device="plughw:1,0", volume=-10.0,
                    music_type="none", eq_output="none", crossfeed="none",
                    hum_noise="none", reverb="none",
                    headphone_profile="akg-k371", headphone_intensity=80)
        base.update(kw)
        cfg = AudioConfig(**base)
        yp = generate_camilladsp_yaml(cfg)
        return pyyaml.safe_load(open(yp).read())

    def test_fir_mode_injects_conv(self):
        y = self._generate(headphone_mode="fir")
        self.assertIn("hp_fir", y["filters"])
        self.assertEqual(y["filters"]["hp_fir"]["type"], "Conv")
        self.assertEqual(y["filters"]["hp_fir"]["parameters"]["type"], "Wav")
        # Biquad 列は存在しない
        self.assertNotIn("hp_0", y["filters"])
        # preamp は Gain のまま (FIR に含めない)
        self.assertIn("hp_preamp", y["filters"])
        # pipeline に含まれる
        names = [n for st in y["pipeline"] for n in st.get("names", [])]
        self.assertIn("hp_fir", names)

    def test_peq_mode_default_unchanged(self):
        """既定 (peq / 未指定) は従来の Biquad 列 — 既存動作完全維持。"""
        y = self._generate()  # headphone_mode 未指定 = 既定 peq
        self.assertNotIn("hp_fir", y["filters"])
        self.assertIn("hp_0", y["filters"])
        self.assertEqual(y["filters"]["hp_0"]["type"], "Biquad")

    def test_fir_ir_file_actually_exists(self):
        """Conv が参照する WAV IR が実在すること (生成失敗で壊れた YAML 防止)。"""
        y = self._generate(headphone_mode="fir")
        fn = y["filters"]["hp_fir"]["parameters"]["filename"]
        self.assertTrue(os.path.exists(fn), f"IR file missing: {fn}")

    def test_fir_boost_counted_in_headroom(self):
        """R-1 対策: FIR のブーストが自動ヘッドルームに織り込まれること。

        Conv は従来 max_gain_of_config で 0dB 扱いだったため、FIR の
        ブースト (+5dB 等) がヘッドルーム計算から漏れてクリップした。
        analysis.py が hp_fir_* IR の実応答を計算するよう修正された
        ことの回帰テスト (preamp 0 + band +5dB → headroom ≈ -5.5dB)。
        """
        import yaml as pyyaml
        import backend.dsp.profiles as profiles_mod
        prof = {"schema_version": 1, "id": "test-boost", "type": "headphone",
                "name": "Test", "source": "test", "purpose": "device_correction",
                "preamp_db": 0.0,
                "bands": [{"type": "peaking", "freq": 4000, "q": 1.0, "gain": 5.0}]}
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "test-boost.json").write_text(json.dumps(prof))
            orig = profiles_mod.PROFILES_DIR
            profiles_mod.PROFILES_DIR = Path(td)
            try:
                from backend.dsp.yaml_generator import generate_camilladsp_yaml
                cfg = AudioConfig(mode="dsp", device="plughw:1,0", volume=-10.0,
                                  music_type="none", eq_output="none",
                                  crossfeed="none", hum_noise="none",
                                  reverb="none", headphone_profile="test-boost",
                                  headphone_intensity=100, headphone_mode="fir")
                y = pyyaml.safe_load(open(generate_camilladsp_yaml(cfg)).read())
                hr = y["filters"]["headroom"]["parameters"]["gain"]
                self.assertLessEqual(hr, -5.0,
                                     f"headroom {hr} does not cover FIR boost")
            finally:
                profiles_mod.PROFILES_DIR = orig


class FirModelsTest(unittest.TestCase):
    """models.py: headphone_mode フィールドの既定値 (R-7 互換性)。"""

    def test_default_is_peq(self):
        cfg = AudioConfig(mode="dsp", device="plughw:1,0", volume=-10.0,
                          music_type="none", eq_output="none", crossfeed="none",
                          hum_noise="none", reverb="none")
        self.assertEqual(cfg.headphone_mode, "peq")

    def test_fir_accepted(self):
        cfg = AudioConfig(mode="dsp", device="plughw:1,0", volume=-10.0,
                          music_type="none", eq_output="none", crossfeed="none",
                          hum_noise="none", reverb="none",
                          headphone_mode="fir")
        self.assertEqual(cfg.headphone_mode, "fir")

    def test_old_config_json_still_valid(self):
        """旧 last_config (headphone_mode 無し) が Pydantic で受理されること。"""
        old = {"mode": "dsp", "device": "plughw:1,0", "volume": -10.0,
               "music_type": "none", "eq_output": "none", "crossfeed": "none",
               "hum_noise": "none", "reverb": "none",
               "headphone_profile": "akg-k371", "headphone_intensity": 60}
        cfg = AudioConfig(**old)
        self.assertEqual(cfg.headphone_mode, "peq")


if __name__ == "__main__":
    unittest.main()
