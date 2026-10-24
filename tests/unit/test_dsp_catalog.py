#!/usr/bin/env python3
"""ヘッドホン カタログ (同梱 AutoEq 測定データ 2,810 機種) の単体テスト.

Bisen-DSP-System の計測カタログ (headphoneCatalog.ts 45 機種 +
headphoneCatalog_oratory_crinacle.ts 2,771 機種) を config/profiles/catalog.json
へ移行したものの検証。

検証事項:
- カタログが同梱され、2,800+ 機種が取得できること
- エントリのプロファイルが検証を通ること (変換時検証の代表サンプル再確認)
- 検索 (AND 一致・人気順・limit・ゼロヒット) の動作
- 取込み (実体化→ロード一致・冪等・未検出) の動作 — 非破壊

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_catalog -v

非破壊: 実 PROFILES_DIR (~/.config/audiophile/profiles) は書き換えない
"""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

# プロジェクトルートをパスに追加
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp import profiles as profiles_mod  # noqa: E402


class TestBundledCatalog(unittest.TestCase):
    """config/profiles/catalog.json の内容検証."""

    def test_catalog_bundled_with_2800_plus_models(self):
        """カタログに 2,800+ 機種が同梱されていること (利用者要件)."""
        catalog = profiles_mod.load_catalog()
        self.assertGreaterEqual(catalog["total"], 2800)
        self.assertEqual(len(catalog["entries"]), catalog["total"])

    def test_catalog_profiles_valid_sample(self):
        """エントリのプロファイルがスキーマ検証を通ること (代表サンプル).

        全件検証は変換スクリプト (scripts/convert_bisen_catalog.py) が実施済み。
        jsonschema 検証は 1 件数 ms のため、先頭 100 + 末尾 100 で代表確認する。
        """
        from backend.dsp.profiles import validate_profile
        catalog = profiles_mod.load_catalog()
        entries = catalog["entries"]
        sample = entries[:100] + entries[-100:]
        for e in sample:
            valid, errors = validate_profile(e["profile"])
            self.assertTrue(valid, f"{e['id']}: {errors}")

    def test_catalog_entries_have_required_fields(self):
        """エントリが必須フィールド (参照 ID / brand / model / profile) を持つこと."""
        catalog = profiles_mod.load_catalog()
        for e in catalog["entries"][:50]:
            self.assertIn("id", e)
            self.assertIn("brand", e)
            self.assertIn("model", e)
            self.assertIn("profile", e)
            self.assertGreaterEqual(len(e["profile"]["bands"]), 1)

    def test_catalog_entry_ids_unique(self):
        """カタログ参照 ID が一意であること."""
        catalog = profiles_mod.load_catalog()
        ids = [e["id"] for e in catalog["entries"]]
        self.assertEqual(len(ids), len(set(ids)))


class TestCatalogSearch(unittest.TestCase):
    """search_catalog の検索ロジック検証."""

    def test_query_hit(self):
        """ブランド名検索がヒットすること."""
        result = profiles_mod.search_catalog("bose")
        self.assertGreater(result["total"], 0)
        names = [f"{e['brand']} {e['model']}" for e in result["entries"]]
        self.assertTrue(any("Bose" in n for n in names))

    def test_and_terms_match(self):
        """複数語は AND 検索になること."""
        result = profiles_mod.search_catalog("sony wh")
        self.assertGreater(result["total"], 0)
        for e in result["entries"]:
            hay = f"{e['brand']} {e['model']} {e['id']}".lower()
            self.assertIn("sony", hay)
            self.assertIn("wh", hay)

    def test_limit_caps_results(self):
        """limit が返却件数を制限すること."""
        result = profiles_mod.search_catalog("", limit=5)
        self.assertEqual(len(result["entries"]), 5)
        self.assertGreaterEqual(result["total"], 5)

    def test_no_hit_returns_empty(self):
        """ゼロヒットは total=0 / entries=[] を返すこと."""
        result = profiles_mod.search_catalog("zzzz-no-such-model")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["entries"], [])


class TestCatalogImport(unittest.TestCase):
    """import_catalog_entry の取込み検証 (非破壊: PROFILES_DIR を差し替え)."""

    def test_import_materializes_profile(self):
        """取込み → 実体化 → ロード一致 → 冪等再取込み."""
        catalog = profiles_mod.load_catalog()
        entry = catalog["entries"][0]
        with tempfile.TemporaryDirectory(prefix="test_catalog_") as tmp:
            with mock.patch.object(profiles_mod, "PROFILES_DIR",
                                   pathlib.Path(tmp)):
                imported = profiles_mod.import_catalog_entry(entry["id"])
                self.assertIsNotNone(imported)
                self.assertEqual(imported["id"], entry["profile"]["id"])
                self.assertEqual(imported["bands"], entry["profile"]["bands"])
                self.assertEqual(imported["preamp_db"],
                                 entry["profile"]["preamp_db"])
                # 冪等: 再取込みでも同一プロファイル ID で上書きされない
                again = profiles_mod.import_catalog_entry(entry["id"])
                self.assertIsNotNone(again)
                self.assertEqual(again["id"], imported["id"])

    def test_import_unknown_entry_returns_none(self):
        """未検出エントリ ID → None."""
        with tempfile.TemporaryDirectory(prefix="test_catalog_") as tmp:
            with mock.patch.object(profiles_mod, "PROFILES_DIR",
                                   pathlib.Path(tmp)):
                self.assertIsNone(
                    profiles_mod.import_catalog_entry("__no_such_entry__"))


class TestCatalogRouter(unittest.TestCase):
    """API エンドポイント関数の直接呼び出し検証 (非破壊・実サービス非依存)."""

    def test_search_endpoint_returns_entries(self):
        """GET /api/dsp/headphones/catalog 相当の検索が動作すること."""
        from hq_api.routers.dsp_headphones import search_catalog_endpoint
        result = search_catalog_endpoint(q="bose", limit=10)
        self.assertGreater(result["total"], 0)
        self.assertLessEqual(len(result["entries"]), 10)
        for e in result["entries"]:
            self.assertIn("id", e)
            self.assertIn("profile", e)

    def test_import_endpoint_unknown_raises_404(self):
        """未検出エントリの取込みは 404 (HQError NOT_FOUND) になること."""
        from fastapi import HTTPException
        from hq_api.routers.dsp_headphones import import_catalog_endpoint
        with self.assertRaises(HTTPException) as ctx:
            import_catalog_endpoint("__no_such_entry__")
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
