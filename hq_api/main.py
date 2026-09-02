"""hq_api — 統合バックエンド エントリポイント (Phase 3a).

当面は最小構成:
- /health (MPD 接続確認)
- /api/devices (DSP から移植)
- /api/now_playing (DSP から移植)
- /api/dsp_status (DSP から移植)
- /api/library/artists (DMP から移植)
- /api/playback/status (DMP から移植)

port 8002 で起動し、旧 DSP:8000 / DMP:8001 は生かしたまま並行稼働する。
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="HQ Linux Music Player — Unified API",
    description="DSP / DMP 統合バックエンド (Phase 3a: 並行稼働用)",
    version="0.1.0-phase3a",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Phase 3a-2: DSP ルータを移植
from hq_api.routers.dsp import router as dsp_router  # noqa: E402

app.include_router(dsp_router)

@app.get("/")
async def root():
    return {
        "service": "HQ Unified API",
        "version": "0.1.0-phase3a",
        "status": "running",
        "port": int(os.getenv("HQ_API_PORT", "8002")),
        "note": "DSP:8000 / DMP:8001 と並行稼働中。旧 backend は生かしたまま。",
    }


@app.get("/health")
async def health():
    """ヘルスチェック。MPD 接続可否を確認。"""
    from hqmplayer_core.mpd import get_client
    try:
        client = await get_client()
        await client.ping()
        mpd_ok = True
    except Exception as e:
        mpd_ok = False
        return {
            "status": "degraded",
            "mpd": "disconnected",
            "error": str(e),
        }
    return {
        "status": "ok" if mpd_ok else "degraded",
        "mpd": "connected" if mpd_ok else "disconnected",
    }
