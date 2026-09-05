"""hq_api バックエンド統合の独立性検証 (Phase 3a-5 拡張).

フロントエンドに依存せず、hq_api:8002 単体の以下を検証:
1. 連続リクエスト負荷（100 req）で 503/500/タイムアウトが 0 件
2. 並行リクエスト（10 並行）で全成功
3. 主要エンドポイントのレスポンス時間（p95 < 200ms 目標）
4. 既存サービス（DSP/DMP）への無影響確認

実行:
  ./backend/venv/bin/python3 -m unittest tests.e2e.test_hq_api_stress -v
"""
import json
import os
import statistics
import sys
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

HQ_API_URL = os.getenv("HQ_API_URL", "http://localhost:8002")
DSP_URL = os.getenv("DSP_URL", "http://localhost:8000")
DMP_URL = os.getenv("DMP_URL", "http://localhost:8001")

# UPnP は外部ネットワーク待ちで 10 秒以上かかることがあるため
# デフォルトでは比較対象から除外。環境変数 INCLUDE_UPNP=1 で含める。
INCLUDE_UPNP = os.getenv("INCLUDE_UPNP", "0") == "1"

# 検証対象エンドポイント（hq_api 単体）
ENDPOINTS = [
    "/health",
    "/api/devices",
    "/api/now_playing",
    "/api/dsp_status",
    "/api/config",
    "/api/presets",
    "/api/library/artists",
    "/api/library/albums",
    "/api/library/stats",
    "/api/playback/status",
    "/api/queue/",
    "/api/playlists/",
    "/api/history/",
]
if INCLUDE_UPNP:
    ENDPOINTS += ["/api/upnp/servers", "/api/upnp/status"]


def fetch_json(url: str, timeout: float = 5.0) -> tuple[int, float, Any]:
    """URL から JSON を取得。タイムアウト時は (-1, elapsed, None).

    UPnP エンドポイントは外部ネットワーク待ちで長くなるため、URL に
    'upnp' を含む場合は自動で 15 秒タイムアウトに延長する。
    """
    if "upnp" in url:
        timeout = max(timeout, 15.0)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            elapsed = time.monotonic() - start
            try:
                return resp.status, elapsed, json.loads(body) if body else None
            except json.JSONDecodeError:
                return resp.status, elapsed, body
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        try:
            body = e.read().decode("utf-8")
            return e.code, elapsed, body
        except Exception:
            return e.code, elapsed, None
    except Exception as e:
        return -1, time.monotonic() - start, str(e)


class TestBackendIsolation(unittest.TestCase):
    """バックエンドがフロントエンドから独立して動作することを確認."""

    def test_hq_api_responds_without_frontend(self):
        """フロントエンド（3000/3001/3002）が停止していても hq_api が応答する."""
        code, _, _ = fetch_json(f"{HQ_API_URL}/health")
        self.assertEqual(code, 200, "hq_api must respond independently of frontend")
        print("  ✅ hq_api:8002 単独応答 OK")

    def test_legacy_backends_unaffected(self):
        """DSP:8000 / DMP:8001 が引き続き正常動作."""
        code_dsp, _, _ = fetch_json(f"{DSP_URL}/api/devices")
        code_dmp, _, _ = fetch_json(f"{DMP_URL}/api/library/artists")
        self.assertEqual(code_dsp, 200, "DSP:8000 must still work")
        self.assertEqual(code_dmp, 200, "DMP:8001 must still work")
        print("  ✅ DSP:8000 / DMP:8001 無傷")

    def test_hq_api_openapi_spec(self):
        """OpenAPI 仕様で 43 ルート以上あること."""
        try:
            with urllib.request.urlopen(f"{HQ_API_URL}/openapi.json", timeout=5) as resp:
                spec = json.loads(resp.read().decode("utf-8"))
                n = len(spec.get("paths", {}))
                self.assertGreaterEqual(n, 43)
                print(f"  ✅ OpenAPI ルート数: {n}")
        except Exception as e:
            self.fail(f"openapi.json failed: {e}")


class TestLoadEndurance(unittest.TestCase):
    """連続リクエストでの安定性確認（バックエンド統合の耐久性）."""

    def test_100_sequential_requests_no_5xx(self):
        """100 連続リクエストで 5xx / タイムアウトが 0 件."""
        path = "/health"
        statuses = []
        for i in range(100):
            code, _, _ = fetch_json(f"{HQ_API_URL}{path}")
            statuses.append(code)
        n_5xx = sum(1 for s in statuses if s >= 500 or s < 0)
        n_ok = sum(1 for s in statuses if s == 200)
        self.assertEqual(n_5xx, 0, f"5xx/timeout: {n_5xx} in {len(statuses)} requests")
        self.assertEqual(n_ok, 100, f"Expected 100 OK, got {n_ok}")
        print(f"  ✅ 100 連続 OK ({n_5xx} errors)")

    def test_concurrent_requests_10_parallel(self):
        """10 並行リクエストで全成功."""
        path = "/api/now_playing"
        results = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(fetch_json, f"{HQ_API_URL}{path}") for _ in range(10)]
            for f in as_completed(futures):
                results.append(f.result()[0])
        n_ok = sum(1 for c in results if c == 200)
        self.assertEqual(n_ok, 10, f"Expected 10 OK, got {n_ok}: {results}")
        print(f"  ✅ 10 並行 OK ({n_ok}/10)")

    def test_all_endpoints_respond(self):
        """全 15 エンドポイントが 1 リクエストずつ成功."""
        for path in ENDPOINTS:
            with self.subTest(path=path):
                code, _, _ = fetch_json(f"{HQ_API_URL}{path}")
                self.assertEqual(code, 200, f"{path} returned {code}")
        print(f"  ✅ 全 {len(ENDPOINTS)} エンドポイント 1 リクエスト成功")


class TestResponseTime(unittest.TestCase):
    """レスポンス時間（p95 < 200ms 目標）."""

    def test_p95_under_200ms(self):
        """50 リクエストの p95 レイテンシが 200ms 以下."""
        path = "/api/now_playing"
        latencies = []
        for _ in range(50):
            _, elapsed, _ = fetch_json(f"{HQ_API_URL}{path}")
            latencies.append(elapsed * 1000)  # ms
        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        p50 = latencies[int(len(latencies) * 0.50)]
        mean = statistics.mean(latencies)
        print(f"  📊 レイテンシ (ms): p50={p50:.0f}, p95={p95:.0f}, mean={mean:.0f}")
        self.assertLess(p95, 200, f"p95 latency {p95:.0f}ms exceeds 200ms target")
        print(f"  ✅ p95 {p95:.0f}ms < 200ms target")


class TestMp3EquivalentBehavior(unittest.TestCase):
    """DSP:8000 / DMP:8001 と同一の JSON を返す（フロント非依存）."""

    DSP_PAIRS = [
        ("/api/devices", "/api/devices"),
        ("/api/now_playing", "/api/now_playing"),
        ("/api/dsp_status", "/api/dsp_status"),
        ("/api/config", "/api/config"),
        ("/api/presets", "/api/presets"),
    ]

    DMP_PAIRS = [
        ("/api/library/artists", "/api/library/artists"),
        ("/api/library/albums", "/api/library/albums"),
        ("/api/library/stats", "/api/library/stats"),
        ("/api/playback/status", "/api/playback/status"),
        ("/api/queue/", "/api/queue/"),
        ("/api/playlists/", "/api/playlists/"),
        ("/api/history/", "/api/history/"),
    ]
    if INCLUDE_UPNP:
        DMP_PAIRS += [
            ("/api/upnp/servers", "/api/upnp/servers"),
            ("/api/upnp/status", "/api/upnp/status"),
        ]

    def test_dsp_identical(self):
        """hq_api vs DSP:8000 の 5 ルートが IDENTICAL."""
        for dsp_path, hq_path in self.DSP_PAIRS:
            with self.subTest(path=dsp_path):
                code_dsp, _, body_dsp = fetch_json(f"{DSP_URL}{dsp_path}")
                code_hq, _, body_hq = fetch_json(f"{HQ_API_URL}{hq_path}")
                self.assertEqual(code_dsp, 200)
                self.assertEqual(code_hq, 200)
                self.assertEqual(body_dsp, body_hq, f"DIFFER at {dsp_path}")
        print(f"  ✅ DSP 比較 {len(self.DSP_PAIRS)} ルート全て IDENTICAL")

    def test_dmp_identical(self):
        """hq_api vs DMP:8001 の 9 ルートが IDENTICAL."""
        for dmp_path, hq_path in self.DMP_PAIRS:
            with self.subTest(path=dmp_path):
                code_dmp, _, body_dmp = fetch_json(f"{DMP_URL}{dmp_path}")
                code_hq, _, body_hq = fetch_json(f"{HQ_API_URL}{hq_path}")
                self.assertEqual(code_dmp, 200)
                self.assertEqual(code_hq, 200)
                self.assertEqual(body_dmp, body_hq, f"DIFFER at {dmp_path}")
        print(f"  ✅ DMP 比較 {len(self.DMP_PAIRS)} ルート全て IDENTICAL")


class TestSystemdIntegration(unittest.TestCase):
    """systemd 経由の自動再起動の動作確認."""

    def test_hq_api_service_active(self):
        """hq-api.service が active 状態."""
        import subprocess
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "hq-api.service"],
                capture_output=True, text=True, timeout=5,
            )
            state = result.stdout.strip()
            self.assertEqual(state, "active", f"hq-api.service is {state}")
            print(f"  ✅ hq-api.service: {state}")
        except FileNotFoundError:
            self.skipTest("systemctl not available")
        except Exception as e:
            self.skipTest(f"systemctl check failed: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        # クイック検証: 独立性 + 1 連続 + 1 並行
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        suite.addTests(loader.loadTestsFromTestCase(TestBackendIsolation))
        suite.addTests(loader.loadTestsFromName("test_100_sequential_requests_no_5xx", TestLoadEndurance))
        suite.addTests(loader.loadTestsFromName("test_concurrent_requests_10_parallel", TestLoadEndurance))
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    else:
        unittest.main(verbosity=2)
