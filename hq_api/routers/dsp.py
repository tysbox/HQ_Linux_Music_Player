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

_ALSA_CARDS_CACHE: tuple[str | None, str | None] | None = None
_ALSA_CARDS_TS: float = 0.0


def _detect_alsa_cards() -> tuple[str | None, str | None]:
    """`aplay -l` を解析して (usb_card, pch_card) のカード番号を返す.

    移植対応: HQ_ALSA_CACHE_TTL (既定60秒) でキャッシュし、aplay 不在時は
    (None, None) を返す。
    """
    global _ALSA_CARDS_CACHE, _ALSA_CARDS_TS
    try:
        _ttl = float(os.getenv("HQ_ALSA_CACHE_TTL", "60"))
    except ValueError:
        _ttl = 60.0
    try:
        import time as _time
        _now = _time.monotonic()
        if _ALSA_CARDS_CACHE is not None and (_now - _ALSA_CARDS_TS) < _ttl:
            return _ALSA_CARDS_CACHE
    except Exception:
        pass
    if shutil.which("aplay") is None:
        return (None, None)
    usb_card = None
    pch_card = None
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        res = subprocess.run(["aplay", "-l"], capture_output=True, text=True, env=env, timeout=5)
        for line in res.stdout.splitlines():
            line_up = line.upper()
            m = re.search(r'(?:card|カード)\s+(\d+)', line, re.IGNORECASE)
            if not m:
                continue
            card_num = m.group(1)
            if "USB" in line_up and usb_card is None:
                usb_card = card_num
            if pch_card is None:
                if ("PCH" in line_up or ("HDA" in line_up and "HDMI" not in line_up) or "CS4208" in line_up):
                    pch_card = card_num
    except Exception:
        pass
    _ALSA_CARDS_CACHE = (usb_card, pch_card)
    try:
        _ALSA_CARDS_TS = _time.monotonic()
    except Exception:
        _ALSA_CARDS_TS = time.monotonic()
    return usb_card, pch_card


@router.get("/api/devices")
def get_devices():
    """旧DSP と同一の JSON を返す."""
    devices = []
    try:
        usb_card, pch_card = _detect_alsa_cards()

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
