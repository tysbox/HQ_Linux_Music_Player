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
# 既定ポートは 6601。/etc/mpd.conf の port 設定および
# config/systemd/mpd.socket.d/override.conf の ListenStream と揃えること
# （パッケージ既定 6600 のままだと接続が不安定になる）。
MPD_HOST = os.getenv("MPD_HOST", "127.0.0.1")
try:
    MPD_PORT = int(os.getenv("MPD_PORT", "6601"))
except ValueError:
    MPD_PORT = 6601


# ─────────────────────────────────────────────────────────────────────
# プロセス全体で共有する非同期接続とロック
# ─────────────────────────────────────────────────────────────────────
_client: Optional[MPDClient] = None
_lock = asyncio.Lock()

#: ping のタイムアウト秒 (2026-10-25 追加)。
#  python-mpd2 の ping() はコマンドキュー経由で実行され **タイムアウトが無い**。
#  MPD が応答しない (TCP は ESTAB のままプロトコル応答が止まる) 状態では
#  ping() が永久にブロックし、_lock を保持したままになる。すると以降の
#  全リクエスト (/health, /api/playback/status 等) がロック待ちで
#  タイムアウトし、GUI が「全く機能しない」状態になる。
#  実測 (2026-10-25 再起動後): hq-api の MPD ソケットが CLOSE-WAIT のまま
#  /health と /api/playback/status が 10 秒タイムアウトしていた。
MPD_PING_TIMEOUT = float(os.getenv("MPD_PING_TIMEOUT", "3.0"))


async def _connect() -> MPDClient:
    c = MPDClient()
    await c.connect(MPD_HOST, MPD_PORT)
    logger.info("MPD接続確立 (%s:%d)", MPD_HOST, MPD_PORT)
    return c


async def _ping_or_raise(client: MPDClient) -> None:
    """ping をタイムアウト付きで実行する。

    タイムアウト時は接続を破棄して例外を送出する。呼び出し側は
    再接続するか、_client を None にして次回に委ねる。
    """
    try:
        await asyncio.wait_for(client.ping(), timeout=MPD_PING_TIMEOUT)
    except asyncio.TimeoutError:
        # 応答が無い接続は使い物にならない。ソケットを閉じてから通知する。
        try:
            client.disconnect()
        except Exception:
            pass
        raise ConnectionError(
            f"MPD ping timeout ({MPD_PING_TIMEOUT}s) — 接続を破棄します"
        )


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
            await _ping_or_raise(_client)
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
    移植対応: 切断時は disconnect() + close()/wait_closed() の両対応で
    CLOSE-WAIT 残留を防ぐ。
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
            # python-mpd2 の disconnect() は __wfile.close() のみで
            # writer の drain/close を待たないため、CLOSE-WAIT が残る
            # ことがある。内部 writer があれば確実に閉じる。
            try:
                wfile = getattr(c, "_MPDClient__wfile", None)
                if wfile is not None:
                    try:
                        wfile.close()
                    except Exception:
                        pass
                    try:
                        await wfile.wait_closed()
                    except Exception:
                        pass
            except Exception:
                pass


async def get_client() -> MPDClient:
    """互換性のためのユーティリティ。

    注意: 返される client は lock 外で使用してはならない。
    通常の MPD 処理では ``mpd_connection()`` を使うこと。
    """
    global _client
    async with _lock:
        if _client is None:
            _client = await _connect()
        try:
            await _ping_or_raise(_client)
        except Exception:
            try:
                _client = await _connect()
            except Exception as e:
                _client = None
                raise ConnectionError(f"MPD再接続失敗: {e}")
        return _client


@asynccontextmanager
async def mpd_probe_connection():
    """health check 用の MPD probe.

    ``get_client()`` の戻り値を lock 外で操作しないため、probe 処理を
    同じ lock 保護された context manager に収める。
    """
    async with mpd_connection() as c:
        await _ping_or_raise(c)
        yield c
