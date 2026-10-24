"""DSP 機能のルータ（Phase 3a-2: 最小移植）.

backend/main.py から以下のみを移植:
- GET /api/devices
- GET /api/now_playing

レスポンス形式は 旧DSP と完全互換を保つ。
"""
import os
import re
import shutil
import subprocess
import time

from fastapi import APIRouter

from hqmplayer_core.mpd import mpd_connection
from hqmplayer_core.meta import format_now_playing
from hq_api.errors import service_unavailable, dsp_offline

router = APIRouter()

# 2026-10-03 v3.1: 実体は backend.dsp.alsa (単一ソース) に移設。
# 本名は互換ラッパとして残す (将来の patch・参照維持)。
from backend.dsp.alsa import detect_alsa_cards as _alsa_detect_impl


def _detect_alsa_cards() -> tuple[str | None, str | None]:
    """`aplay -l` を解析して (usb_card, pch_card) を返す (委譲: backend.dsp.alsa)."""
    return _alsa_detect_impl()


def _detect_alsa_cards_fresh() -> tuple[str | None, str | None]:
    """キャッシュを無視して ALSA カードを再検出する。

    /api/devices は GUI の OUTPUT 一覧を駆動するため、USB DAC の着脱を
    反映できることが重要。alsa.py のキャッシュ (既定 60 秒) では
    DAC 再接続後も 60 秒間 "USB DAC (Not Connected)" のままになる。
    """
    return _alsa_detect_impl(force=True)


@router.get("/api/devices")
def get_devices():
    """旧DSP と同一の JSON を返す."""
    devices = []
    try:
        usb_card, pch_card = _detect_alsa_cards_fresh()

        if usb_card:
            devices.append({"id": f"plughw:{usb_card},0", "name": f"USB DAC (hw:{usb_card},0)", "available": True})
        else:
            devices.append({"id": "none", "name": "USB DAC (Not Connected)", "available": False})

        if pch_card:
            devices.append({"id": f"plughw:{pch_card},0", "name": f"PC Speaker / Headphone (hw:{pch_card},0)", "available": True})
        else:
            devices.append({"id": "plughw:1,0", "name": "PC Speaker / Headphone (hw:1,0)", "available": False})

        # Bluetooth は BT 接続時のみ ALSA PCM が現れる (移植診断用に available を付与)
        try:
            from backend.dsp.state_manager import bluetooth_sink_available
            bt_available = bool(bluetooth_sink_available())
        except Exception:
            bt_available = True  # 判定不能時は従来通り利用可能扱い
        devices.append({"id": "plug:bluealsa", "name": "Bluetooth (A2DP)", "available": bt_available})

    except Exception as e:
        devices.append({"id": "error", "name": str(e)})

    return devices


@router.get("/api/now_playing")
async def get_now_playing():
    """旧DSP と同一の JSON を返す."""
    try:
        async with mpd_connection() as c:
            st = await c.status()
            so = await c.currentsong()
        return format_now_playing(st, so)
    except Exception:
        raise service_unavailable("MPD offline")


@router.get("/api/dsp_status")
def get_dsp_status():
    """CamillaDSP 状態。旧DSP と同一の JSON を返す (移植対応: env)."""
    c = None
    try:
        from camilladsp import CamillaClient
        _host = os.getenv("CAMILLA_HOST", "127.0.0.1")
        try:
            _port = int(os.getenv("CAMILLA_PORT", "1234"))
        except ValueError:
            _port = 1234
        c = CamillaClient(_host, _port)
        c.connect()
        version_info = c.cdsp_version
        st = c.general.state()
        return {"status": "running", "version": version_info, "state": st}
    except Exception as e:
        raise dsp_offline(str(e))
    finally:
        if c is not None:
            try:
                c.disconnect()
            except Exception:
                pass
