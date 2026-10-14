#!/usr/bin/env python3
"""Phase 3 (bisen-dspd 経由 Tube/Restore) の単体テスト.

検証対象:
- backend.dsp.bisen_daemon: Unix socket クライアント + 経路オーケストレーション
  (フェイクデーモンを実際に起動してプロトコルを検証 — 実機デーモン不要)
- backend.dsp.yaml_generator: tube/restore 有効時の playback 経路分岐
- backend.dsp.models: tube / tube_bias / restore フィールド

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_phase3_bisen -v
"""
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp import bisen_daemon
from backend.dsp.models import AudioConfig, DspParams


class FakeBisenDaemon(threading.Thread):
    """bisen-dspd のラインプロトコルを模すフェイクサーバ (テスト用)。"""

    def __init__(self, path, never_open=False):
        super().__init__(daemon=True)
        self.path = path
        self.never_open = never_open  # True なら playback_open を 0 のまま
        self.state = {
            "routing": 0, "bypass": 1, "tube_enabled": 0, "tube_type": "TRIODE",
            "tube_bias": 0.0, "restore_enabled": 0, "restore_mode": "lossy_standard",
            "playback_open": 0, "output_device": "plughw:1,0",
        }
        self.peaks = {
            "peak_db_l": -12.5, "peak_db_r": -13.2, "true_peak_db": -11.8,
        }
        self.commands = []
        self.running = True
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(path)
        self.srv.listen(4)

    def run(self):
        while self.running:
            try:
                self.srv.settimeout(0.2)
                conn, _ = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(1.0)
                data = conn.recv(4096).decode().strip()
                self.commands.append(data)
                resp = self._handle_line(data)
                conn.sendall((resp + "\n").encode())

    def _handle_line(self, line):
        if line == "ping":
            return "pong"
        if line == "get params":
            return " ".join(f"{k}={v}" for k, v in self.state.items())
        if line == "get peaks":
            # Phase 4: true_peak_db を含む (実デーモンの get peaks 応答形式)
            return (f"peak_db_l={self.peaks['peak_db_l']:.2f} "
                    f"peak_db_r={self.peaks['peak_db_r']:.2f} "
                    f"true_peak_db={self.peaks['true_peak_db']:.2f} "
                    f"frames=12345 xruns=0")
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "set":
            key, val = parts[1], parts[2]
            if key == "routing":
                self.state["routing"] = int(val)
                # routing=1 なら即 DAC を掴んだ体 (never_open=True では掴まない)
                self.state["playback_open"] = 1 if (int(val) and not self.never_open) else 0
                return "OK"
            if key in ("tube_enabled", "restore_enabled"):
                self.state[key] = int(val)
                return "OK"
            if key == "tube_type":
                self.state[key] = val
                return "OK"
            if key == "tube_bias":
                self.state[key] = float(val)
                return "OK"
            if key == "restore_mode":
                self.state[key] = val
                return "OK"
            if key == "output_device":
                self.state[key] = val
                return "OK"
        return "ERROR unknown"

    def stop(self):
        self.running = False
        self.join(timeout=2)
        self.srv.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class BisenDaemonClientTest(unittest.TestCase):
    """Unix socket クライアント + オーケストレーション (フェイクデーモン相手)。"""

    def setUp(self):
        self.sock_path = os.path.join(tempfile.mkdtemp(prefix="bisen_test_"), "control.sock")
        self.fake = FakeBisenDaemon(self.sock_path)
        self.fake.start()
        self._patch = mock.patch.object(bisen_daemon, "DAEMON_SOCKET", self.sock_path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.fake.stop()

    def test_ping_alive(self):
        self.assertTrue(bisen_daemon.is_daemon_alive())
        st = bisen_daemon.daemon_status()
        self.assertEqual(st.get("routing"), "0")
        self.assertEqual(st.get("playback_open"), "0")

    def test_push_params_tube_triode(self):
        bisen_daemon.push_params({"tube": "triode", "tube_bias": 65, "restore": "none"})
        self.assertEqual(self.fake.state["tube_enabled"], 1)
        self.assertEqual(self.fake.state["tube_type"], "TRIODE")
        self.assertEqual(self.fake.state["tube_bias"], 65.0)
        self.assertEqual(self.fake.state["restore_enabled"], 0)

    def test_push_params_tube_pentode_and_bias_clamp(self):
        bisen_daemon.push_params({"tube": "pentode", "tube_bias": 999, "restore": "cd"})
        self.assertEqual(self.fake.state["tube_type"], "PENTODE")
        self.assertEqual(self.fake.state["tube_bias"], 100.0)
        self.assertEqual(self.fake.state["restore_enabled"], 1)
        self.assertEqual(self.fake.state["restore_mode"], "cd")

    def test_push_params_invalid_values_disable(self):
        bisen_daemon.push_params({"tube": "bogus", "restore": "bogus"})
        self.assertEqual(self.fake.state["tube_enabled"], 0)
        self.assertEqual(self.fake.state["restore_enabled"], 0)

    def test_begin_and_wait_routing(self):
        cfg = {"tube": "triode", "tube_bias": 50, "restore": "none", "device": "plughw:1,0"}
        self.assertTrue(bisen_daemon.begin_routing("plughw:1,0", cfg))
        self.assertTrue(bisen_daemon.wait_routing_active(timeout=2.0))
        self.assertEqual(self.fake.state["output_device"], "plughw:1,0")
        self.assertEqual(self.fake.state["routing"], 1)
        # パラメータ反映
        bisen_daemon.push_params(cfg)
        self.assertEqual(self.fake.state["tube_enabled"], 1)

    def test_wait_routing_timeout(self):
        stuck = FakeBisenDaemon(self.sock_path + ".stuck", never_open=True)
        stuck.start()
        with mock.patch.object(bisen_daemon, "DAEMON_SOCKET", self.sock_path + ".stuck"):
            bisen_daemon.begin_routing("plughw:1,0", {"tube": "triode"})
            self.assertFalse(bisen_daemon.wait_routing_active(timeout=0.6))
        stuck.stop()

    def test_end_routing(self):
        bisen_daemon.begin_routing("plughw:1,0", {"tube": "triode"})
        self.assertTrue(bisen_daemon.end_routing())
        self.assertEqual(self.fake.state["routing"], 0)
        self.assertEqual(self.fake.state["playback_open"], 0)

    def test_daemon_down_is_safe(self):
        # ソケット不在 → 全 API が例外を投げずフォールバックする
        with mock.patch.object(bisen_daemon, "DAEMON_SOCKET", "/nonexistent/bisen.sock"):
            self.assertFalse(bisen_daemon.is_daemon_alive())
            self.assertFalse(bisen_daemon.begin_routing("plughw:1,0", {"tube": "triode"}))
            self.assertTrue(bisen_daemon.end_routing())  # 停止なら解放不要 = True


class RoutingDecisionTest(unittest.TestCase):
    """routing_requested / routing_active の判定ロジック (socket 呼び出しは mock)。"""

    def test_routing_requested(self):
        self.assertTrue(bisen_daemon.routing_requested({"tube": "triode", "restore": "none"}))
        self.assertTrue(bisen_daemon.routing_requested({"tube": "none", "restore": "cd"}))
        self.assertFalse(bisen_daemon.routing_requested({"tube": "none", "restore": "none"}))
        self.assertFalse(bisen_daemon.routing_requested({}))  # 旧 last_config 互換

    def test_routing_active_fallback_daemon_down(self):
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=False):
            self.assertFalse(bisen_daemon.routing_active({"tube": "triode", "device": "plughw:1,0"}))

    def test_routing_active_bt_excluded(self):
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=True):
            self.assertFalse(bisen_daemon.routing_active(
                {"tube": "triode", "device": "bluealsa:DEV=XX"}))

    def test_routing_active_ok(self):
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=True):
            self.assertTrue(bisen_daemon.routing_active(
                {"tube": "none", "restore": "cd", "device": "plughw:1,0"}))


class YamlGeneratorRoutingTest(unittest.TestCase):
    """YAML 生成の playback 経路分岐 (デーモン生死で直結/ループバックが切り替わる)。"""

    def _generate(self, cfg):
        from backend.dsp.yaml_generator import generate_camilladsp_yaml
        out = os.path.join(tempfile.mkdtemp(prefix="bisen_yaml_"), "active_dsp.yml")
        generate_camilladsp_yaml(cfg, out)
        import yaml
        with open(out) as f:
            return yaml.safe_load(f)

    def test_direct_when_daemon_down(self):
        cfg = AudioConfig(mode="dsp", device="plughw:1,0", volume=-10.0,
                          music_type="none", eq_output="none", crossfeed="none",
                          hum_noise="none", reverb="none", tube="triode")
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=False):
            y = self._generate(cfg)
        # デーモン停止 → 直結のまま (無音化フォールバック)
        self.assertEqual(y["devices"]["playback"]["device"], "plughw:1,0")

    def test_loopback_when_daemon_active(self):
        cfg = AudioConfig(mode="dsp", device="plughw:1,0", volume=-10.0,
                          music_type="none", eq_output="none", crossfeed="none",
                          hum_noise="none", reverb="none",
                          tube="none", restore="cd")
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=True):
            y = self._generate(cfg)
        self.assertEqual(y["devices"]["playback"]["device"], "hw:Loopback,0,1")
        self.assertEqual(y["devices"]["playback"]["format"], "S32_LE")
        self.assertEqual(y["devices"]["capture"]["device"], "hw:Loopback,1,0")

    def test_direct_when_tube_restore_off(self):
        cfg = AudioConfig(mode="dsp", device="plughw:1,0", volume=-10.0,
                          music_type="none", eq_output="none", crossfeed="none",
                          hum_noise="none", reverb="none")
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=True):
            y = self._generate(cfg)
        # tube/restore 無効ならデーモン稼働中でも従来どおり直結 (既存動作不変)
        self.assertEqual(y["devices"]["playback"]["device"], "plughw:1,0")


class ModelsTest(unittest.TestCase):
    """AudioConfig / DspParams の Phase 3 フィールド。"""

    def test_audio_config_defaults(self):
        cfg = AudioConfig(mode="dsp", device="plughw:1,0", volume=-10.0,
                          music_type="none", eq_output="none", crossfeed="none",
                          hum_noise="none", reverb="none")
        self.assertEqual(cfg.tube, "none")
        self.assertEqual(cfg.tube_bias, 50)
        self.assertEqual(cfg.restore, "none")

    def test_dsp_params_fields(self):
        p = DspParams(tube="pentode", tube_bias=70, restore="lossy_high")
        self.assertEqual(p.tube, "pentode")
        self.assertEqual(p.tube_bias, 70)
        self.assertEqual(p.restore, "lossy_high")


class DaemonPeaksTest(unittest.TestCase):
    """Phase 4 (Step 4-1): get peaks / daemon_peaks() のプロトコル検証。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.sock = os.path.join(self.dir, "control.sock")
        self.fake = FakeBisenDaemon(self.sock)
        self.fake.start()
        self._patch = mock.patch.object(bisen_daemon, "DAEMON_SOCKET", self.sock)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.fake.stop()
        os.rmdir(self.dir)

    def test_daemon_peaks_parses_true_peak(self):
        pk = bisen_daemon.daemon_peaks()
        self.assertAlmostEqual(float(pk["peak_db_l"]), -12.5, places=1)
        self.assertAlmostEqual(float(pk["peak_db_r"]), -13.2, places=1)
        self.assertAlmostEqual(float(pk["true_peak_db"]), -11.8, places=1)
        self.assertEqual(pk["frames"], "12345")
        self.assertEqual(pk["xruns"], "0")

    def test_daemon_peaks_down_returns_empty(self):
        self.fake.stop()
        self.assertEqual(bisen_daemon.daemon_peaks(), {})


class LevelsBisenSwitchTest(unittest.TestCase):
    """Phase 4 (Step 4-1): /ws/levels のデーモン true-peak 優先切替ロジック。"""

    def _read_bisen(self):
        from hq_api.ws import levels as ws_levels
        return ws_levels._read_bisen_levels()

    def test_bisen_levels_when_routing_active(self):
        with mock.patch.object(bisen_daemon, "daemon_status", return_value={
            "routing": "1", "playback_open": "1",
        }), mock.patch.object(bisen_daemon, "daemon_peaks", return_value={
            "peak_db_l": "-12.5", "peak_db_r": "-13.2", "true_peak_db": "-11.8",
        }):
            out = self._read_bisen()
        self.assertIsNotNone(out)
        self.assertEqual(out["source"], "bisen-dspd")
        self.assertAlmostEqual(out["peak"][0], -11.8, places=1)
        self.assertAlmostEqual(out["peak"][1], -11.8, places=1)
        self.assertAlmostEqual(out["rms"][0], -12.5, places=1)

    def test_fallback_when_routing_inactive(self):
        with mock.patch.object(bisen_daemon, "daemon_status", return_value={
            "routing": "0", "playback_open": "0",
        }):
            self.assertIsNone(self._read_bisen())

    def test_fallback_when_daemon_down(self):
        with mock.patch.object(bisen_daemon, "daemon_status", return_value={}):
            self.assertIsNone(self._read_bisen())

    def test_fallback_when_no_true_peak_field(self):
        with mock.patch.object(bisen_daemon, "daemon_status", return_value={
            "routing": "1", "playback_open": "1",
        }), mock.patch.object(bisen_daemon, "daemon_peaks", return_value={
            "peak_db_l": "-12.5", "peak_db_r": "-13.2",
        }):
            self.assertIsNone(self._read_bisen())


class BisenStatusEndpointTest(unittest.TestCase):
    """Phase 4 (Step 4-2): GET /api/bisen/status の応答検証 (TestClient 無し・関数直呼び)。"""

    def test_status_daemon_down(self):
        from hq_api.routers import dsp_readonly
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=False), \
             mock.patch.object(dsp_readonly, "_load_last_config", return_value={
                 "tube": "triode", "restore": "none",
             }):
            out = dsp_readonly.get_bisen_status()
        self.assertFalse(out["alive"])
        self.assertTrue(out["requested"])
        self.assertFalse(out["active"])
        self.assertEqual(out["config_tube"], "triode")
        self.assertEqual(out["config_restore"], "none")

    def test_status_daemon_active(self):
        from hq_api.routers import dsp_readonly
        with mock.patch.object(bisen_daemon, "is_daemon_alive", return_value=True), \
             mock.patch.object(bisen_daemon, "daemon_status", return_value={
                 "routing": "1", "playback_open": "1", "bypass": "0",
                 "tube_enabled": "1", "tube_type": "PENTODE", "tube_bias": "65.0",
                 "restore_enabled": "1", "restore_mode": "cd",
                 "output_device": "plughw:1,0",
             }), mock.patch.object(bisen_daemon, "routing_active", return_value=True), \
             mock.patch.object(dsp_readonly, "_load_last_config", return_value={
                 "tube": "pentode", "restore": "cd",
             }):
            out = dsp_readonly.get_bisen_status()
        self.assertTrue(out["alive"])
        self.assertTrue(out["active"])
        self.assertTrue(out["routing"])
        self.assertFalse(out["bypass"])
        self.assertTrue(out["tube_enabled"])
        self.assertEqual(out["tube_type"], "PENTODE")
        self.assertAlmostEqual(out["tube_bias"], 65.0)
        self.assertTrue(out["restore_enabled"])
        self.assertEqual(out["restore_mode"], "cd")


if __name__ == "__main__":
    unittest.main()
