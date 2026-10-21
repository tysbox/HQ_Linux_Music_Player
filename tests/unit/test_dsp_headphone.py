#!/usr/bin/env python3
"""ホンキャリブレーション (Stage 8 / Bisen移植 Phase 1) の単体テスト.

検証事項:
1. 回帰保証: 既定 (headphone_profile="none") では hp_ フィルタを 1 つも追加せず、
   従来の YAML 生成結果と完全一致すること (= 既存機能への影響ゼロ)
2. プロファイル選択時: preamp Gain + 補正 Biquad 列が Bisen のチェーン順
   (src EQ → out EQ → calib EQ) どおり挿入されること
3. headphone_intensity は band ゲインのみスケールし preamp はスケールしないこと
   (Bisen calibrationIntensity と同じ意味論)
4. Stage 2-5 自動ヘッドルームがキャリブレーションのブーストを考慮すること
5. 生成 YAML が camilladsp --check を通過すること

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_headphone -v

非破壊: 稼働中の DSP 設定 (/var/lib/camilladsp/active_dsp.yml) は書き換えない
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

# プロジェクトルートをパスに追加
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

import yaml  # noqa: E402

from backend.dsp import profiles as profiles_mod  # noqa: E402
from backend.dsp.yaml_generator import generate_camilladsp_yaml  # noqa: E402
from backend.dsp.models import AudioConfig  # noqa: E402

CAMILLADSP_BIN = shutil.which("camilladsp")

# スキーマ準拠のテスト用プロファイル (Bisen hifiman_deva_pro の部分バンド)
TEST_PROFILE = {
    "schema_version": 1,
    "id": "unit-test-hp",
    "type": "headphone",
    "name": "Unit Test Headphone",
    "source": "Unit test fixture (Bisen hifiman_deva_pro 一部)",
    "purpose": "device_correction",
    "preamp_db": -6.5,
    "target_curve": "harman_2018",
    "bands": [
        {"type": "lowshelf", "freq": 105, "q": 0.70, "gain": 7.3},
        {"type": "peaking", "freq": 1960, "q": 2.77, "gain": 4.9},
        {"type": "peaking", "freq": 1160, "q": 0.94, "gain": -2.6},
        {"type": "highshelf", "freq": 10000, "q": 0.70, "gain": 0.9},
    ],
}


# リキャリブレーション先 (ターゲット機種) のテスト用プロファイル
TEST_TARGET_PROFILE = {
    "schema_version": 1,
    "id": "unit-test-target",
    "type": "headphone",
    "name": "Unit Test Target Headphone",
    "source": "Unit test fixture",
    "purpose": "device_correction",
    "preamp_db": -4.0,
    "target_curve": "harman_2018",
    "bands": [
        {"type": "lowshelf", "freq": 200, "q": 0.70, "gain": 5.0},
        {"type": "peaking", "freq": 3000, "q": 2.0, "gain": -3.0},
    ],
}


def _make_config(**overrides) -> AudioConfig:
    """テスト用 AudioConfig (既定 = 全機能なし)."""
    defaults = dict(
        mode="dsp",
        device="plughw:1,0",
        volume=-12.0,
        music_type="none",
        eq_output="none",
        crossfeed="none",
        crossfeed_intensity=5,
        hum_noise="none",
        reverb="none",
        reverb_intensity=5,
    )
    defaults.update(overrides)
    return AudioConfig(**defaults)


def _generate_yaml_dict(config) -> dict:
    """YAML を一時ファイルに生成して辞書で返す (本番パスは書き換えない)."""
    fd, tmp_path = tempfile.mkstemp(suffix="_dsp.yml", prefix="test_hp_")
    os.close(fd)
    try:
        generate_camilladsp_yaml(config, out_path=tmp_path)
        with open(tmp_path) as f:
            return yaml.safe_load(f)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


class _TempProfileDir:
    """テスト用プロファイルディレクトリを作り、profiles.PROFILES_DIR を差し替える."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test_profiles_")
        for prof in (TEST_PROFILE, TEST_TARGET_PROFILE):
            path = os.path.join(self.tmp.name, f"{prof['id']}.json")
            with open(path, "w") as f:
                json.dump(prof, f)
        self._patcher = mock.patch.object(
            profiles_mod, "PROFILES_DIR", pathlib.Path(self.tmp.name))
        self._patcher.start()
        return self

    def __exit__(self, *exc):
        self._patcher.stop()
        self.tmp.cleanup()
        return False


class TestHeadphoneCalibration(unittest.TestCase):
    """Stage 8 ホンキャリブレーションの生成ロジック検証."""

    def test_default_config_adds_no_calibration_filters(self):
        """回帰保証: 既定 (headphone_profile="none") では hp_ フィルタが 1 つも無い.

        全機能 none の従来構成 = dummy フィルタのみ (既存スナップショットと同一)。
        """
        y = _generate_yaml_dict(_make_config())
        hp_filters = [n for n in y["filters"] if n.startswith("hp_")]
        self.assertEqual(hp_filters, [])
        # 従来の none 構成どおり dummy フィルタのみであること
        self.assertEqual(set(y["filters"].keys()), {"dummy"})

    def test_old_style_config_without_new_fields(self):
        """新フィールドを持たない旧型オブジェクト (duck typing) でも従来どおり生成."""
        cfg = types.SimpleNamespace(
            mode="dsp", device="plughw:1,0", volume=-12.0,
            music_type="none", eq_output="none",
            crossfeed="none", crossfeed_intensity=5,
            hum_noise="none", reverb="none", reverb_intensity=5,
            tilt=0.0, balance=0.0, eq_left=[], eq_right=[],
            loudness_ref=80.0, loudness_enabled=False,
            absolute_phase=False, ctc="none", ctc_intensity=50,
        )
        y = _generate_yaml_dict(cfg)
        hp_filters = [n for n in y["filters"] if n.startswith("hp_")]
        self.assertEqual(hp_filters, [])

    def test_calibration_generates_preamp_and_biquads(self):
        """プロファイル選択時: preamp Gain + 全バンド Biquad が生成される."""
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp", headphone_intensity=100))
        self.assertIn("hp_preamp", y["filters"])
        self.assertEqual(y["filters"]["hp_preamp"]["type"], "Gain")
        self.assertAlmostEqual(
            y["filters"]["hp_preamp"]["parameters"]["gain"], -6.5, places=2)
        type_map = {"lowshelf": "Lowshelf", "peaking": "Peaking", "highshelf": "Highshelf"}
        for i, band in enumerate(TEST_PROFILE["bands"]):
            name = f"hp_{i}"
            self.assertIn(name, y["filters"], f"missing filter {name}")
            self.assertEqual(y["filters"][name]["type"], "Biquad")
            self.assertEqual(y["filters"][name]["parameters"]["type"], type_map[band["type"]])
            self.assertAlmostEqual(
                y["filters"][name]["parameters"]["gain"], band["gain"], places=2)

    def test_intensity_scales_band_gains_not_preamp(self):
        """強度は band ゲインのみスケール (preamp は不変) — Bisen 仕様."""
        with _TempProfileDir():
            y50 = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp", headphone_intensity=50))
            y100 = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp", headphone_intensity=100))
        # preamp はスケールしない
        self.assertAlmostEqual(y50["filters"]["hp_preamp"]["parameters"]["gain"], -6.5, places=2)
        self.assertAlmostEqual(y100["filters"]["hp_preamp"]["parameters"]["gain"], -6.5, places=2)
        # band gain はスケールされる
        self.assertAlmostEqual(y50["filters"]["hp_0"]["parameters"]["gain"], 7.3 * 0.5, places=2)
        self.assertAlmostEqual(y100["filters"]["hp_0"]["parameters"]["gain"], 7.3, places=2)
        # 負ゲインも対称にスケールされる
        self.assertAlmostEqual(y50["filters"]["hp_2"]["parameters"]["gain"], -2.6 * 0.5, places=2)

    def test_intensity_zero_keeps_preamp_only(self):
        """強度 0 = band ゲイン 0 (preamp は維持) — Bisen の意味論."""
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp", headphone_intensity=0))
        self.assertAlmostEqual(y["filters"]["hp_preamp"]["parameters"]["gain"], -6.5, places=2)
        for i in range(len(TEST_PROFILE["bands"])):
            self.assertAlmostEqual(
                y["filters"][f"hp_{i}"]["parameters"]["gain"], 0.0, places=2)

    def test_chain_order_matches_bisen(self):
        """Bisen チェーン順: src EQ (m_*) → out EQ (o_*) → calib (hp_*) → headroom."""
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                music_type="classical", eq_output="studio-monitors",
                headphone_profile="unit-test-hp"))
        dry_names = []
        for p in y["pipeline"]:
            if p.get("type") == "Filter" and "hp_preamp" in p.get("names", []):
                dry_names = p["names"]
                break
        self.assertTrue(dry_names, "dry path Filter (hp_*) not found in pipeline")
        self.assertLess(dry_names.index("m_0"), dry_names.index("o_0"))
        self.assertLess(dry_names.index("o_0"), dry_names.index("hp_preamp"))
        self.assertLess(dry_names.index("hp_preamp"), dry_names.index("hp_0"))
        self.assertLess(dry_names.index("hp_3"), dry_names.index("headroom"))

    def test_headroom_includes_calibration_boost(self):
        """キャリブレーションのみ有効 (= EQ なし) でも headroom 保護が働く.

        Stage 2-5 と同じ算法 (preamp を含む合成応答の最大ゲイン + 0.5dB マージン)
        で検算する。preamp -6.5dB が lowshelf +7.3dB を相殺するため正味の
        ヘッドルームは浅くなる (= preamp の存在意義どおり)。
        """
        from backend.dsp.analysis import max_gain_of_config
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp", headphone_intensity=100))
        self.assertIn("headroom", y["filters"])
        headroom_gain = y["filters"]["headroom"]["parameters"]["gain"]
        # 検算: headroom 以外の全 dry フィルタの合成最大ゲインから期待値を導出
        dry_filters = {k: v for k, v in y["filters"].items() if k != "headroom"}
        expected = round(-(max_gain_of_config(dry_filters) + 0.5), 1)
        self.assertAlmostEqual(headroom_gain, expected, places=1)
        # 保護が実働していること (= 負の値)
        self.assertLess(headroom_gain, 0.0)

    def test_unknown_profile_id_is_ignored(self):
        """存在しないプロファイル ID は警告のみで従来どおり生成 (保護動作)."""
        y = _generate_yaml_dict(_make_config(headphone_profile="does-not-exist"))
        hp_filters = [n for n in y["filters"] if n.startswith("hp_")]
        self.assertEqual(hp_filters, [])
        self.assertNotIn("headroom", y["filters"])

    @unittest.skipIf(CAMILLADSP_BIN is None, "camilladsp バイナリが見つかりません")
    def test_calibration_yaml_passes_camilladsp_check(self):
        """キャリブレーション有効時の YAML が camilladsp --check を通過する."""
        with _TempProfileDir():
            fd, yp = tempfile.mkstemp(suffix="_dsp.yml", prefix="test_hp_check_")
            os.close(fd)
            try:
                generate_camilladsp_yaml(
                    _make_config(headphone_profile="unit-test-hp",
                                 headphone_intensity=100),
                    out_path=yp)
                result = subprocess.run(
                    [CAMILLADSP_BIN, "--check", yp],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(
                    result.returncode, 0,
                    f"camilladsp --check failed: {result.stderr}\n{result.stdout}")
                self.assertIn("Config is valid", result.stdout)
            finally:
                if os.path.exists(yp):
                    os.remove(yp)


class TestHeadphoneRecalibration(unittest.TestCase):
    """Step 1-6c: リキャリブレーション (Bisen App.tsx computeCorrectionBands 相当) の検証."""

    def test_default_target_keeps_listening_bands(self):
        """ターゲット既定 harman = リスニング補正のみ (従来動作と完全同一)。"""
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp", headphone_intensity=100))
        hp_bands = [n for n in y["filters"] if n.startswith("hp_") and n != "hp_preamp"]
        self.assertEqual(len(hp_bands), len(TEST_PROFILE["bands"]))

    def test_bypass_target_no_filters(self):
        """bypass = 素の音: hp_ フィルタなし・headroom もなし。"""
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp", headphone_target="bypass"))
        self.assertEqual([n for n in y["filters"] if n.startswith("hp_")], [])
        self.assertNotIn("headroom", y["filters"])

    def test_same_model_target_no_filters(self):
        """同一機種 = 補正なし (Bisen 仕様: listening.id === target.id → no correction)。"""
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp",
                headphone_target="unit-test-hp"))
        self.assertEqual([n for n in y["filters"] if n.startswith("hp_")], [])
        self.assertNotIn("headroom", y["filters"])

    def test_recalibration_appends_negated_target_bands(self):
        """機種ターゲット = リスニング補正 + ターゲット補正の逆 (バンド連結方式)。

        実効補正 = C_L + (−C_T):
        リスニング機種 → AutoEq ターゲット(主に Harman)近似 → ターゲット機種の特性。
        """
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp",
                headphone_target="unit-test-target",
                headphone_intensity=100))
        total = len(TEST_PROFILE["bands"]) + len(TEST_TARGET_PROFILE["bands"])
        hp_names = [n for n in y["filters"] if n.startswith("hp_") and n != "hp_preamp"]
        self.assertEqual(len(hp_names), total)
        # 前半: リスニングバンド (そのまま)
        for i, band in enumerate(TEST_PROFILE["bands"]):
            self.assertAlmostEqual(
                y["filters"][f"hp_{i}"]["parameters"]["gain"], band["gain"], places=2)
        # 後半: ターゲットバンド (ゲイン反転)
        offset = len(TEST_PROFILE["bands"])
        for j, band in enumerate(TEST_TARGET_PROFILE["bands"]):
            self.assertAlmostEqual(
                y["filters"][f"hp_{offset + j}"]["parameters"]["gain"],
                -band["gain"], places=2)
        # preamp はリスニング側のみ維持 (Bisen 仕様)
        self.assertAlmostEqual(y["filters"]["hp_preamp"]["parameters"]["gain"], -6.5, places=2)

    def test_unknown_target_falls_back_to_listening(self):
        """未解決ターゲット ID はリスニング補正のみ (既存動作保護)。"""
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp",
                headphone_target="does-not-exist",
                headphone_intensity=100))
        hp_bands = [n for n in y["filters"] if n.startswith("hp_") and n != "hp_preamp"]
        self.assertEqual(len(hp_bands), len(TEST_PROFILE["bands"]))

    def test_catalog_target_resolution(self):
        """ターゲットは同梱カタログからも解決される (機種取込み不要でリキャリブ可能)。"""
        from backend.dsp.profiles import load_catalog
        catalog = load_catalog()
        self.assertGreater(catalog["total"], 0)
        entry = catalog["entries"][0]
        with _TempProfileDir():
            y = _generate_yaml_dict(_make_config(
                headphone_profile="unit-test-hp",
                headphone_target=entry["profile"]["id"],
                headphone_intensity=100))
        total = len(TEST_PROFILE["bands"]) + len(entry["profile"]["bands"])
        hp_bands = [n for n in y["filters"] if n.startswith("hp_") and n != "hp_preamp"]
        self.assertEqual(len(hp_bands), total)

    @unittest.skipIf(CAMILLADSP_BIN is None, "camilladsp バイナリが見つかりません")
    def test_recalibration_yaml_passes_camilladsp_check(self):
        """リキャリブレーション有効時の YAML が camilladsp --check を通過する。"""
        with _TempProfileDir():
            fd, yp = tempfile.mkstemp(suffix="_dsp.yml", prefix="test_hp_recal_")
            os.close(fd)
            try:
                generate_camilladsp_yaml(
                    _make_config(headphone_profile="unit-test-hp",
                                  headphone_target="unit-test-target",
                                  headphone_intensity=100),
                    out_path=yp)
                result = subprocess.run(
                    [CAMILLADSP_BIN, "--check", yp],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(
                    result.returncode, 0,
                    f"camilladsp --check failed: {result.stderr}\n{result.stdout}")
                self.assertIn("Config is valid", result.stdout)
            finally:
                if os.path.exists(yp):
                    os.remove(yp)


class TestBundledProfiles(unittest.TestCase):
    """config/profiles/ 同梱プロファイル (Bisen 内蔵 7 機種) の検証."""

    BUNDLED_DIR = os.path.join(_PROJ, "config", "profiles")

    def _bundled_jsons(self) -> list:
        if not os.path.isdir(self.BUNDLED_DIR):
            return []
        # catalog.json はプロファイルでなくカタログ容器ファイルのため除外する
        return sorted(
            e for e in os.listdir(self.BUNDLED_DIR)
            if e.endswith(".json") and e != "catalog.json"
        )

    def test_bundled_profiles_count(self):
        """Bisen 内蔵 7 機種が同梱されていること.

        注: Bisen の SoundPeats GoFree 2 は正ゲイン合計 29.5dB がスキーマの
        安全上限 (合計 20dB) を超過するため除外した (過補正防止の保護)。
        flat_bypass は「プロファイルなし」設定 (= none) と等価のため対象外。
        """
        self.assertGreaterEqual(len(self._bundled_jsons()), 7)

    def test_all_bundled_profiles_pass_schema(self):
        """全同梱プロファイルが JSON スキーマ + セマンティック検証を通過する."""
        from backend.dsp.profiles import validate_profile
        jsons = self._bundled_jsons()
        self.assertTrue(jsons, "bundled profiles not found")
        for name in jsons:
            with open(os.path.join(self.BUNDLED_DIR, name)) as f:
                profile = json.load(f)
            valid, errors = validate_profile(profile)
            self.assertTrue(valid, f"{name}: {errors}")

    @unittest.skipIf(CAMILLADSP_BIN is None, "camilladsp バイナリが見つかりません")
    def test_bundled_profile_yaml_generation(self):
        """各同梱プロファイル → YAML 生成 → camilladsp --check 全通過."""
        import shutil as _shutil
        jsons = self._bundled_jsons()
        self.assertTrue(jsons, "bundled profiles not found")
        with tempfile.TemporaryDirectory(prefix="test_bundled_") as tmp:
            for name in jsons:
                _shutil.copy(os.path.join(self.BUNDLED_DIR, name), tmp)
            with mock.patch.object(profiles_mod, "PROFILES_DIR", pathlib.Path(tmp)):
                for name in jsons:
                    profile_id = name[:-len(".json")]
                    fd, yp = tempfile.mkstemp(suffix="_dsp.yml", prefix="test_bundled_")
                    os.close(fd)
                    try:
                        generate_camilladsp_yaml(
                            _make_config(headphone_profile=profile_id,
                                         headphone_intensity=100),
                            out_path=yp)
                        result = subprocess.run(
                            [CAMILLADSP_BIN, "--check", yp],
                            capture_output=True, text=True, timeout=10,
                        )
                        self.assertEqual(
                            result.returncode, 0,
                            f"{name}: camilladsp --check failed: "
                            f"{result.stderr}\n{result.stdout}")
                    finally:
                        if os.path.exists(yp):
                            os.remove(yp)


if __name__ == "__main__":
    unittest.main()
