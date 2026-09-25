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

# ─────────────────────────────────────────────────────────────────────────────
# DSP 直列化ロック (2026-09-06 課題 2)
# /api/apply, /api/dsp_update, /api/volume はいずれも CamillaDSP の状態・YAML・
# ALSA デバイスに影響するため、短時間に並列実行すると競合して音量リセット・
# YAML 破損・CamillaDSP 未起動などを引き起こす。
# FastAPI の同期エンドポイントは内部でスレッドプール実行されるため、
# threading.Lock で十分直列化できる (async.Lock 化は呼び出し側を async def に
# 変える必要があり、影響範囲が大きくなるため本コミットでは見送り)。
# ─────────────────────────────────────────────────────────────────────────────
import threading  # noqa: E402

DSP_LOCK = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# CORS 許可オリジン (2026-09-06 課題4)
# 環境変数 ALLOWED_ORIGINS (カンマ区切り) で allow_origins を組み立てる。
# 未設定時は localhost 開発用のデフォルトを使う。
# NOTE: CORS spec で `Access-Control-Allow-Origin: *` と
# `Access-Control-Allow-Credentials: true` の同時指定はブラウザに
# 拒否される (Chrome の CORS policy)。POST/credentials を使う
# /api/playback/* 系のため明示列挙する。
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3003",
    "http://127.0.0.1:3003",
    "http://localhost:8002",
]

# 移植対応: HQ_GUI_ORIGINS (カンマ区切り) で LAN/別ホストの GUI を追加。
# 例: HQ_GUI_ORIGINS="http://192.168.0.50:3003" (既定の 192.168.0.211 は廃止)
_extra_gui_origins = [
    o.strip()
    for o in os.getenv("HQ_GUI_ORIGINS", "").split(",")
    if o.strip()
]

_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if _allowed_origins_env:
    _allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
else:
    _allowed_origins = _DEFAULT_ALLOWED_ORIGINS + _extra_gui_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
        "note": "DSP/DMP unified API on port 8002",
    }


@app.get("/health")
async def health():
    """ヘルスチェック。MPD 接続可否を確認し、DSP 死活を非破壊で付与。

    移植対応: HTTP 200 維持で status ok/degraded を返す。
    DSP 停止時も 200 (degraded) のため既存監視・GUI を壊さない。
    """
    from hqmplayer_core.mpd import get_client
    try:
        client = await get_client()
        await client.ping()
    except Exception as e:
        # H-3 修正: MPD 切断時は 503 Service Unavailable を返す（仕様通り）
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"MPD disconnected: {str(e)}")
    # DSP 死活は短タイムアウトで試行し、失敗しても 200 維持 (P1 非破壊拡張)
    dsp_state = "disconnected"
    try:
        import os as _os
        import socket as _socket
        _host = _os.getenv("CAMILLA_HOST", "127.0.0.1")
        try:
            _port = int(_os.getenv("CAMILLA_PORT", "1234"))
        except ValueError:
            _port = 1234
        try:
            _timeout = float(_os.getenv("HQ_HEALTH_DSP_TIMEOUT", "0.5"))
        except ValueError:
            _timeout = 0.5
        with _socket.create_connection((_host, _port), timeout=_timeout):
            dsp_state = "connected"
    except Exception:
        dsp_state = "disconnected"
    # 移植診断用 (additive): Loopback / Bluetooth の実在性を付与。失敗時は None。
    loopback_ok = None
    bt_sink = None
    try:
        from backend.dsp.state_manager import (
            has_loopback_capture_device,
            bluetooth_sink_available,
        )
        loopback_ok = bool(has_loopback_capture_device())
        bt_sink = bool(bluetooth_sink_available())
    except Exception:
        pass
    return {
        "status": "ok" if dsp_state == "connected" else "degraded",
        "mpd": "connected",
        "dsp": dsp_state,
        "loopback": loopback_ok,
        "bt_sink": bt_sink,
    }


@app.get("/health/metrics")
async def health_metrics():
    """詳細メトリクス。Phase X-4 で追加。"""
    from hq_api.metrics import get_metrics
    return get_metrics().get_summary()
