from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.responses import Response, RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import Request
from pydantic import BaseModel
from mpd import MPDClient
from camilladsp import CamillaClient
import subprocess, requests, yaml, os, re, time, wave, array, socket, json, asyncio, threading, struct, math
from urllib.parse import urlparse, parse_qs, quote_plus

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SWITCH_AUDIO_SCRIPT = os.path.join(BASE_DIR, "scripts", "switch_audio.sh")


def _load_local_env_defaults():
    env_defaults = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return env_defaults
    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env_defaults[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return env_defaults
    return env_defaults


_LOCAL_ENV_DEFAULTS = _load_local_env_defaults()
MPD_HOST = os.getenv("MPD_HOST", _LOCAL_ENV_DEFAULTS.get("MPD_HOST", "127.0.0.1"))
try:
    MPD_PORT = int(os.getenv("MPD_PORT", _LOCAL_ENV_DEFAULTS.get("MPD_PORT", "6601")))
except ValueError:
    MPD_PORT = 6601


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
    # Only compare keys that exist on AudioConfig and are sent by the frontend
    for key in [
        "mode",
        "device",
        "music_type",
        "eq_output",
        "crossfeed",
        "hum_noise",
        "reverb",
        "reverb_intensity",
        "volume",
    ]:
        try:
            if last_config.get(key) != getattr(config, key):
                return True
        except AttributeError:
            # If the config object doesn't have the attribute, skip comparison
            continue
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the raw body to help diagnose 422 JSON decode errors from the GUI
    try:
        body = await request.body()
        print(f"[VALIDATION_ERROR] path={request.url.path} error={exc} body={body.decode(errors='replace')}")
    except Exception:
        print(f"[VALIDATION_ERROR] path={request.url.path} error={exc} (failed to read body)")
    return JSONResponse(status_code=422, content={"detail": str(exc)})


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
    post_filt = {"type": "Filter", "channels": [0, 1], "names": []}
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

    def add_post_f(n, d):
        y["filters"][n] = d
        post_filt["names"].append(n)

    if config.hum_noise in ["50hz", "60hz"] and config.hum_noise != "none":
        add_f("rumble_cut", {"type": "Biquad", "parameters": {"type": "HighpassFO", "freq": 15}})
        freq = 50 if config.hum_noise == "50hz" else 60
        add_f("hum", {"type": "Biquad", "parameters": {"type": "Notch", "freq": freq, "q": 30.0}})

    reverb_enabled = config.reverb != "none" and config.reverb_intensity > 0
    if reverb_enabled:
        src_ir = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        ir_path = f"/tmp/camilladsp/ir/{config.reverb}.wav"
        os.makedirs("/tmp/camilladsp/ir", exist_ok=True)
        scale = config.reverb_intensity / 100.0
        try:
            if not os.path.exists(src_ir):
                raise FileNotFoundError(f"IR source missing: {src_ir}")
            # Read original WAV and scale (prefer `sox` external tool; python fallback used otherwise)

            with wave.open(src_ir, "rb") as w:
                params = w.getparams()
                nframes = w.getnframes()
                raw = w.readframes(nframes)

            def _is_silent_ir(data: bytes, sample_width: int) -> bool:
                if not data:
                    return True
                if sample_width == 1:
                    return all(b == 128 for b in data)
                if sample_width == 2:
                    vals = struct.unpack("<" + "h" * (len(data) // 2), data)
                    return max((abs(v) for v in vals), default=0) <= 1
                return not any(data)

            def _write_synthetic_ir(path: str, rate: int, preset: str, wet: float) -> None:
                # Lightweight fallback IR so ambience never collapses to silence.
                # Keep energy intentionally low; CamillaDSP convolves the whole signal,
                # so a strong synthetic IR can sound like clipping or a huge volume jump.
                wet = max(0.05, min(1.0, wet))
                length_s = 1.6 if preset == "hall" else 0.75
                frame_count = max(1, int(rate * length_s))
                samples = [0.0] * frame_count

                if preset == "hall":
                    tap_times = [0.024, 0.041, 0.067, 0.093, 0.131, 0.179, 0.251, 0.347, 0.463, 0.611]
                    base_gain = 0.060 * wet
                else:
                    tap_times = [0.012, 0.021, 0.034, 0.049, 0.072, 0.101, 0.146, 0.214]
                    base_gain = 0.045 * wet

                for tap_index, delay_s in enumerate(tap_times):
                    start = int(delay_s * rate)
                    if start >= frame_count:
                        break
                    amplitude = base_gain * (0.74 ** tap_index)
                    samples[start] += amplitude if tap_index % 2 == 0 else -amplitude

                peak = max((abs(v) for v in samples), default=1.0) or 1.0
                norm = min(1.0, 0.16 / peak)
                pcm = bytearray()
                for sample in samples:
                    value = int(max(-32768, min(32767, round(sample * norm * 32767))))
                    pcm.extend(struct.pack("<h", value))
                with wave.open(path, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(rate)
                    w.writeframes(bytes(pcm))

            if _is_silent_ir(raw, params.sampwidth):
                _write_synthetic_ir(ir_path, samplerate, config.reverb, scale)
                y["filters"]["rev"] = {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path}}
            else:
                # Prefer to resample+scale with `sox` if available (keeps sample-rate/channel handling robust).
                try:
                    import shutil

                    sox_path = shutil.which("sox")
                    if sox_path:
                        cmd = [sox_path, src_ir, "-r", str(samplerate), ir_path, "vol", str(scale)]
                        try:
                            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            scaled_raw = None
                        except Exception:
                            # fall back to python scaler if sox fails
                            scaled_raw = raw
                    else:
                        scaled_raw = raw
                except Exception:
                    scaled_raw = raw

                # If we have scaled_raw bytes (python fallback), write them; otherwise sox already created the file.
                if scaled_raw is not None:
                    try:
                        with wave.open(ir_path, "wb") as w:
                            w.setparams(params)
                            w.writeframes(scaled_raw)
                    except Exception:
                        # best-effort: write raw if writing scaled failed
                        with wave.open(ir_path, "wb") as w:
                            w.setparams(params)
                            w.writeframes(raw)

                y["filters"]["rev"] = {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path}}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            try:
                with open('/tmp/hq_api_apply.log', 'a') as lf:
                    lf.write(f"Failed to process IR {config.reverb}: {str(e)}\n")
                    lf.write(tb + "\n")
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

    if reverb_enabled:
        if "mixers" not in y:
            y["mixers"] = {}
        y["mixers"]["reverb_split"] = {
            "channels": {"in": 2, "out": 4},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": 0.0, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": 0.0, "inverted": False}]},
                {"dest": 2, "sources": [{"channel": 0, "gain": 0.0, "inverted": False}]},
                {"dest": 3, "sources": [{"channel": 1, "gain": 0.0, "inverted": False}]},
            ],
        }
        y["mixers"]["reverb_sum"] = {
            "channels": {"in": 4, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": 0.0, "inverted": False}, {"channel": 2, "gain": -6.0, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": 0.0, "inverted": False}, {"channel": 3, "gain": -6.0, "inverted": False}]},
            ],
        }
        y["pipeline"].append({"type": "Mixer", "name": "reverb_split"})
        y["pipeline"].append({"type": "Filter", "channels": [2, 3], "names": ["rev"]})
        y["pipeline"].append({"type": "Mixer", "name": "reverb_sum"})

    if config.music_type != "none" or config.eq_output != "none" or config.reverb != "none":
        add_post_f("headroom", {"type": "Gain", "parameters": {"gain": -4.0, "inverted": False, "mute": False}})

    if post_filt["names"]:
        y["pipeline"].append(post_filt)

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
        return {"status": "error", "message": str(e)}


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
async def apply_audio(request: Request, bt: BackgroundTasks):
    # Read raw body for logging to help diagnose GUI-originated JSON issues
    try:
        raw = await request.body()
        raw_text = raw.decode(errors="replace")
    except Exception:
        raw_text = "(failed to read body)"
    # write to a temp logfile for reliable debugging even if journal is noisy
    try:
        with open('/tmp/hq_api_apply.log', 'a') as lf:
            lf.write('\n--- API_APPLY at ' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n')
            lf.write('Raw body:\n')
            lf.write(raw_text + '\n')
    except Exception:
        pass
    print(f"[API_APPLY] Raw body: {raw_text}")

    # Parse JSON and validate
    try:
        data = json.loads(raw_text)
    except Exception as e:
        try:
            with open('/tmp/hq_api_apply.log', 'a') as lf:
                lf.write('JSON parse error: ' + str(e) + '\n')
        except Exception:
            pass
        print(f"[API_APPLY] JSON parse error: {e}")
        return JSONResponse(status_code=422, content={"detail": "JSON parse error", "error": str(e), "body": raw_text})

    try:
        config = AudioConfig(**data)
    except Exception as e:
        try:
            with open('/tmp/hq_api_apply.log', 'a') as lf:
                lf.write('Validation error: ' + str(e) + '\n')
        except Exception:
            pass
        print(f"[API_APPLY] Validation error: {e}")
        return JSONResponse(status_code=422, content={"detail": "Validation error", "error": str(e), "body": raw_text})

    requested_mode = config.mode
    if os.path.exists(LAST_CONFIG_PATH):
        try:
            last_config = _load_last_config()
        except Exception:
            last_config = None
    else:
        last_config = None

    print(f"[API_APPLY] last_config={last_config}")
    config = _normalize_config_for_device(config, requested_mode=requested_mode)
    # compute per-key differences for debugging
    keys_to_check = [
        "mode",
        "device",
        "music_type",
        "eq_output",
        "crossfeed",
        "hum_noise",
        "reverb",
        "reverb_intensity",
        "volume",
    ]
    diffs = {}
    for k in keys_to_check:
        try:
            old = last_config.get(k) if last_config else None
            new = getattr(config, k)
            if old != new:
                diffs[k] = {"old": old, "new": new}
        except Exception:
            pass
    needs_restart = _config_requires_restart(config, last_config)
    print(f"[API_APPLY] diffs={diffs} needs_restart={needs_restart}")
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
        try:
            with open('/tmp/hq_api_apply.log', 'a') as lf:
                lf.write('Apply success. diffs=' + str(diffs) + '\n')
        except Exception:
            pass
        return {"status": "success"}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            with open('/tmp/hq_api_apply.log', 'a') as lf:
                lf.write('Exception while applying:\n')
                lf.write(tb + '\n')
        except Exception:
            pass
        print(f"[API_APPLY] Exception while applying: {e}\n{tb}")
        raise HTTPException(status_code=422, detail=str(e))


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
def get_art(file: str, artist: str, album: str, title: str = ""):
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
                f"https://itunes.apple.com/search?term={quote_plus(f'{artist} {album}')}&entity=album&limit=1",
                timeout=3,
            )
            results = response.json().get("results")
            if results:
                url = results[0].get("artworkUrl100", "").replace("100x100", "600x600")
                if url:
                    return RedirectResponse(url)
        except Exception:
            pass

    if artist and title and artist != "Unknown" and title != "Unknown":
        try:
            response = requests.get(
                f"https://itunes.apple.com/search?term={quote_plus(f'{artist} {title}')}&entity=song&limit=1",
                timeout=3,
            )
            results = response.json().get("results")
            if results:
                url = results[0].get("artworkUrl100", "").replace("100x100", "600x600")
                if url:
                    return RedirectResponse(url)
        except Exception:
            pass

    if album and album != "Unknown":
        try:
            response = requests.get(
                f"https://itunes.apple.com/search?term={quote_plus(album)}&entity=album,song&limit=1",
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