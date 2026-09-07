"""generate_camilladsp_yaml() の単体テスト.

CamillaDSP 4.1.3 で生成YAMLが起動可能かを `camilladsp --check` で検証。
ff840cb0 で根治した chunksize 配置 (devices 直下) が回帰しないことを保証する。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_camilladsp_yaml_schema -v

前提:
- camilladsp バイナリが PATH に存在 (/usr/local/bin/camilladsp)
- backend.main が import 可能 (PYTHONPATH=/home/tysbox/HQ_Linux_Music_Player)
"""
import os
import shutil
import subprocess
import sys
import unittest
import yaml

# backend.main を import するため PYTHONPATH を設定
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.main import generate_camilladsp_yaml, AudioConfig  # noqa: E402

CAMILLADSP_BIN = shutil.which("camilladsp")


def _check_camilladsp(yaml_path: str) -> tuple[int, str, str]:
    """camilladsp --check を実行して (exit, stdout, stderr) を返す."""
    result = subprocess.run(
        [CAMILLADSP_BIN, "--check", yaml_path],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


def _make_default_config(**overrides) -> AudioConfig:
    """テスト用のデフォルト AudioConfig を作成."""
    defaults = dict(
        mode="dsp",
        device="plughw:1,0",
        volume=-3.0,
        music_type="none",
        eq_output="none",
        crossfeed="light",
        crossfeed_intensity=5,
        hum_noise="none",
        reverb="none",
        reverb_intensity=5,
    )
    defaults.update(overrides)
    return AudioConfig(**defaults)


@unittest.skipIf(CAMILLADSP_BIN is None, "camilladsp バイナリが見つかりません")
class TestCamillaDSPYamlSchema(unittest.TestCase):
    """CamillaDSP 4.1.3 YAML スキーマ準拠テスト."""

    def test_default_config_yaml_passes_check(self):
        """デフォルト設定 (mode=dsp, music_type=none) で生成YAMLが --check 通過."""
        cfg = _make_default_config()
        yp = generate_camilladsp_yaml(cfg)
        self.assertTrue(os.path.exists(yp), f"YAML file not created: {yp}")

        rc, out, err = _check_camilladsp(yp)
        self.assertEqual(rc, 0, f"camilladsp --check failed (rc={rc}): {err}\n{out}")
        self.assertIn("Config is valid", out)

    def test_chunksize_in_devices_block_level(self):
        """chunksize は devices 直下必須 (ff840cb0 根治位置)."""
        cfg = _make_default_config()
        yp = generate_camilladsp_yaml(cfg)
        with open(yp) as f:
            y = yaml.safe_load(f)

        # devices 直下に chunksize があること
        self.assertIn("chunksize", y["devices"], "chunksize must be in devices block")
        # capture/playback 内に chunksize がないこと (誤位置の回帰検出)
        self.assertNotIn(
            "chunksize",
            y["devices"].get("capture", {}),
            "chunksize must NOT be in capture block (ff840cb0 regression)",
        )
        self.assertNotIn(
            "chunksize",
            y["devices"].get("playback", {}),
            "chunksize must NOT be in playback block (ff840cb0 regression)",
        )

    def test_devices_block_required_fields(self):
        """devices 直下に必須フィールドが揃う."""
        cfg = _make_default_config()
        yp = generate_camilladsp_yaml(cfg)
        with open(yp) as f:
            y = yaml.safe_load(f)

        devices = y["devices"]
        self.assertIn("samplerate", devices)
        self.assertIn("capture", devices)
        self.assertIn("playback", devices)
        # capture / playback の必須フィールド
        for sub in (devices["capture"], devices["playback"]):
            self.assertIn("type", sub)
            self.assertIn("channels", sub)
            self.assertIn("device", sub)
            self.assertIn("format", sub)

    def test_jazz_music_type_yaml_passes_check(self):
        """music_type=jazz (EQ有効) で生成YAMLが --check 通過."""
        cfg = _make_default_config(music_type="jazz", eq_output="studio-monitors")
        yp = generate_camilladsp_yaml(cfg)
        rc, out, err = _check_camilladsp(yp)
        self.assertEqual(rc, 0, f"camilladsp --check failed (rc={rc}): {err}\n{out}")

    def test_60hz_hum_noise_yaml_passes_check(self):
        """hum_noise=60hz (ハム除去有効) で生成YAMLが --check 通過."""
        cfg = _make_default_config(hum_noise="60hz")
        yp = generate_camilladsp_yaml(cfg)
        rc, out, err = _check_camilladsp(yp)
        self.assertEqual(rc, 0, f"camilladsp --check failed (rc={rc}): {err}\n{out}")

    def test_pure_mode_also_generates_yaml(self):
        """mode=pure でも YAML 生成自体は成功する (DSP モードへの切替経路として)."""
        cfg = _make_default_config(mode="pure")
        yp = generate_camilladsp_yaml(cfg)
        self.assertTrue(os.path.exists(yp))

    def test_no_state_file_path_in_yaml(self):
        """CamillaDSP 4.1.3 で削除された devices.state_file_path は YAML に含まない.

        HANDOVER0907 §2 根治: state_file_path はYAML から削除、
        代わりに -s/--statefile コマンドラインオプションで指定。
        """
        cfg = _make_default_config()
        yp = generate_camilladsp_yaml(cfg)
        with open(yp) as f:
            y = yaml.safe_load(f)
        self.assertNotIn(
            "state_file_path",
            y["devices"],
            "state_file_path must NOT be in YAML (removed in CamillaDSP 4.1.3)",
        )


if __name__ == "__main__":
    unittest.main()