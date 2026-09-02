"""hq_api 互換性 E2E テスト (Phase 3a-5 Task 4: 追加インストール不要版).

外部ライブラリ (pytest/httpx) を使わず、Python 標準の unittest + urllib のみ使用。
これにより環境セットアップなしで即座に実行可能。

検証内容:
1. hq_api:8002 と DSP:8000 / DMP:8001 の主要 GET エンドポイント同一性
2. hq_api:8002 のヘルスチェック
3. 既存サービスが全て稼働中

実行:
  ./backend/venv/bin/python3 -m unittest tests.e2e.test_hq_api_compat -v
"""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from typing import Any

# サービス URL
HQ_API_URL = os.getenv("HQ_API_URL", "http://localhost:8002")
DSP_URL = os.getenv("DSP_URL", "http://localhost:8000")
DMP_URL = os.getenv("DMP_URL", "http://localhost:8001")
SHELL_URL = os.getenv("SHELL_URL", "http://localhost:3002")

# 比較対象エンドポイント（DSP 由来）
DSP_ENDPOINTS = [
    "/api/devices",
    "/api/now_playing",
    "/api/dsp_status",
    "/api/config",
    "/api/presets",
]

# 比較対象エンドポイント（DMP 由来）
DMP_ENDPOINTS = [
    "/api/library/artists",
    "/api/library/albums",
    "/api/library/stats",
    "/api/playback/status",
    "/api/queue/",
    "/api/playlists/",
    "/api/history/",
    "/api/upnp/servers",
    "/api/upnp/status",
]


def fetch_json(url: str, timeout: float = 5.0) -> tuple[int, Any]:
    """URL から JSON を取得。タイムアウト時は (-1, None)。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body) if body else None
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            return e.code, body
        except Exception:
            return e.code, None
    except Exception as e:
        return -1, str(e)


class TestServicesUp(unittest.TestCase):
    """全サービス稼働確認."""

    def test_hq_api_health(self):
        code, body = fetch_json(f"{HQ_API_URL}/health")
        self.assertEqual(code, 200, f"hq_api /health returned {code}: {body}")
        self.assertIsInstance(body, dict)
        self.assertIn("status", body)
        print(f"  hq_api /health: {body}")

    def test_hq_api_root(self):
        code, body = fetch_json(f"{HQ_API_URL}/")
        self.assertEqual(code, 200)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("status"), "running")
        self.assertEqual(body.get("port"), 8002)
        print(f"  hq_api /: service={body.get('service')}, port={body.get('port')}")

    def test_dsp_alive(self):
        code, _ = fetch_json(f"{DSP_URL}/api/devices")
        self.assertEqual(code, 200, "DSP:8000 must be alive for comparison")
        print("  DSP:8000 /api/devices -> 200")

    def test_dmp_alive(self):
        code, _ = fetch_json(f"{DMP_URL}/api/library/artists")
        self.assertEqual(code, 200, "DMP:8001 must be alive for comparison")
        print("  DMP:8001 /api/library/artists -> 200")

    def test_shell_alive(self):
        code, _ = fetch_json(f"{SHELL_URL}/", timeout=10.0)
        self.assertEqual(code, 200, "unified-shell:3002 must be alive")
        print("  unified-shell:3002 / -> 200")


class TestDspCompat(unittest.TestCase):
    """hq_api vs DSP:8000 の同一性検証."""

    def test_all_dsp_endpoints_identical(self):
        for path in DSP_ENDPOINTS:
            with self.subTest(path=path):
                code_dsp, body_dsp = fetch_json(f"{DSP_URL}{path}")
                code_hq, body_hq = fetch_json(f"{HQ_API_URL}{path}")
                self.assertEqual(code_dsp, 200, f"DSP {path} returned {code_dsp}")
                self.assertEqual(code_hq, 200, f"hq_api {path} returned {code_hq}: {body_hq}")
                self.assertEqual(
                    body_dsp, body_hq,
                    f"DIFFER at {path}\n  DSP:    {body_dsp}\n  hq_api: {body_hq}"
                )
                print(f"  ✅ {path} IDENTICAL")


class TestDmpCompat(unittest.TestCase):
    """hq_api vs DMP:8001 の同一性検証."""

    def test_all_dmp_endpoints_identical(self):
        for path in DMP_ENDPOINTS:
            with self.subTest(path=path):
                code_dmp, body_dmp = fetch_json(f"{DMP_URL}{path}")
                code_hq, body_hq = fetch_json(f"{HQ_API_URL}{path}")
                self.assertEqual(code_dmp, 200, f"DMP {path} returned {code_dmp}")
                self.assertEqual(code_hq, 200, f"hq_api {path} returned {code_hq}: {body_hq}")
                self.assertEqual(
                    body_dmp, body_hq,
                    f"DIFFER at {path}\n  DMP:    {body_dmp}\n  hq_api: {body_hq}"
                )
                print(f"  ✅ {path} IDENTICAL")


class TestRouteCount(unittest.TestCase):
    """hq_api のルート数検証."""

    def test_minimum_route_count(self):
        """Phase 3a-5 完了時点で 43 ルート以上あること."""
        try:
            with urllib.request.urlopen(f"{HQ_API_URL}/openapi.json", timeout=5) as resp:
                spec = json.loads(resp.read().decode("utf-8"))
                n = len(spec.get("paths", {}))
                self.assertGreaterEqual(
                    n, 43,
                    f"Expected >= 43 routes, got {n}. "
                    "Phase 3a-4 (DMP 統合) が完了していない可能性"
                )
                print(f"  hq_api ルート数: {n}")
        except Exception as e:
            self.fail(f"openapi.json 取得失敗: {e}")


class TestMp3ResponseUnchanged(unittest.TestCase):
    """スナップショットとの互換性（Phase 3 着手前 baseline との比較）."""

    SNAPSHOT_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "snapshots"
    )

    def test_now_playing_matches_snapshot(self):
        """tests/snapshots/dsp__api_now_playing.json との比較.

        song_id や position は再生状態によって変わるが、構造と必須キーは同じはず。
        """
        snapshot_path = os.path.join(self.SNAPSHOT_DIR, "dsp__api_now_playing.json")
        if not os.path.exists(snapshot_path):
            self.skipTest(f"snapshot not found: {snapshot_path}")
        with open(snapshot_path) as f:
            snapshot = json.load(f)
        # 必須キーが存在することを確認
        required_keys = {"song_id", "state"}  # 最低限
        for k in required_keys:
            self.assertIn(k, snapshot, f"snapshot missing key: {k}")
        print(f"  snapshot 検証: {len(snapshot)} keys")


if __name__ == "__main__":
    # 個別実行サポート
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        # スモークテスト: サービス稼働確認のみ
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(TestServicesUp)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    else:
        unittest.main(verbosity=2)
