"""
UPnP ライブラリルーター
Soundgenic + Asset UPnP の両サーバーに対応。
server_id パラメータで切り替え（デフォルト: soundgenic）。
"""
from fastapi import APIRouter, HTTPException, Query
from app.services import upnp_service
from app.models.track import Track

router = APIRouter(prefix="/api/upnp", tags=["upnp"])


def _item_to_track(item: dict) -> Track:
    return Track(
        id=f"upnp::{item['id']}",
        title=item.get("title", "Unknown"),
        artist=item.get("artist", "Unknown Artist"),
        album=item.get("album", "Unknown Album"),
        track_number=item.get("track_number"),
        duration=item.get("duration"),
        source="upnp",
        uri=item.get("uri", ""),
        artwork_url=item.get("artwork_url"),
    )


@router.get("/servers")
async def list_servers():
    """全UPnPサーバーの接続状態を返す"""
    return {"servers": await upnp_service.status_all()}


@router.get("/status")
async def server_status(server: str = Query("soundgenic")):
    """指定サーバーの接続状態確認"""
    try:
        srv = upnp_service.get_server(server)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    reachable = await upnp_service.is_reachable(server)
    return {
        "id":        server,
        "name":      srv["name"],
        "ip":        srv["ip"],
        "reachable": reachable,
    }


@router.get("/browse")
async def browse(
    id:     str = Query("0",          description="UPnP ObjectID"),
    server: str = Query("soundgenic", description="サーバーID"),
):
    """ContentDirectoryをブラウズ"""
    try:
        items = await upnp_service.browse(server, id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"UPnP接続エラー: {e}")

    containers = [
        {
            "type":        "container",
            "id":          i["id"],
            "title":       i["title"],
            "child_count": i.get("child_count"),
        }
        for i in items if i["type"] == "container"
    ]
    tracks = [_item_to_track(i) for i in items if i["type"] == "item"]

    return {
        "server":     server,
        "object_id":  id,
        "containers": containers,
        "tracks":     tracks,
        "total":      len(items),
    }


@router.get("/search")
async def search(
    q:      str = Query(..., min_length=1),
    server: str = Query("soundgenic"),
):
    """ライブラリ検索（タイトル・アーティスト・アルバム横断）"""
    try:
        items = await upnp_service.search(server, q)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    tracks = [_item_to_track(i) for i in items]
    return {"server": server, "query": q, "tracks": tracks, "total": len(tracks)}
