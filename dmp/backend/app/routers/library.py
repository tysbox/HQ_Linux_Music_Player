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
        result = []
        try:
            result = await client.search("any", q)
        except Exception:
            result = []

        if not result:
            # フォールバック：個別検索とファイル名検索をマージ
            r1 = await client.search("title", q)
            r2 = await client.search("artist", q)
            r3 = await client.search("album", q)
            r4 = await client.search("file", q)
            seen = set()
            result = []
            for song in r1 + r2 + r3 + r4:
                uri = song.get("file")
                if uri not in seen:
                    seen.add(uri)
                    result.append(song)

        tracks = [_song_to_track(song) for song in result[:100]]  # 上限100件
        return {"tracks": tracks, "total": len(tracks), "query": q}


@router.get("/artwork")
async def get_artwork(
    uri: str = Query(...),
    artist: str = Query(""),
    album: str = Query(""),
):
    """アルバムアート取得（MPD readpicture 経由 + iTunes フォールバック）.

    旧実装は MPD readpicture のみで、UPnP 経由の URI では必ず 404 になっていた。
    hqmplayer_core.art.resolve_art（local → MPD → iTunes → placeholder の
    4段フォールバック）へ委譲し、GUI 側で 404 にならないようにする。
    artist / album が渡，iTunes 検索フォールバックが有効になる。
    """
    from fastapi.responses import RedirectResponse, Response

    from hqmplayer_core.art import get_cached_art, resolve_art, save_cached_art
    from hqmplayer_core.mpd import mpd_connection
    import requests

    async def _mpd_readpicture(u):
        async with mpd_connection() as c:
            try:
                return await c.readpicture(u)
            except Exception:
                return None

    async def _mpd_albumart(u):
        async with mpd_connection() as c:
            try:
                return await c.albumart(u)
            except Exception:
                return None

    if artist and album:
        cached_url = get_cached_art(artist, album)
        if cached_url:
            return RedirectResponse(url=cached_url, status_code=307)

    result = await resolve_art(
        file=uri,
        artist=artist,
        album=album,
        mpd_readpicture=_mpd_readpicture,
        mpd_albumart=_mpd_albumart,
        http_get=requests.get,
    )
    if result.source == "itunes" and result.redirect_url:
        if artist and album:
            save_cached_art(artist, album, result.redirect_url)
        return RedirectResponse(url=result.redirect_url, status_code=307)
    if result.content is not None:
        return Response(content=result.content, media_type=result.media_type or "image/jpeg")
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
