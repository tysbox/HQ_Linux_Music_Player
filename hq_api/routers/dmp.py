"""DMP ルータの re-import（Phase 3a-4）.

dmp/backend/app/routers/* を import して include する。
dmp/backend を sys.path に追加するだけで、dmp 側コードには一切手を加えない。
"""
import os
import sys

# dmp/backend をパスに追加（既存コードの import を満たすため）
_DMP_BACKEND = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "dmp", "backend"
)
if _DMP_BACKEND not in sys.path:
    sys.path.insert(0, _DMP_BACKEND)

# DMP ルータを import
from app.routers import library, playback, queue, history, playlists, upnp  # noqa: E402

# WebSocket は別 ADR で扱うため、Phase 3a-4 では除外
routers = [
    library.router,
    playback.router,
    queue.router,
    history.router,
    playlists.router,
    upnp.router,
]

__all__ = ["routers"]
