"""MPD クライアント共通実装（async 専用）.

DSP / DMP の両バックエンドから利用される MPD I/O の共通層。
FastAPI 等の Web フレームワークには依存しない（純粋ロジック）。

設計方針:
  - プロセス全体で 1 本の非同期接続を保持する
  - asyncio.Lock で多重呼び出しを防ぐ（python-mpd2 は async セーフではない）
  - 接続断時は ping() 失敗をトリガに自動再接続する
  - 環境変数 MPD_HOST / MPD_PORT で接続先を上書き可能
  - メインのイベントloop上の  で動作すること前提とする
    （同期 def ハンドラから sync_* 経由で呼ぶと、別イベントloopの が
     立って _lock が別物になり、ソケットが混線する）

  利用例:
    async def handler():
        async with mpd_connection() as c:
            status = await c.status()
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from mpd.asyncio import MPDClient

logger = logging.getLogger(__name__)

# 接続設定（環境変数で上書き可能）
MPD_HOST = os.getenv("MPD_HOST", "localhost")
try:
    MPD_PORT = int(os.getenv("MPD_PORT", "6600"))
except ValueError:
    MPD_PORT = 6600


# ─────────────────────────────────────────────────────────────────────
# プロセス全体で共有する非同期接続とロック
# ─────────────────────────────────────────────────────────────────────
_client: Optional[MPDClient] = None
_lock = asyncio.Lock()


async def _connect() -> MPDClient:
    c = MPDClient()
    await c.connect(MPD_HOST, MPD_PORT)
    logger.info("MPD接続確立 (%s:%d)", MPD_HOST, MPD_PORT)
    return c


@asynccontextmanager
async def mpd_connection(*_args, **_kwargs):
    """共有 MPD 接続のコンテキストマネージャ.

    ロックを yield 中も維持し、MPD コマンドの混線を防ぐ。
    必ずメインの async イベントloopの で await すること。
    NOTE: idle() 待機には使わないこと — ロックを占有し続け、
    /health 等の通常リクエストが永久に待たされる。idle 待機には
    mpd_idle_connection() を使うこと。
    purpose 引数は後方互換のため無視する。
    """
    global _client
    async with _lock:
        if _client is None:
            _client = await _connect()
        try:
            await _client.ping()
        except Exception:
            logger.warning("MPD切断検出、再接続します")
            try:
                _client = await _connect()
            except Exception as e:
                _client = None
                raise ConnectionError(f"MPD再接続失敗: {e}")
        try:
            yield _client
        except Exception as e:
            logger.error(f"MPD操作エラー: {e}")
            raise


@asynccontextmanager
async def mpd_idle_connection():
    """idle() 待機専用の独立 MPD 接続.

    共有ロックを使わず、毎回新規接続を作成・破棄する。
    idle() は応答まで無期限にブロックするため、共有接続で
    待機すると全ての通常リクエスト (/health, /api/*) が
    デッドロックする。これを分離するための専用経路。
    """
    c: Optional[MPDClient] = None
    try:
        c = await _connect()
        yield c
    finally:
        if c is not None:
            try:
                c.disconnect()
            except Exception:
                pass


async def get_client() -> MPDClient:
    """互換性のためのユーティリティ。既存のグローバルクライアントを返す。"""
    global _client
    async with _lock:
        if _client is None:
            _client = await _connect()
        try:
            await _client.ping()
        except Exception:
            try:
                _client = await _connect()
            except Exception as e:
                _client = None
                raise ConnectionError(f"MPD再接続失敗: {e}")
        return _client
