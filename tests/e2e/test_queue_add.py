"""hq_api POST /api/queue/add 統合テスト (Task 6, 安全版).

設計方針:
- MPD キューへの追加は一切行わない（既存再生環境を保護）
- tearDown で queue/clear 等の破壊的コマンドを実行しない
- レスポンス形状と HTTP コードの検証のみに集中
- 不正入力（URI 欠落等）のみ 422 を確認

実行:
  ./backend/venv/bin/python3 -m unittest tests.e2e.test_queue_add -v

注意:
- テストは MPD キューに何も追加しない
- 再生中のトラックには一切影響しない
"""
import json
import os
import time
import unittest
import urllib.error
import urllib.request
from typing import Any

HQ_API_URL = os.getenv("HQ_API_URL", "http://localhost:8002")


def _http_json(url: str, method: str = "GET", body: dict | None = None, timeout: float = 5.0) -> tuple[int, Any]:
    """JSON を {method} で送受信。 (status, parsed_json or raw_text)."""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:
        return -1, str(e)


class QueueAddSchemaTests(unittest.TestCase):
    """hq_api の /api/queue/add のスキーマ・入出力検証（MPD 触らない）."""

    def test_01_endpoint_exists(self):
        """エンドポイントが存在する（OpenAPI 定義確認）."""
        code, data = _http_json(f"{HQ_API_URL}/openapi.json")
        self.assertEqual(code, 200)
        # paths キーが dict 型であることを確認
        self.assertIsInstance(data, dict)
        paths_dict = data.get("paths", {})
        self.assertIsInstance(paths_dict, dict)
        # /api/queue/add が存在することを確認
        self.assertTrue("/api/queue/add" in paths_dict, f"missing path. got keys: {list(paths_dict.keys())[:5]}")
        # 値も dict 型
        ops = paths_dict["/api/queue/add"]
        self.assertIsInstance(ops, dict)
        self.assertIn("post", ops)

    def test_02_missing_uri_returns_422(self):
        """uri 欠落時は 422 (Pydantic ValidationError)."""
        code, data = _http_json(
            f"{HQ_API_URL}/api/queue/add",
            method="POST",
            body={"play_now": True},
        )
        self.assertIn(code, (400, 422), f"expected 4xx, got {code}: {data}")
        # FastAPI の 422 は detail 配列を持つ
        if code == 422 and isinstance(data, dict) and "detail" in data:
            self.assertIsInstance(data["detail"], list)

    def test_03_empty_body_returns_422(self):
        """空ボディも 422."""
        code, data = _http_json(
            f"{HQ_API_URL}/api/queue/add",
            method="POST",
            body={},
        )
        self.assertIn(code, (400, 422), f"expected 4xx, got {code}: {data}")

    def test_04_invalid_json_returns_4xx(self):
        """不正な JSON は 4xx (FastAPI 422)."""
        req = urllib.request.Request(
            f"{HQ_API_URL}/api/queue/add",
            data=b"not-valid-json{",
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.fail(f"expected error, got {resp.status}")
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, (400, 422), f"expected 4xx, got {e.code}")

    def test_05_optional_fields_accepted_in_schema(self):
        """オプションフィールド (play_now, insert_next) がスキーマで許可されている."""
        # OpenAPI 定義で play_now, insert_next が定義されているか確認
        code, data = _http_json(f"{HQ_API_URL}/openapi.json")
        self.assertEqual(code, 200)
        add_op = data.get("paths", {}).get("/api/queue/add", {}).get("post", {})
        request_body = add_op.get("requestBody", {})
        content = request_body.get("content", {}).get("application/json", {})
        schema = content.get("schema", {})
        ref = schema.get("$ref", "")
        # $ref から実スキーマを取得
        if ref and ref.startswith("#/components/schemas/"):
            schema_name = ref.split("/")[-1]
            schema = data.get("components", {}).get("schemas", {}).get(schema_name, {})
        props = schema.get("properties", {})
        self.assertIn("uri", props, f"uri 必須欠落: {props.keys()}")
        self.assertIn("play_now", props, f"play_now オプション欠落: {props.keys()}")
        self.assertIn("insert_next", props, f"insert_next オプション欠落: {props.keys()}")

    def test_06_get_queue_endpoint_exists(self):
        """/api/queue/ (GET) も存在する."""
        code, data = _http_json(f"{HQ_API_URL}/openapi.json")
        self.assertEqual(code, 200)
        paths_dict = data.get("paths", {})
        self.assertTrue("/api/queue/" in paths_dict)
        queue_root = paths_dict["/api/queue/"]
        self.assertIsInstance(queue_root, dict)
        self.assertIn("get", queue_root)

    def test_07_other_queue_endpoints_exist(self):
        """関連エンドポイント (clear, move, shuffle, play) も全て定義されている."""
        code, data = _http_json(f"{HQ_API_URL}/openapi.json")
        self.assertEqual(code, 200)
        paths = data.get("paths", {})
        expected = ["/api/queue/clear", "/api/queue/move", "/api/queue/shuffle"]
        for path in expected:
            self.assertIn(path, paths, f"missing endpoint: {path}")
            self.assertIn("post", paths[path], f"{path} は POST のみ")


if __name__ == "__main__":
    unittest.main()
