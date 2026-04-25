from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.responses import Response, RedirectResponse
from pydantic import BaseModel
from mpd import MPDClient
from camilladsp import CamillaClient
import subprocess, requests, yaml, os, re, time, wave, array, socket, json, asyncio, threading
from urllib.parse import urlparse, parse_qs

MPD_HOST = os.getenv("MPD_HOST", "127.0.0.1")
try:
    MPD_PORT = int(os.getenv("MPD_PORT", "6600"))
except ValueError:
    MPD_PORT = 6600

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SWITCH_AUDIO_SCRIPT = os.path.join(BASE_DIR, "scripts", "switch_audio.sh")


# ─────────────────────────────────────────────────────────────────────────────
# MPD 接続ヘルパー（リトライ付き・レースコンディション修正版）
# ─────────────────────────────────────────────────────────────────────────────
def mpd_connect(timeout=3, retries=2):
    """
    MPD に接続して MPDClient を返す。
    ソケット事前チェック→close→connectのレースコンディションを廃止し、
    connect() のエラーを直接キャッチしてリトライする。
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
    """永続MPD接続で5秒ごとに状態確認 — 毎秒再接続によるALSA割り込みを排除"""
    loop = asyncio.get_event_loop()
    was_playing = False

    def _make_client() -> MPDClient:
        c = MPDClient()
        c.timeout = 3
        c.connect(MPD_HOST, MPD_PORT)
        return c

    client: MPDClient | None = None

    while True:
        try:
            await asyncio.sleep(5)

            def _poll(c):
                st = c.status()
                return st.get("state", "stop"), c

            if client is None:
                client = await loop.run_in_executor(None, _make_client)

            state, client = await loop.run_in_executor(None, _poll, client)

            if state == "play":
                was_playing = True
            elif state == "stop" and was_playing:
                def _resume(c):
                    c.play()

                await loop.run_in_executor(None, _resume, client)
                was_playing = False
            elif state in ("pause", "stop"):
                was_playing = False

        except Exception:
            try:
                client.disconnect()
            except Exception:
                pass
            client = None
            await asyncio.sleep(5)


LAST_CONFIG_PATH = os.path.expanduser("~/.config/audiophile/last_config.json")
VOLUME_FADE_SECONDS = 0.2
VOLUME_FADE_STEPS = 10
STARTUP_VOLUME_DB = -80.0


def _default_audio_config() -> dict:
    return {
        "mode": "pure",
        "device": "",
        "volume": -5.0,
        "music_type": "none",
        "eq_output": "none",
        "crossfeed": "none",
        "hum_noise": "none",
        "reverb": "none",
        "reverb_intensity": 5,
    }


def _load_last_config() -> dict:
    config = _default_audio_config()
    try:
        if os.path.exists(LAST_CONFIG_PATH):
            with open(LAST_CONFIG_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update(data)
    except Exception:
        pass
    return config


def _save_last_config(config_dict: dict):
    os.makedirs(os.path.dirname(LAST_CONFIG_PATH), exist_ok=True)
    with open(LAST_CONFIG_PATH, "w") as f:
        json.dump(config_dict, f)


def _update_last_config(patch: dict):
    config = _load_last_config()
    config.update(patch)
    _save_last_config(config)


def _config_requires_restart(config: "AudioConfig", last_config: dict | None) -> bool:
    if last_config is None:
        return True
    for key in [
        "mode",
        "device",
        "music_type",
        "eq_output",
        "crossfeed",
        "crossfeed_intensity",
        "hum_noise",
        "reverb",
        "reverb_intensity",
    ]:
        if last_config.get(key) != getattr(config, key):
            return True
    return False


def _normalize_config_for_device(config: "AudioConfig", requested_mode: str | None = None) -> "AudioConfig":
    """Bluetooth を pure で選択した場合は DSP でパススルーし、処理をすべて無効化する。"""
    if "bluealsa" in config.device and requested_mode == "pure":
        return AudioConfig(
            mode="dsp",
            device=config.device,
            volume=config.volume,
            music_type="none",
            eq_output="none",
            crossfeed="none",
            crossfeed_intensity=5,
            hum_noise="none",
            reverb="none",
            reverb_intensity=5,
        )
    if "bluealsa" in config.device:
        config.mode = "dsp"
    return config


def _has_loopback_capture_device() -> bool:
    capture_path = "/proc/asound/Loopback/pcm1c/info"
    return os.path.exists(capture_path)


def _ensure_dsp_prerequisites(config: "AudioConfig"):
    if config.mode != "dsp":
        return
    if not _has_loopback_capture_device():
        raise HTTPException(
            status_code=503,
            detail="ALSA Loopback device is unavailable. Load snd-aloop and retry.",
        )


def _write_ambience_ir(src_ir: str, dest_ir: str, intensity: int):
    with wave.open(src_ir, "rb") as wav_file:
        params = wav_file.getparams()
        raw = wav_file.readframes(wav_file.getnframes())

    if params.sampwidth != 2:
        raise ValueError(f"Unsupported IR sample width: {params.sampwidth * 8}-bit")

    samples = array.array("h", raw)
    wet_scale = max(0.0, min(1.0, intensity / 100.0))
    blended = array.array("h", [0] * len(samples))

    for index, sample in enumerate(samples):
        value = int(sample * wet_scale)
        if index < params.nchannels:
            value += 32767
        blended[index] = max(-32768, min(32767, value))

    with wave.open(dest_ir, "wb") as wav_file:
        wav_file.setparams(params)
        wav_file.writeframes(blended.tobytes())


def _restore_last_config():
    """起動時に前回の設定を復元してスクリプト経由で適用"""
    try:
        if not os.path.exists(LAST_CONFIG_PATH):
            return
        d = _load_last_config()
        cfg = AudioConfig(**d)
        cfg = _normalize_config_for_device(cfg, requested_mode=d.get("mode"))
        if cfg.mode == "dsp":
            yp = generate_camilladsp_yaml(cfg)
            subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, "dsp", cfg.device, yp])
            _schedule_init_vol(cfg.volume, fade_in=True, wait_for_restart=True)
        else:
            subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, "pure", cfg.device or "plughw:AUDIO,0", "none"])
    except Exception:
        pass

    def _has_loopback_capture_device() -> bool:
        return os.path.exists("/proc/asound/Loopback/pcm1c/info")


    def _ensure_dsp_prerequisites(config: "AudioConfig"):
        if config.mode != "dsp":
            return
        if not _has_loopback_capture_device():
            raise HTTPException(
                status_code=503,
                detail="ALSA Loopback device is unavailable. Load snd-aloop and retry.",
            )


    def _write_ambience_ir(src_ir: str, dest_ir: str, intensity: int):
        with wave.open(src_ir, "rb") as wav_file:
            params = wav_file.getparams()
            raw = wav_file.readframes(wav_file.getnframes())

        if params.sampwidth != 2:
            raise ValueError(f"Unsupported IR sample width: {params.sampwidth * 8}-bit")

        samples = array.array("h", raw)
        wet_scale = max(0.0, min(1.0, intensity / 100.0))
        blended = array.array("h", [0] * len(samples))

        for index, sample in enumerate(samples):
            value = int(sample * wet_scale)
            if index < params.nchannels:
                value += 32767
            blended[index] = max(-32768, min(32767, value))

        with wave.open(dest_ir, "wb") as wav_file:
            wav_file.setparams(params)
            wav_file.writeframes(blended.tobytes())



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
# DSP プリセット保存先
# ─────────────────────────────────────────────────────────────────────────────
PRESETS_PATH = os.path.expanduser("~/.config/audiophile/presets.json")


def load_presets() -> dict:
    try:
        with open(PRESETS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_presets(presets: dict):
    os.makedirs(os.path.dirname(PRESETS_PATH), exist_ok=True)
    with open(PRESETS_PATH, "w") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


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
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        res = subprocess.run(["aplay", "-l"], capture_output=True, text=True, env=env)

        usb_card = None
        pch_card = None
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
# CamillaDSP YAML 生成
# ─────────────────────────────────────────────────────────────────────────────
def generate_camilladsp_yaml(config: AudioConfig) -> str:
    is_bt = "bluealsa" in config.device
    is_usb = "USB" in config.device.upper()

    samplerate = 48000 if is_usb else (96000 if is_bt else 192000)
    pb_format = "S16_LE" if (is_usb or is_bt) else "S32_LE"
    cap_format = "S32_LE"

    pb_device = config.device.replace("hw:", "plughw:") if config.device.startswith("hw:") else config.device

    filt = {"type": "Filter", "channels": [0, 1], "names": []}
    devices_block = {
        "samplerate": samplerate,
        "chunksize": 4096,
        "enable_rate_adjust": True,
        "capture": {"type": "Alsa", "channels": 2, "device": "hw:Loopback,1,0", "format": cap_format},
        "playback": {"type": "Alsa", "channels": 2, "device": pb_device, "format": pb_format},
    }
    if samplerate != 192000:
        devices_block["capture_samplerate"] = 192000
        devices_block["resampler"] = {"type": "AsyncPoly", "interpolation": "Cubic"}
    else:
        devices_block["resampler"] = {"type": "Synchronous"}

    y = {"devices": devices_block, "filters": {}, "pipeline": [filt]}

    def add_f(n, d):
        y["filters"][n] = d
        filt["names"].append(n)

    if config.hum_noise in ["50hz", "60hz"] and config.hum_noise != "none":
        add_f("rumble_cut", {"type": "Biquad", "parameters": {"type": "HighpassFO", "freq": 15}})
        freq = 50 if config.hum_noise == "50hz" else 60
        add_f("hum", {"type": "Biquad", "parameters": {"type": "Notch", "freq": freq, "q": 30.0}})

    if config.reverb != "none" and config.reverb_intensity > 0:
        src_ir = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        ir_path = f"/tmp/camilladsp/ir/{config.reverb}.wav"
        os.makedirs("/tmp/camilladsp/ir", exist_ok=True)
        try:
            if not os.path.exists(src_ir):
                raise FileNotFoundError(f"IR source missing: {src_ir}")
            _write_ambience_ir(src_ir, ir_path, config.reverb_intensity)
            add_f("rev", {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path}})
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            try:
                with open("/tmp/hq_api_apply.log", "a") as lof:
                    lof.write(f"Failed to process IR {config.reverb}: {str(e)}\n")
                    lof.write(tb + "\n")
            except Exception:
                pass
            raise

    if config.crossfeed != "none":
        cf_gain_direct = -3.5
        cf_gain_cross = -9.5
        if config.crossfeed == "light":
            cf_gain_cross = -14.0
            cf_gain_direct = -1.5
        if "mixers" not in y:
            y["mixers"] = {}
        y["mixers"]["cf"] = {
            "channels": {"in": 2, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": cf_gain_direct, "inverted": False}, {"channel": 1, "gain": cf_gain_cross, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": cf_gain_direct, "inverted": False}, {"channel": 0, "gain": cf_gain_cross, "inverted": False}]},
            ],
        }
        y["pipeline"].insert(0, {"type": "Mixer", "name": "cf"})

    for i, eq in enumerate(MUSIC_EQ.get(config.music_type, [])):
        add_f(f"m_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})
    for i, eq in enumerate(OUTPUT_EQ.get(config.eq_output, [])):
        add_f(f"o_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})

    if config.music_type != "none" or config.eq_output != "none" or config.reverb != "none":
        add_f("headroom", {"type": "Gain", "parameters": {"gain": -4.0, "inverted": False, "mute": False}})

    y["pipeline"] = [p for p in y["pipeline"] if not (p.get("type") == "Filter" and len(p.get("names", [])) == 0)]
    if not y["pipeline"]:
        y["filters"]["dummy"] = {"type": "Gain", "parameters": {"gain": 0.0, "inverted": False, "mute": False}}
        y["pipeline"] = [{"type": "Filter", "channels": [0, 1], "names": ["dummy"]}]

    os.makedirs("/tmp/camilladsp", exist_ok=True)
    with open("/tmp/camilladsp/active_dsp.yml", "w") as f:
        yaml.dump(y, f, sort_keys=False)
    return "/tmp/camilladsp/active_dsp.yml"


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


def _init_vol(v: float, fade_in: bool = False, wait_for_restart: bool = False):
    restart_observed = not wait_for_restart
    for _ in range(200):
        time.sleep(0.05)
        try:
            c = CamillaClient("127.0.0.1", 1234)
            c.connect()
            if not restart_observed:
                c.disconnect()
                continue

            if fade_in:
                start_volume = min(v, STARTUP_VOLUME_DB)
                c.volume.set_main_mute(True)
                c.volume.set_main_volume(start_volume)
                c.volume.set_main_mute(False)
                if start_volume != v:
                    step_sleep = VOLUME_FADE_SECONDS / VOLUME_FADE_STEPS
                    for step in range(1, VOLUME_FADE_STEPS + 1):
                        level = start_volume + ((v - start_volume) * step / VOLUME_FADE_STEPS)
                        c.volume.set_main_volume(level)
                        time.sleep(step_sleep)
                else:
                    c.volume.set_main_volume(v)
            else:
                c.volume.set_main_volume(v)

            c.disconnect()
            return
        except Exception:
            if wait_for_restart:
                restart_observed = True


def _schedule_init_vol(v: float, fade_in: bool = False, wait_for_restart: bool = False):
    thread = threading.Thread(target=_init_vol, args=(v, fade_in, wait_for_restart), daemon=True)
    thread.start()


# ─────────────────────────────────────────────────────────────────────────────
# 設定適用
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/config", response_model=StoredAudioConfig)
def get_audio_config():
    return StoredAudioConfig(**_load_last_config())


@app.post("/api/apply")
def apply_audio(config: AudioConfig, bt: BackgroundTasks):
    requested_mode = config.mode
    if os.path.exists(LAST_CONFIG_PATH):
        try:
            last_config = _load_last_config()
        except Exception:
            last_config = None
    else:
        last_config = None

    config = _normalize_config_for_device(config, requested_mode=requested_mode)
    _ensure_dsp_prerequisites(config)
    needs_restart = _config_requires_restart(config, last_config)
    try:
        if config.mode == "dsp":
            saved_volume = float(last_config.get("volume", config.volume)) if last_config else config.volume
            config = AudioConfig(**{**config.model_dump(), "volume": saved_volume})
            if needs_restart:
                yp = generate_camilladsp_yaml(config)
                subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, config.mode, config.device, yp])
                _schedule_init_vol(config.volume, fade_in=True, wait_for_restart=True)
            else:
                _schedule_init_vol(config.volume)
        else:
            if needs_restart:
                subprocess.Popen(["bash", SWITCH_AUDIO_SCRIPT, config.mode, config.device, "none"])
        _save_last_config(config.model_dump())
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Now Playing
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/now_playing")
def get_now_playing():
    try:
        c = mpd_connect()
        st = c.status()
        so = c.currentsong()
        c.disconnect()

        file_url = so.get("file", "")
        title = so.get("title", "Unknown")
        artist = so.get("artist", "Unknown").split(";")[0].split(",")[0].strip()
        album = so.get("album", "Unknown")

        if "http" in file_url and (title == "Unknown" or artist == "Unknown"):
            q = parse_qs(urlparse(file_url).query)
            if "title" in q:
                title = q["title"][0]
            if "artist" in q:
                artist = q["artist"][0]
            elif "albumartist" in q:
                artist = q["albumartist"][0]
            if "album" in q:
                album = q["album"][0]

        return {
            "song_id": st.get("songid", ""),
            "title": title,
            "artist": artist,
            "album": album,
            "file": file_url,
            "state": st.get("state", "stop"),
            "audio": st.get("audio", ""),
            "elapsed": float(st.get("elapsed", 0) or 0),
            "duration": float(st.get("duration", 0) or 0),
        }
    except Exception:
        return {"error": "MPD offline"}


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
def _mpd_current_data() -> dict:
    """MPD から現在の再生情報を取得して返す（同期）"""
    try:
        c = mpd_connect(timeout=5)
        st = c.status()
        so = c.currentsong()
        c.disconnect()

        file_url = so.get("file", "")
        title = so.get("title", "Unknown")
        artist = so.get("artist", "Unknown").split(";")[0].split(",")[0].strip()
        album = so.get("album", "Unknown")

        if "http" in file_url and (title == "Unknown" or artist == "Unknown"):
            q = parse_qs(urlparse(file_url).query)
            if "title" in q:
                title = q["title"][0]
            if "artist" in q:
                artist = q["artist"][0]
            elif "albumartist" in q:
                artist = q["albumartist"][0]
            if "album" in q:
                album = q["album"][0]

        return {
            "song_id": st.get("songid", ""),
            "title": title,
            "artist": artist,
            "album": album,
            "file": file_url,
            "state": st.get("state", "stop"),
            "audio": st.get("audio", ""),
            "elapsed": float(st.get("elapsed", 0) or 0),
            "duration": float(st.get("duration", 0) or 0),
        }
    except Exception:
        return {"error": "MPD offline"}


@app.websocket("/ws/now_playing")
async def ws_now_playing(ws: WebSocket):
    """
    MPD の idle コマンドを使ったイベント駆動型 Now Playing ストリーム。
    曲・状態が変化した瞬間にだけクライアントへ push する。
    ポーリングを完全に廃止するため MPD への接続負荷が大幅に減少する。
    """
    await ws_manager.connect(ws)
    await ws.send_json(_mpd_current_data())

    loop = asyncio.get_event_loop()
    try:
        while True:
            def _idle():
                try:
                    c = mpd_connect(timeout=60)
                    changed = c.idle("player", "mixer")
                    c.disconnect()
                    return changed
                except Exception:
                    return None

            changed = await loop.run_in_executor(None, _idle)
            if changed is None:
                await asyncio.sleep(2)
                continue

            data = await loop.run_in_executor(None, _mpd_current_data)
            await ws.send_json(data)

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


def _check_local_art(filepath: str):
    if filepath.startswith("http"):
        try:
            filepath = urllib.parse.unquote(urlparse(filepath).path)
        except Exception:
            pass
    dirname = os.path.dirname(filepath) if os.path.exists(filepath) else filepath
    for name in ("Folder.jpg", "folder.jpg", "cover.jpg", "Cover.jpg"):
        path = os.path.join(dirname, name)
        if os.path.exists(path):
            return path
    return None


@app.get("/api/art")
def get_art(file: str, artist: str, album: str):
    local = _check_local_art(file)
    if local:
        try:
            with open(local, "rb") as f:
                return Response(content=f.read(), media_type="image/jpeg")
        except Exception:
            pass

    try:
        c = mpd_connect()
        for method in ("readpicture", "albumart"):
            try:
                picture = getattr(c, method)(file)
                if picture and "binary" in picture:
                    c.disconnect()
                    return Response(content=picture["binary"], media_type="image/jpeg")
            except Exception:
                pass
        c.disconnect()
    except Exception:
        pass

    if artist and album and artist != "Unknown":
        try:
            response = requests.get(
                f"https://itunes.apple.com/search?term={artist}+{album}&entity=album&limit=1",
                timeout=3,
            )
            results = response.json().get("results")
            if results:
                url = results[0].get("artworkUrl100", "").replace("100x100", "600x600")
                if url:
                    return RedirectResponse(url)
        except Exception:
            pass

    return Response(
        content=(
            '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">'
            '<rect width="300" height="300" fill="#1f2937"/>'
            '<text x="50%" y="50%" fill="#4b5563" font-size="16" '
            'font-family="sans-serif" text-anchor="middle" dy=".3em">No Artwork</text>'
            "</svg>"
        ),
        media_type="image/svg+xml",
    )