"""DSP 機能のルータ（Phase 3a-2: 最小移植）.

backend/main.py から以下のみを移植:
- GET /api/devices
- GET /api/now_playing

レスポンス形式は DSP:8000 と完全互換を保つ。
"""
import os
import re
import subprocess

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from hqmplayer_core.mpd import mpd_connection
from hqmplayer_core.meta import format_now_playing

router = APIRouter()


def _detect_alsa_cards() -> tuple[str | None, str | None]:
    """`aplay -l` を解析して (usb_card, pch_card) のカード番号を返す."""
    usb_card = None
    pch_card = None
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        res = subprocess.run(["aplay", "-l"], capture_output=True, text=True, env=env)
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
    return usb_card, pch_card


@router.get("/api/devices")
def get_devices():
    """DSP:8000 と同一の JSON を返す."""
    devices = []
    try:
        usb_card, pch_card = _detect_alsa_cards()

        if usb_card:
            devices.append({"id": f"plughw:{usb_card},0", "name": f"USB DAC (hw:{usb_card},0)"})
        else:
            devices.append({"id": "none", "name": "USB DAC (Not Connected)"})

        if pch_card:
            devices.append({"id": f"plughw:{pch_card},0", "name": f"PC Speaker / Headphone (hw:{pch_card},0)"})
        else:
            devices.append({"id": "plughw:1,0", "name": "PC Speaker / Headphone (hw:1,0)"})

        devices.append({"id": "plug:bluealsa", "name": "Bluetooth (A2DP)"})

    except Exception as e:
        devices.append({"id": "error", "name": str(e)})

    return devices


@router.get("/api/now_playing")
async def get_now_playing():
    """DSP:8000 と同一の JSON を返す."""
    try:
        async with mpd_connection() as c:
            st = await c.status()
            so = await c.currentsong()
        return format_now_playing(st, so)
    except Exception:
        return JSONResponse(status_code=503, content={"error": "MPD offline"})
