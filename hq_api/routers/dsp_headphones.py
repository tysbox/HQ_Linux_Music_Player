"""ヘッドホン カタログ ルータ (Bisen移植 Phase 1 / Step 1-5b).

同梱 AutoEq 測定カタログ (2,810 機種: oratory1990 / crinacle / 定番) の検索・取込み。

- GET  /api/dsp/headphones/catalog               — 検索 (オフライン・即応)
- POST /api/dsp/headphones/catalog/{id}/import   — 取込み (プロファイル実体化)

取込み後は既存のプロファイル選択経路で適用する:
  headphone_profile (AudioConfig) + GET /api/dsp/profiles + POST /api/dsp_update
"""
from fastapi import APIRouter, Query

from hq_api.errors import not_found

router = APIRouter()


@router.get("/api/dsp/headphones/catalog")
def search_catalog_endpoint(
    q: str = Query("", description="ブランド/モデル名 (スペース区切り AND 検索)"),
    limit: int = Query(50, ge=1, le=200, description="最大返却件数"),
):
    """同梱カタログ (AutoEq 測定データ) を検索する."""
    from backend.dsp.profiles import search_catalog
    return search_catalog(q, limit)


@router.post("/api/dsp/headphones/catalog/{entry_id}/import")
def import_catalog_endpoint(entry_id: str, force: bool = Query(False)):
    """カタログエントリを選択可能なプロファイルとして取り込む (冪等)."""
    from backend.dsp.profiles import import_catalog_entry
    profile = import_catalog_entry(entry_id, force=force)
    if profile is None:
        raise not_found(f"catalog entry '{entry_id}' not found or invalid")
    return {"status": "success", "profile_id": profile["id"], "profile": profile}
