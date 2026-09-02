"""MPD クライアント共通実装.

DSP / DMP の両バックエンドから利用される MPD I/O の共通層。
FastAPI 等の Web フレームワークには依存しない（純粋ロジック）。

設計方針:
  - プロセス全体で 1 本の非同期接続を保持する
  - asyncio.Lock で多重呼び出しを防ぐ（python-mpd2 は async セーフではない）
  - 接続断時は ping() 失敗をトリガに自動再接続する
  - 環境変数 MPD_HOST / MPD_PORT で接続先を上書き可能
  - 同期 I/O からも使えるよう、サブスレッドで async を実行する薄いランブを提供
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional, Any, List

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
async def mpd_connection():
    """共有 MPD 接続のコンテキストマネージャ.

    ロックを yield 中も維持し、MPD コマンドの混線を防ぐ。
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


# ─────────────────────────────────────────────────────────────────────
# 同期 I/O 用ランブ（DSP backend などから使用）
# ─────────────────────────────────────────────────────────────────────
# 同期コードから async 接続を使うため、専用スレッドでイベントループを回す。
# 各 sync_* 関数はスレッドプール上で 1 回だけ async を実行する。
_mpd_exec = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mpd-sync")


def _run_sync(coro) -> Any:
    """別スレッドで async coroutine を実行し、結果を返す.

    MPDClient の内部 reader タスク（__run() コルーチン）が
    loop.close() 後も生存したままになる問題を避けるため、
    終了前に残っているタスクを明示的にキャンセルする。
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        # MPDClient の内部タスクを先に停止してからループを閉じる
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                # キャンセルが伝播するのを待つ（短時間タイムアウト）
                loop.run_until_complete(
                    asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=1.0,
                    )
                )
        except Exception:
            # クリーンアップ中の例外は握りつぶす（本来の戻り値を優先）
            pass
        finally:
            loop.close()


def sync_status() -> dict:
    """MPD の status() を同期取得."""
    async def _get():
        async with mpd_connection() as c:
            return await c.status()
    return _run_sync(_get())


def sync_currentsong() -> dict:
    """MPD の currentsong() を同期取得."""
    async def _get():
        async with mpd_connection() as c:
            return await c.currentsong()
    return _run_sync(_get())


def sync_idle(*subsystems: str) -> List[str]:
    """MPD の idle() を同期実行し、変化したサブシステム名のリストを返す."""
    async def _get():
        async with mpd_connection() as c:
            # mpd.asyncio の idle は async iterator を返すので 1 回分だけ消費する
            result: List[str] = []
            async for changed in c.idle(*subsystems):
                result.append(changed)
                # 1 回分のサブシステム変更だけ消費して返す
                break
            return result
    return _run_sync(_get())


def sync_readpicture(uri: str) -> Optional[dict]:
    """MPD の readpicture() を同期実行（失敗時は None）。"""
    async def _get():
        async with mpd_connection() as c:
            try:
                return await c.readpicture(uri)
            except Exception:
                return None
    return _run_sync(_get())


def sync_albumart(uri: str) -> Optional[dict]:
    """MPD の albumart() を同期実行（失敗時は None）。"""
    async def _get():
        async with mpd_connection() as c:
            try:
                return await c.albumart(uri)
            except Exception:
                return None
    return _run_sync(_get())