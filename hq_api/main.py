"""hq_api — DSP/DMP 統合バックエンド (port 8002)."""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

tags_metadata = [
    {"name": "health", "description": "ヘルスチェック"},
    {"name": "dsp", "description": "DSP (CamillaDSP) 機能"},
    {"name": "dmp", "description": "DMP (MPD ライブラリ) 機能"},
    {"name": "playback", "description": "再生制御"},
    {"name": "websocket", "description": "WebSocket push"},
    {"name": "art", "description": "アルバムアート"},
    {"name": "history", "description": "再生履歴"},
    {"name": "upnp", "description": "UPnP サーバ"},
]

app = FastAPI(
    title="HQ Linux Music Player — Unified API",
    description="DSP/DMP 統合バックエンド。詳細は HANDOVER.md 参照。",
    version="0.1.0-phase3a",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
    contact={"name": "HQ Linux Music Player"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    # NOTE: CORS spec で `Access-Control-Allow-Origin: *` と
    # `Access-Control-Allow-Credentials: true` の同時指定はブラウザに
    # 拒否される (Chrome の CORS policy)。POST/credentials を使う
    # /api/playback/* 系のため allow_origins を明示列挙する。
    allow_origins=[
        "http://localhost:3002",
        "http://localhost:3000",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:8002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase X-4: メトリクス計測ミドルウェア
from hq_api.middleware import metrics_middleware  # noqa: E402

app.middleware("http")(metrics_middleware)
# Phase 3a-5: 統一エラーハンドラ（ADR-005）
from hq_api.errors import install_error_handlers  # noqa: E402

install_error_handlers(app)# Phase 3a-2: DSP ルータを移植
from hq_api.routers.dsp import router as dsp_router  # noqa: E402

app.include_router(dsp_router)

# Phase 3a-5: DSP 読み取り専用ルータを追加（GET のみ、副作用なし）
from hq_api.routers.dsp_readonly import router as dsp_readonly_router  # noqa: E402

app.include_router(dsp_readonly_router)

# Phase X-3: DSP 書き込み系ルータ（リスク低: ファイル I/O のみ）
from hq_api.routers.dsp_write import router as dsp_write_router  # noqa: E402

app.include_router(dsp_write_router)

# Phase X-3-3: DSP 設定適用ルータ（高音圧: CamillaDSP 再起動 + ALSA 切替）
from hq_api.routers.dsp_apply import router as dsp_apply_router  # noqa: E402

app.include_router(dsp_apply_router)

# Phase 3a-4: DMP ルータを re-import して統合
# 注: websocket ルータは install_error_handlers との相互作用で 403 を返すため除外
from hq_api.routers.dmp import routers as dmp_routers  # noqa: E402

for r in dmp_routers:
    if "websocket" not in str(r.prefix or "") and "websocket" not in str(r.routes):
        app.include_router(r)

# Phase X-2: WebSocket ルータを追加（DMP 由来の /ws/status を上書き）
from hq_api.ws.now_playing import router as ws_now_playing_router  # noqa: E402
from hq_api.ws.status import router as ws_status_router  # noqa: E402
from hq_api.ws.all import router as ws_all_router  # noqa: E402

app.include_router(ws_now_playing_router)
app.include_router(ws_status_router)  # DMP 由来を上書き
app.include_router(ws_all_router)

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


@app.get("/health/metrics")
async def health_metrics():
    """詳細メトリクス。Phase X-4 で追加。"""
    from hq_api.metrics import get_metrics
    return get_metrics().get_summary()
