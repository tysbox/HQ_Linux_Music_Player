"""ws/levels — CamillaDSP レベル中継 WebSocket (Bisen移植 Phase 2 / Step 2-2).

CamillaDSP (:1234) の実再生レベル (playback peak/rms) を 10Hz で GUI に中継する。
Bisen の VU (レンダラ peakL/peakR) 相当を、HQ では CamillaDSP の
GetPlaybackSignalPeak/Rms から供給する (= DSP 後 = DAC へ出る直前の実レベル)。

README 原則「GUI は必ず 8003 経由」に従い、ブラウザは :1234 を直接参照しない。

非破壊: 読み取り専用の WebSocket。CamillaDSP への影響なし。
"""
import asyncio
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# 中継間隔 (既定 100ms = 10Hz。VU メータの十分な更新率)
POLL_INTERVAL = float(os.getenv("HQ_LEVELS_INTERVAL", "0.1"))


def _connect_camilla():
    """CamillaDSP へのクライアントを生成・接続 (失敗時 None)。同期関数。"""
    from camilladsp import CamillaClient

    host = os.getenv("CAMILLA_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("CAMILLA_PORT", "1234"))
    except ValueError:
        port = 1234
    client = CamillaClient(host, port)
    client.connect()
    return client


def _disconnect_camilla(client) -> None:
    """CamillaDSP クライアントを切断 (例外は握りつぶす)。同期関数。"""
    try:
        client.disconnect()
    except Exception:
        pass


def _read_levels(client) -> dict:
    """playback peak/rms [dB/ch] を読む。同期関数。"""
    peak = client.levels.playback_peak()
    rms = client.levels.playback_rms()
    return {
        "peak": [float(x) for x in peak],
        "rms": [float(x) for x in rms],
    }


def _read_bisen_levels() -> dict | None:
    """bisen-dspd 経路時のレベル供給 (Phase 4 / Step 4-1)。同期関数。

    デーモンが routing 中 (tube/restore 有効) のとき、CamillaDSP の
    playback peak はループバック sub1 に書いた値であって DAC へ出る値ではない。
    デーモンの get peaks (DSP 後 = DAC へ出す実信号) を優勝供給する:
      - true_peak_db (TruePeakLimiter 4x OS 検出値) を両 ch の peak へ
      - peak_db_l/r (DSP 後サンプルピーク) を rms 代用に
    デーモン非応答・routing=0 なら None (CamillaDSP 供給へフォールバック)。
    """
    from backend.dsp import bisen_daemon

    try:
        st = bisen_daemon.daemon_status()
        if st.get("routing") != "1" or st.get("playback_open") != "1":
            return None
        pk = bisen_daemon.daemon_peaks()
        tp = pk.get("true_peak_db")
        if tp is None:
            return None
        tpv = float(tp)
        pl = float(pk.get("peak_db_l", tpv))
        pr = float(pk.get("peak_db_r", tpv))
        return {
            "peak": [tpv, tpv],
            "rms": [pl, pr],
            "source": "bisen-dspd",
        }
    except Exception:
        return None


@router.websocket("/ws/levels")
async def websocket_levels(websocket: WebSocket):
    """CamillaDSP レベル中継。切断/再接続は自動 (GUI は接続しっぱなしで良い)。"""
    await websocket.accept()
    logger.info("/ws/levels 接続確立")

    client = None
    try:
        client = await asyncio.to_thread(_connect_camilla)
    except Exception as e:
        logger.warning("ws_levels: CamillaDSP 初期接続失敗: %s", e)

    try:
        while True:
            if client is None:
                # 再接続試行 (失敗時もループは継続)
                await websocket.send_text(json.dumps({"error": "dsp_disconnected"}))
                await asyncio.sleep(2.0)
                try:
                    client = await asyncio.to_thread(_connect_camilla)
                except Exception:
                    pass
                continue

            try:
                # Phase 4 (Step 4-1): bisen-dspd 経路時はデーモンの true-peak
                # (DAC へ出す実信号) を優先。非経路時は CamillaDSP 供給のまま。
                levels = await asyncio.to_thread(_read_bisen_levels)
                if levels is None:
                    levels = await asyncio.to_thread(_read_levels, client)
                await websocket.send_text(json.dumps(levels))
                await asyncio.sleep(POLL_INTERVAL)
            except WebSocketDisconnect:
                raise
            except Exception as e:
                # CamillaDSP 落下 → クライアント作り直して再試行
                logger.warning("ws_levels: 読み取り失敗 (%s) — 再接続します", e)
                await asyncio.to_thread(_disconnect_camilla, client)
                client = None
    except WebSocketDisconnect:
        logger.info("/ws/levels 切断")
    finally:
        if client is not None:
            await asyncio.to_thread(_disconnect_camilla, client)
