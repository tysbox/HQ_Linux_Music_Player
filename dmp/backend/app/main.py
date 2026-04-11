import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import library, playback, queue, history, playlists, websocket, upnp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("app.services.upnp_service").setLevel(logging.DEBUG)

app = FastAPI(
    title="HQ Linux Music Player — DMP Backend",
    description="Digital Media Player バックエンドAPI（ローカルライブラリ + MPD制御）",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://0.0.0.0:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(library.router)
app.include_router(playback.router)
app.include_router(queue.router)
app.include_router(history.router)
app.include_router(playlists.router)
app.include_router(websocket.router)
app.include_router(upnp.router)


@app.get("/")
async def root():
    return {
        "service": "DMP Backend",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """ヘルスチェック（systemd watchdog用）"""
    from app.services.mpd_service import get_client
    try:
        client = await get_client()
        await client.ping()
        mpd_ok = True
    except Exception:
        mpd_ok = False
    return {
        "status": "ok" if mpd_ok else "degraded",
        "mpd": "connected" if mpd_ok else "disconnected",
        "soundgenic": "pending",
    }
