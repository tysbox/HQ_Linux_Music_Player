from fastapi import APIRouter, Query
from app.services.history_service import load_history, clear_history, add_to_history
from app.models.track import Track

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/")
async def get_history(limit: int = Query(100, le=500)):
    """再生履歴を取得"""
    entries = load_history()
    return {
        "history": entries[:limit],
        "total": len(entries),
    }


@router.delete("/")
async def delete_history():
    """再生履歴をクリア"""
    clear_history()
    return {"ok": True}
