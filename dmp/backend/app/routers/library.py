from fastapi import APIRouter, HTTPException, Query
from app.services.mpd_service import mpd_connection, _song_to_track
from app.models.track import Track

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/artists")
async def get_artists():
    """アーティスト一覧（アルファベット順）"""
    async with mpd_connection() as client:
        result = await client.list("albumartist")
        artists = sorted(set(r["albumartist"] for r in result if r.get("albumartist")))
        return {"artists": artists, "total": len(artists)}


@router.get("/artists/{artist}/albums")
async def get_albums_by_artist(artist: str):
    """アーティスト別アルバム一覧"""
    async with mpd_connection() as client:
        result = await client.find("albumartist", artist)
        albums: dict[str, dict] = {}
        for song in result:
            album = song.get("album", "Unknown Album")
            if album not in albums:
                albums[album] = {
                    "name": album,
                    "artist": song.get("albumartist", artist),
                    "date": song.get("date", ""),
                    "track_count": 0,
                    "artwork_url": f"/api/library/artwork?uri={song.get('file', '')}",
                }
            albums[album]["track_count"] += 1
        sorted_albums = sorted(albums.values(), key=lambda x: x.get("date", ""))
        return {"albums": sorted_albums, "total": len(sorted_albums)}


@router.get("/albums")
async def get_all_albums():
    """全アルバム一覧"""
    async with mpd_connection() as client:
        result = await client.list("album", "group", "albumartist")
        albums = []
        for r in result:
            if r.get("album"):
                albums.append({
                    "name": r["album"],
                    "artist": r.get("albumartist", ""),
                })
        albums.sort(key=lambda x: x["name"].lower())
        return {"albums": albums, "total": len(albums)}


@router.get("/albums/{album}/tracks")
async def get_tracks_by_album(album: str, artist: str = Query(None)):
    """アルバム別トラック一覧"""
    async with mpd_connection() as client:
        if artist:
            result = await client.find("album", album, "albumartist", artist)
        else:
            result = await client.find("album", album)

        tracks = [_song_to_track(song) for song in result]
        # ディスク番号→トラック番号でソート
        tracks.sort(key=lambda t: (t.disc_number or 1, t.track_number or 0))
        return {"tracks": tracks, "total": len(tracks)}


@router.get("/search")
async def search_library(q: str = Query(..., min_length=1)):
    """キーワード検索（タイトル・アーティスト・アルバムを横断）"""
    async with mpd_connection() as client:
        # anyタグ検索（MPD 0.21以降対応）
        try:
            result = await client.search("any", q)
        except Exception:
            # フォールバック：個別検索してマージ
            r1 = await client.search("title", q)
            r2 = await client.search("artist", q)
            r3 = await client.search("album", q)
            seen = set()
            result = []
            for song in r1 + r2 + r3:
                uri = song.get("file")
                if uri not in seen:
                    seen.add(uri)
                    result.append(song)

        tracks = [_song_to_track(song) for song in result[:100]]  # 上限100件
        return {"tracks": tracks, "total": len(tracks), "query": q}


@router.get("/artwork")
async def get_artwork(uri: str = Query(...)):
    """アルバムアート取得（MPD readpicture経由）"""
    from fastapi.responses import Response
    async with mpd_connection() as client:
        try:
            pic = await client.readpicture(uri)
            if pic and "binary" in pic:
                mime = pic.get("type", "image/jpeg")
                return Response(content=pic["binary"], media_type=mime)
        except Exception:
            pass
    raise HTTPException(status_code=404, detail="アートワークが見つかりません")


@router.get("/stats")
async def get_library_stats():
    """ライブラリ統計"""
    async with mpd_connection() as client:
        stats = await client.stats()
        return {
            "artists": int(stats.get("artists", 0)),
            "albums": int(stats.get("albums", 0)),
            "songs": int(stats.get("songs", 0)),
            "db_playtime": int(stats.get("db_playtime", 0)),
            "db_updated": stats.get("db_update", ""),
        }
