"""Legacy DMP entrypoint shim — DO NOT USE FOR NEW CODE.

This module exists only for backward compatibility during transition.
All DMP routes are now served via hq_api.main (port 8002).
"""

import logging

# Prevent accidental execution as main entrypoint
if __name__ != "__main__":
    # Allow import for re-export purposes only
    pass
else:
    raise RuntimeError(
        "dmp/backend/app/main.py is a legacy shim. Use hq_api.main (port 8002) instead."
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("app.services.upnp_service").setLevel(logging.DEBUG)

# Re-export routers for hq_api consumption (no FastAPI app creation)
from app.routers import library, playback, queue, history, playlists, websocket, upnp

__all__ = [
    "library",
    "playback", 
    "queue",
    "history",
    "playlists",
    "websocket",
    "upnp",
]

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
    from app.services.mpd_service import mpd_probe_connection
    try:
        async with mpd_probe_connection():
            mpd_ok = True
    except Exception:
        mpd_ok = False
    return {
        "status": "ok" if mpd_ok else "degraded",
        "mpd": "connected" if mpd_ok else "disconnected",
        "soundgenic": "pending",
    }
