"""generate_camilladsp_yaml() が capture と出力デバイスのクロック差を補正することを検証する単体テスト。

BT (LDAC 96kHz) 経由で `PB: Prepare playback after buffer underrun` が
約41秒毎に発生した事象 (2026-09-18) の回帰防止。
enable_rate_adjust が無効だと Loopback (snd-aloop) と出力デバイスの
クロック差 (数十ppm) で出力バッファが枯渇し、周期的な underrun になる。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_bluetooth_rate_adjust -v
"""
import builtins
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from backend.dsp import yaml_generator


class TestBluetoothRateAdjust(unittest.TestCase):
    def test_rate_adjust_is_enabled_for_all_outputs(self):
        for device, pb_device in [
            ("plug:bluealsa", "plug:bluealsa"),
            ("bluealsa:DEV=BB:36:6E:A9:97:BB,PROFILE=a2dp", "bluealsa:DEV=BB:36:6E:A9:97:BB,PROFILE=a2dp"),
            ("plughw:2,0", "plughw:2,0"),
            ("hw:1,0", "plughw:1,0"),
        ]:
            with self.subTest(device=device), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "test.yml"
                config = SimpleNamespace(
                    mode="dsp", device=device, volume=-8.0,
                    music_type="classical", eq_output="studio-monitors",
                    crossfeed="light", crossfeed_intensity=5,
                    hum_noise="60hz", reverb="none", reverb_intensity=5,
                    # Stage 6
                    tilt=0.0, balance=0.0, eq_left=[], eq_right=[],
                    loudness_ref=80.0, loudness_enabled=False,
                    # Stage 7
                    ctc="none", ctc_intensity=50,
                )

                def isolated_open(path, mode="r", *args, **kwargs):
                    self.assertEqual(path, "/tmp/camilladsp/active_dsp.yml")
                    self.assertEqual(mode, "w")
                    return builtins.open(output, mode, *args, **kwargs)

                with patch.object(yaml_generator, "open", isolated_open, create=True), \
                     patch.object(yaml_generator, "_detect_alsa_cards", return_value=("2", "1")):
                    yaml_generator.generate_camilladsp_yaml(config)
                data = yaml.safe_load(output.read_text())
                devices = data["devices"]
                # クロック差補正は常に有効 (BT/LDAC 経路の周期 underrun 回帰防止)
                self.assertIs(devices["enable_rate_adjust"], True)
                self.assertEqual(devices["samplerate"], 192000)
                self.assertEqual(devices["chunksize"], 16384)
                self.assertEqual(devices["capture"]["device"], "hw:Loopback,1,0")
                self.assertEqual(devices["capture"]["format"], "S32_LE")
                self.assertEqual(devices["playback"]["format"], "S32_LE")
                self.assertEqual(devices["playback"]["device"], pb_device)
                self.assertNotIn("resampler", devices)
                if subprocess.run(["which", "camilladsp"], capture_output=True).returncode == 0:
                    result = subprocess.run(
                        ["camilladsp", "--check", str(output)],
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
