from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.responses import Response, RedirectResponse, JSONResponse
from pydantic import BaseModel
from mpd import MPDClient
from camilladsp import CamillaClient
import subprocess, requests, yaml, os, re, time, json, asyncio, threading, wave, shutil
import math
from urllib.parse import urlparse, parse_qs

# Phase 1a: 共通 MPD クライアントを取り込む
from hqmplayer_core.mpd import (
    MPD_HOST as _MPD_HOST,
    MPD_PORT as _MPD_PORT,
    mpd_connection,
)

# Phase 1b: Now Playing 整形ロジックを共通化
from hqmplayer_core.meta import format_now_playing

# Phase 1d: アルバムアート解決を共通化
from hqmplayer_core.art import resolve_art

MPD_HOST = os.getenv("MPD_HOST", "127.0.0.1")
try:
    MPD_PORT = int(os.getenv("MPD_PORT", "6600"))
except ValueError:
    MPD_PORT = 6600

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SWITCH_AUDIO_SCRIPT = os.path.join(BASE_DIR, "scripts", "switch_audio.sh")


# ─────────────────────────────────────────────────────────────────────────────
# MPD 接続ヘルパー
# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 修正: async 関数として共通モジュールの mpd_connection を直接使う。
# sync_* 系は廃止（マルチイベントループの競合を避けるため）。

async def mpd_status() -> dict:
    """MPD の status() を取得（async）。"""
    async with mpd_connection() as c:
        return await c.status()


async def mpd_currentsong() -> dict:
    """MPD の currentsong() を取得（async）。"""
    async with mpd_connection() as c:
        return await c.currentsong()


async def mpd_idle(*subsystems: str):
    """MPD の idle() を実行（変更サブシステムのリストを返す）。"""
    async with mpd_connection() as c:
        result = []
        async for changed in c.idle(subsystems=tuple(subsystems)):
            result.append(changed)
            break
        return result


async def mpd_readpicture(uri: str):
    """MPD の readpicture() を実行（失敗時は None）。"""
    async with mpd_connection() as c:
        try:
            return await c.readpicture(uri)
        except Exception:
            return None


async def mpd_albumart(uri: str):
    """MPD の albumart() を実行（失敗時は None）。"""
    async with mpd_connection() as c:
        try:
            return await c.albumart(uri)
        except Exception:
            return None


# 後方互換のため旧名の関数を残しておく（Phase 2 で削除予定）
def mpd_connect(timeout=3, retries=2):
    """旧 API（接続オブジェクトを返す）。Phase 2 時点では未使用。

    新規コードは async 版の mpd_status / mpd_currentsong / mpd_idle を使うこと。
    旧呼び出し箇所（Phase 2 で撤去予定）のために暫定的に残している。
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            c = MPDClient()
            c.timeout = timeout
            c.idletimeout = timeout
            c.connect(MPD_HOST, MPD_PORT)
            return c
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(0.5)
    raise last_err


async def _playback_watchdog():
    """5秒ごとに MPD 状態を確認 — 共通モジュールの mpd_connection を直接使う"""
    from hqmplayer_core.mpd import mpd_connection as _mpd_conn
    was_playing = False

    while True:
        try:
            await asyncio.sleep(5)

            # Phase 2 修正: メインループ上で直接 mpd_connection を await
            async with _mpd_conn() as c:
                st = await c.status()
            state = st.get("state", "stop")

            if state == "play":
                was_playing = True
            elif state == "stop" and was_playing:
                # 再生再開（DSP backend のみの挙動を維持）
                async with _mpd_conn() as c:
                    await c.play()
                was_playing = False
            elif state in ("pause", "stop"):
                was_playing = False

        except Exception:
            # 接続断時は共通モジュール側で自動再接続される
            await asyncio.sleep(5)


# ─────────────────────────────────────────────────────────────────────────────
# DSP 状態管理（backend.dsp.state_manager に移植済み）
# ─────────────────────────────────────────────────────────────────────────────
from backend.dsp.state_manager import (
    LAST_CONFIG_PATH,
    PRESETS_PATH,
    load_last_config as _load_last_config,
    save_last_config as _save_last_config,
    update_last_config as _update_last_config,
    config_requires_restart as _config_requires_restart,
    normalize_config_for_device as _normalize_config_for_device,
    has_loopback_capture_device as _has_loopback_capture_device,
    ensure_dsp_prerequisites as _ensure_dsp_prerequisites,
    load_presets,
    save_presets,
)


def _detect_alsa_cards() -> tuple[str | None, str | None]:
    """① 共通: aplay -l を解析して (usb_card, pch_card) のカード番号を返す。"""
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


def _get_available_devices() -> list[dict]:
    """① 共通: 利用可能なオーディオデバイス一覧を返す。"""
    usb_card, pch_card = _detect_alsa_cards()
    devices = []
    if usb_card:
        devices.append({"id": f"plughw:{usb_card},0", "name": f"USB DAC (hw:{usb_card},0)"})
    if pch_card:
        devices.append({"id": f"plughw:{pch_card},0", "name": f"PC Speaker (hw:{pch_card},0)"})
    devices.append({"id": "plug:bluealsa", "name": "Bluetooth (A2DP)"})
    return devices if devices else [{"id": "plughw:1,0", "name": "PC Speaker (hw:1,0)"}]


def _get_first_valid_device(exclude_bluetooth: bool = True) -> str:
    """Get the first available non-bluetooth device, or first bluetooth if none found"""
    devices = _get_available_devices()
    for dev in devices:
        if exclude_bluetooth and "bluealsa" in dev["id"]:
            continue
        if dev["id"] != "none" and dev["id"] != "error":
            return dev["id"]
    for dev in devices:
        if dev["id"] != "none" and dev["id"] != "error":
            return dev["id"]
    return "plughw:1,0"


def _restore_last_config():
    """起動時に前回の設定を復元してスクリプト経由で適用。デバイスが無効な場合は自動検出。"""
    try:
        if not os.path.exists(LAST_CONFIG_PATH):
            return
        d = _load_last_config()
        cfg = AudioConfig(**d)
        cfg = _normalize_config_for_device(cfg, requested_mode=d.get("mode"))
        
        # デバイスが無効または空の場合、利用可能なデバイスを自動検出
        if not cfg.device or cfg.device == "none" or cfg.device == "error":
            cfg.device = _get_first_valid_device(exclude_bluetooth=True)
        
        if cfg.mode == "dsp":
            yp = generate_camilladsp_yaml(cfg)
            subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, "dsp", cfg.device, yp])
            _schedule_init_vol(cfg.volume)
        else:
            subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, "pure", cfg.device, "none"])
    except Exception as e:
        try:
            with open("/tmp/hq_api_apply.log", "a") as lof:
                lof.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] _restore_last_config failed: {e}\n")
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_playback_watchdog())
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _restore_last_config)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket 接続マネージャー
# ─────────────────────────────────────────────────────────────────────────────
class WSManager:
    def __init__(self):
        self.clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.remove(ws)


ws_manager = WSManager()


class AudioConfig(BaseModel):
    mode: str
    device: str
    volume: float
    music_type: str
    eq_output: str
    crossfeed: str
    crossfeed_intensity: int = 5
    hum_noise: str
    reverb: str
    reverb_intensity: int = 5


class VolumeControl(BaseModel):
    volume: float


class StoredAudioConfig(AudioConfig):
    pass


MUSIC_EQ = {
    "none": [],
    "jazz": [{"freq": 80, "q": 0.9, "gain": 2.5}, {"freq": 300, "q": 1.0, "gain": 1.0}, {"freq": 7000, "q": 0.8, "gain": 0.7}],
    "classical": [{"freq": 60, "q": 0.7, "gain": 1.0}, {"freq": 400, "q": 0.9, "gain": -0.5}, {"freq": 8000, "q": 0.8, "gain": 1.0}],
    "electronic": [{"freq": 50, "q": 0.8, "gain": 4.0}, {"freq": 400, "q": 1.2, "gain": -2.0}, {"freq": 10000, "q": 0.9, "gain": 2.5}],
    "vocal": [{"freq": 150, "q": 1.0, "gain": -1.0}, {"freq": 1000, "q": 0.8, "gain": 3.0}, {"freq": 3000, "q": 0.9, "gain": 2.0}],
}

OUTPUT_EQ = {
    "none": [],
    "studio-monitors": [{"freq": 80, "q": 0.8, "gain": 3.0}, {"freq": 2500, "q": 1.0, "gain": -0.8}, {"freq": 20000, "q": 1.0, "gain": 3.0}],
    "JBL-Speakers": [{"freq": 70, "q": 0.7, "gain": 3.0}, {"freq": 1200, "q": 1.0, "gain": -2.0}, {"freq": 13000, "q": 0.8, "gain": 5.0}],
    "planar-magnetic": [{"freq": 30, "q": 0.7, "gain": 1.0}, {"freq": 180, "q": 0.9, "gain": -1.0}, {"freq": 15000, "q": 0.8, "gain": 1.0}],
    "loud-speaker": [{"freq": 70, "q": 0.7, "gain": 4.0}, {"freq": 300, "q": 1.0, "gain": 1.0}, {"freq": 8000, "q": 0.7, "gain": 4.0}, {"freq": 16000, "q": 0.9, "gain": 2.5}],
    "Tube-Warmth": [{"freq": 200, "q": 0.8, "gain": 2.5}, {"freq": 4000, "q": 1.0, "gain": -1.5}, {"freq": 10000, "q": 0.8, "gain": -2.0}],
    "Crystal-Clarity": [{"freq": 100, "q": 1.2, "gain": -2.0}, {"freq": 8000, "q": 0.7, "gain": 4.0}, {"freq": 16000, "q": 0.9, "gain": 2.5}],
}


# ─────────────────────────────────────────────────────────────────────────────
# デバイス一覧
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/devices")
def get_devices():
    devices = []
    try:
        usb_card, pch_card = _detect_alsa_cards()  # ① 共通関数を使用

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


# ─────────────────────────────────────────────────────────────────────────────
# CamillaDSP YAML 生成（backend.dsp.yaml_generator に移植済み）
# ─────────────────────────────────────────────────────────────────────────────
from backend.dsp.yaml_generator import generate_camilladsp_yaml


# ─────────────────────────────────────────────────────────────────────────────
# ボリューム
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/volume")
def set_volume(vol: VolumeControl):
    try:
        c = CamillaClient("127.0.0.1", 1234)
        c.connect()
        c.volume.set_main_volume(vol.volume)
        c.disconnect()
        _update_last_config({"volume": vol.volume})
        return {"status": "success"}
    except Exception as e:
        # Surface errors as HTTP 422 so frontend sees non-OK responses
        raise HTTPException(status_code=422, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# DSP 適用ロジック（backend.dsp.apply_logic に移植済み）
# ─────────────────────────────────────────────────────────────────────────────
from backend.dsp.apply_logic import (
    init_vol as _init_vol,
    schedule_init_vol as _schedule_init_vol,
    SWITCH_AUDIO_SCRIPT,
    restart_dsp as _restart_dsp_impl,
    apply_audio as _apply_audio_impl,
)

# ---- CamillaDSP Health Check & Restart API ----
@app.get("/api/dsp_status")
def get_dsp_status():
    """Check if CamillaDSP is running on port 1234."""
    try:
        c = CamillaClient("127.0.0.1", 1234)
        c.connect()
        version_info = c.cdsp_version
        st = c.general.state()
        c.disconnect()
        return {"status": "running", "version": version_info, "state": st}
    except Exception as e:
        return {"status": "stopped", "error": str(e)}


@app.post("/api/dsp_restart")
def restart_dsp(cfg: AudioConfig):
    """Force restart CamillaDSP with current config."""
    return _restart_dsp_impl(
        cfg,
        generate_camilladsp_yaml,
        _normalize_config_for_device,
        _ensure_dsp_prerequisites,
        _save_last_config,
    )


# 設定適用
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/config", response_model=StoredAudioConfig)
def get_audio_config():
    return StoredAudioConfig(**_load_last_config())


@app.post("/api/apply")
def apply_audio(config: AudioConfig, bt: BackgroundTasks):
    """DSP 設定適用エンドポイント（backend.dsp.apply_logic に委譲）."""
    from backend.dsp.apply_logic import apply_audio as _apply_audio_impl
    return _apply_audio_impl(
        config,
        generate_camilladsp_yaml,
        _normalize_config_for_device,
        _ensure_dsp_prerequisites,
        _config_requires_restart,
        _load_last_config,
        _save_last_config,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Now Playing
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/now_playing")
async def get_now_playing():
    try:
        # Phase 2 修正: async 版 mpd_* を直接 await
        st = await mpd_status()
        so = await mpd_currentsong()
        return format_now_playing(st, so)
    except Exception:
        return JSONResponse(status_code=503, content={"error": "MPD offline"})


# ─────────────────────────────────────────────────────────────────────────────
# DSP プリセット API
# ─────────────────────────────────────────────────────────────────────────────
class PresetSave(BaseModel):
    name: str
    config: dict


@app.get("/api/presets")
def get_presets():
    return load_presets()


@app.post("/api/presets/save")
def save_preset(body: PresetSave):
    if not body.name.strip():
        return {"status": "error", "message": "名前を入力してください"}
    presets = load_presets()
    presets[body.name.strip()] = body.config
    save_presets(presets)
    return {"status": "success", "presets": presets}


@app.delete("/api/presets/{name}")
def delete_preset(name: str):
    presets = load_presets()
    if name in presets:
        del presets[name]
        save_presets(presets)
    return {"status": "success", "presets": presets}


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket — MPD Now Playing（イベント駆動型・ポーリング廃止）
# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: _mpd_current_data は廃止。WebSocket は直接 async で
# mpd_connection を使う（_run_sync を経由しない）ため、
# 同期版の整形関数は不要になった。


@app.websocket("/ws/now_playing")
async def ws_now_playing(ws: WebSocket):
    """Now Playing WebSocket.

    Phase 2 修正: idle の async generator 取り扱いの複雑さを避けるため、
    シンプルな polling（2 秒ごと）に戻した。MPD 接続モデル自体は
    プロセス全体で 1 本の共有接続なので、ポーリングコストは小さい。
    """
    from hqmplayer_core.mpd import mpd_connection as _mpd_conn

    await ws_manager.connect(ws)

    # 前回送信した song_id を保持し、変更があったときだけ push する
    last_song_id: Optional[str] = None
    last_state: Optional[str] = None

    try:
        while True:
            try:
                async with _mpd_conn() as c:
                    st = await c.status()
                    so = await c.currentsong()
            except Exception:
                await asyncio.sleep(2)
                continue

            data = format_now_playing(st, so)
            song_id = data.get("song_id", "")
            state = data.get("state", "")

            # 曲 ID か state が変わったときだけ push（不要な push を抑制）
            if song_id != last_song_id or state != last_state:
                await ws.send_json(data)
                last_song_id = song_id
                last_state = state

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception:
        try:
            ws_manager.disconnect(ws)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# アルバムアート
# ─────────────────────────────────────────────────────────────────────────────
import urllib.parse


# Phase 1d: 共通モジュールの _check_local_art を使う（重複を削除）
from hqmplayer_core.art import _check_local_art


@app.get("/api/art")
async def get_art(file: str, artist: str, album: str):
    # Phase 1d: アート解決戦略を共通モジュールに集約。
    # Phase 2 修正: async 化された resolve_art を await。
    result = await resolve_art(
        file=file,
        artist=artist,
        album=album,
        mpd_readpicture=mpd_readpicture,
        mpd_albumart=mpd_albumart,
        http_get=requests.get,
    )

    if result.source == "itunes" and result.redirect_url:
        return RedirectResponse(result.redirect_url)

    return Response(content=result.content, media_type=result.media_type)