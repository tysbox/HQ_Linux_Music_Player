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
from backend.dsp.paths import dsp_yaml_path


class TestBluetoothRateAdjust(unittest.TestCase):
    def test_rate_adjust_is_enabled_for_all_outputs(self):
        # (device, playback device, expected playback format)
        # _detect_alsa_cards は ("2","1") = (usb_card=2, pch_card=1) を返す。
        # generator の規則: BT (bluealsa) または USB カードは S16_LE、
        # それ以外 (PCH) は S32_LE。
        #   → 6060c4b6「BT/DSD 再生時の Loopback フォーマット競合対策」で
        #     意図的に導入された挙動であり、稼働中 YAML もこれに従う。
        # 本テストは S32_LE を一律に期待する古い remained ままで常時失敗していた。
        for device, pb_device, pb_format, exp_chunksize in [
            ("plug:bluealsa", "plug:bluealsa", "S16_LE", 16384),
            ("bluealsa:DEV=BB:36:6E:A9:97:BB,PROFILE=a2dp", "bluealsa:DEV=BB:36:6E:A9:97:BB,PROFILE=a2dp", "S16_LE", 16384),
            ("bluealsa", "bluealsa", "S16_LE", 16384),
            ("plughw:2,0", "plughw:2,0", "S16_LE", 4096),
            ("hw:1,0", "plughw:1,0", "S32_LE", 4096),
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
                    # 2026-10-02 修正: generator は atomic 書き込みのため
                    # "<out_path>.tmp.<pid>" を開く。本テストは古く
                    # out_path 自体を前提にしていたため常時失敗していた。
                    # atomic 書き込みの前提 (同一ディレクトリの一時ファイル) も
                    # 併せて検証する。
                    expected = dsp_yaml_path()
                    self.assertTrue(
                        path.startswith(expected + ".tmp."),
                        f"atomic 書き込み一時ファイルではない: {path} (期待: {expected}.tmp.*)",
                    )
                    self.assertEqual(mode, "w")
                    return builtins.open(output, mode, *args, **kwargs)

                # 既定出力先は /var/lib/camilladsp (root 所有) なので、
                # open / makedirs / replace のすべてを隔離しないと
                # 実FSに触れてしまう (Content の検証だけが本テストの目的)。
                with patch.object(yaml_generator, "open", isolated_open, create=True), \
                     patch.object(yaml_generator.os, "makedirs", lambda *a, **k: None), \
                     patch.object(yaml_generator.os, "replace", lambda *a, **k: None), \
                     patch.object(yaml_generator, "_detect_alsa_cards", return_value=("2", "1")):
                    yaml_generator.generate_camilladsp_yaml(config)
                data = yaml.safe_load(output.read_text())
                devices = data["devices"]
                # クロック差補正は常に有効 (BT/LDAC 経路の周期 underrun 回帰防止)
                self.assertIs(devices["enable_rate_adjust"], True)
                self.assertEqual(devices["samplerate"], 192000)
                # chunksize: BT=16384 (約85ms・underrun防止)、有線=4096 (低遅延)。
                # 履歴: HANDOVER 2026-10-03 で BT=16384 が5分間underrunゼロを実証。
                self.assertEqual(devices["chunksize"], exp_chunksize)
                self.assertEqual(devices["capture"]["device"], "hw:Loopback,1,0")
                self.assertEqual(devices["capture"]["format"], "S32_LE")
                # 再生フォーマットはデバイス依存 (BT/USB=S16_LE, PCH=S32_LE)
                self.assertEqual(devices["playback"]["format"], pb_format)
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
