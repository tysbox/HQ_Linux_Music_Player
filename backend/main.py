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
        "crossfeed_intensity": 5,
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


def _extract_alsa_card_number(device_id: str) -> str | None:
    """Extract ALSA card number from device ids like plughw:2,0 / hw:2,0."""
    if not device_id:
        return None
    m = re.search(r"(?:^|:)(?:plughw|hw):(\d+),\d+", device_id, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _ensure_ir_192k(ir_path: str, target_rate: int = 192000) -> None:
    """IR ファイルが target_rate でなければ SoX で変換して上書き保存（初回のみ）。

    - 192kHz 済みなら即リターン（ゼロコスト）
    - SoX があれば自動変換して ir_path に上書き
    - SoX がなければ手動変換コマンドを示して RuntimeError
    """
    try:
        with wave.open(ir_path, "r") as wf:
            rate = wf.getframerate()
    except Exception:
        return  # ヘッダが読めない場合は変換スキップ（CamillaDSP に任せる）

    if rate == target_rate:
        return  # 既に目標レート

    # 変換が必要
    if not shutil.which("sox"):
        raise RuntimeError(
            f"IR ファイル {ir_path} は {rate}Hz です（{target_rate}Hz 必要）。\n"
            f"一度だけ以下を実行してください:\n"
            f"  sox '{ir_path}' -r {target_rate} /tmp/_ir_tmp.wav && mv /tmp/_ir_tmp.wav '{ir_path}'"
        )

    tmp = ir_path + "._converting.wav"
    try:
        subprocess.run(["sox", ir_path, "-r", str(target_rate), tmp],
                       check=True, capture_output=True)
        os.replace(tmp, ir_path)  # アトミックに上書き
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"IR 変換失敗 ({rate}Hz → {target_rate}Hz): {e}")


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
            _schedule_init_vol(cfg.volume, fade_in=True, wait_for_restart=True)
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
# CamillaDSP YAML 生成
# ─────────────────────────────────────────────────────────────────────────────
def generate_camilladsp_yaml(config: AudioConfig) -> str:
    is_bt = "bluealsa" in config.device
    usb_card, _ = _detect_alsa_cards()
    selected_card = _extract_alsa_card_number(config.device)
    is_usb = bool(usb_card and selected_card and selected_card == usb_card)

    samplerate = 192000
    pb_format = "S16_LE" if (is_usb or is_bt) else "S32_LE"
    cap_format = "S32_LE"

    pb_device = config.device.replace("hw:", "plughw:") if config.device.startswith("hw:") else config.device

    devices_block = {
        "samplerate": samplerate,
        "chunksize": 4096,
        "enable_rate_adjust": True,
        "capture": {"type": "Alsa", "channels": 2, "device": "hw:Loopback,1,0", "format": cap_format},
        "playback": {"type": "Alsa", "channels": 2, "device": pb_device, "format": pb_format},
    }
    capture_samplerate = 192000
    if capture_samplerate != samplerate:
        devices_block["capture_samplerate"] = capture_samplerate
        devices_block["resampler"] = {"type": "AsyncPoly", "interpolation": "Cubic"}

    y = {"devices": devices_block, "filters": {}, "pipeline": [], "mixers": {}}

    # Determine if we need parallel DRY/WET paths (reverb enabled)
    has_reverb = config.reverb != "none" and config.reverb_intensity > 0
    
    # ─────────────────────────────────────────────────────────────────────
    # MIXER: Split input to DRY (ch 0-1) and WET (ch 2-3) if reverb enabled
    # ─────────────────────────────────────────────────────────────────────
    if has_reverb:
        y["mixers"]["split"] = {
            "channels": {"in": 2, "out": 4},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": 0.0, "inverted": False}]},  # DRY L: UNCHANGED - preserve signal quality
                {"dest": 1, "sources": [{"channel": 1, "gain": 0.0, "inverted": False}]},  # DRY R: UNCHANGED
                {"dest": 2, "sources": [{"channel": 0, "gain": 0.0, "inverted": False}]},  # WET L input: full level to Conv
                {"dest": 3, "sources": [{"channel": 1, "gain": 0.0, "inverted": False}]},  # WET R input: full level to Conv
            ],
        }
        y["pipeline"].append({"type": "Mixer", "name": "split"})

    # ─────────────────────────────────────────────────────────────────────
    # FILTER: Main DRY path (ch 0-1) or monolithic path (no reverb)
    # ─────────────────────────────────────────────────────────────────────
    filt_dry = {"type": "Filter", "channels": [0, 1] if has_reverb else [0, 1], "names": []}
    
    def add_f_dry(n, d):
        y["filters"][n] = d
        filt_dry["names"].append(n)

    if config.hum_noise in ["50hz", "60hz"] and config.hum_noise != "none":
        add_f_dry("rumble_cut", {"type": "Biquad", "parameters": {"type": "HighpassFO", "freq": 15}})
        freq = 50 if config.hum_noise == "50hz" else 60
        add_f_dry("hum", {"type": "Biquad", "parameters": {"type": "Notch", "freq": freq, "q": 30.0}})

    for i, eq in enumerate(MUSIC_EQ.get(config.music_type, [])):
        add_f_dry(f"m_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})
    for i, eq in enumerate(OUTPUT_EQ.get(config.eq_output, [])):
        add_f_dry(f"o_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})

    # Headroom protection on DRY path - only when NOT using reverb (no parallel processing)
    # When reverb is on, DRY goes through split mixer and headroom is applied AFTER mixing
    if not has_reverb:
        headroom_db = -4.0
        if config.music_type != "none" or config.eq_output != "none":
            add_f_dry("headroom", {"type": "Gain", "parameters": {"gain": headroom_db, "inverted": False, "mute": False}})

    if filt_dry["names"]:
        y["pipeline"].append(filt_dry)

    # ─────────────────────────────────────────────────────────────────────
    # FILTER: WET path (ch 2-3) - Conv + WET gain
    # ─────────────────────────────────────────────────────────────────────
    if has_reverb:
        src_ir = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        try:
            if not os.path.exists(src_ir):
                raise FileNotFoundError(f"IR source missing: {src_ir}")

            # WET path filters: Conv + Gain (on channels 2-3)
            filt_wet = {"type": "Filter", "channels": [2, 3], "names": []}

            def add_f_wet(n, d):
                y["filters"][n] = d
                filt_wet["names"].append(n)

            # IR を 192kHz に変換（既に 192kHz なら即リターン）
            _ensure_ir_192k(src_ir, target_rate=192000)

            # Conv: 192kHz に変換済みの IR を直接参照
            add_f_wet("rev", {"type": "Conv", "parameters": {
                "type": "Wav",
                "filename": src_ir,
            }})
            
            # WET gain: VERY conservative to avoid clipping when mixed with full-level DRY
            # intensity=50 -> -44dB (extremely subtle), intensity=100 -> -32dB (very subtle)
            wet_gain_db = round(-50.0 + (config.reverb_intensity / 100.0) * 18.0, 1)
            add_f_wet("rev_out", {"type": "Gain", "parameters": {"gain": wet_gain_db, "inverted": False, "mute": False}})
            
            y["pipeline"].append(filt_wet)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            try:
                with open("/tmp/hq_api_apply.log", "a") as lof:
                    lof.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Failed to process IR {config.reverb}: {str(e)}\n")
                    lof.write(tb + "\n")
            except Exception:
                pass
            # ④ Fallback: エラー時に split/mix Mixer が残らないよう、
            # pipeline から split Mixer と後続の mix Mixer を除去してから reverb を無効化
            y["pipeline"] = [p for p in y["pipeline"] if not (p.get("type") == "Mixer" and p.get("name") in ("split", "mix"))]
            y["mixers"].pop("split", None)
            y["mixers"].pop("mix", None)
            config.reverb = "none"
            print(f"Ambience error: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # CROSSFEED mixer (before splitting, so applies to all signals)
    # ─────────────────────────────────────────────────────────────────────
    if config.crossfeed != "none":
        intensity = config.crossfeed_intensity
        intensity_pct = max(0.01, min(1.0, intensity / 100.0))
        if config.crossfeed == "light":
            cf_gain_cross = round(-20 + 6 * intensity_pct, 1)
            cf_gain_direct = round(-1.5 * (1 - intensity_pct), 1)
        else:
            cf_gain_cross = round(-20 + 10.5 * intensity_pct, 1)
            cf_gain_direct = round(-3.5 * (1 - intensity_pct), 1)
        
        y["mixers"]["cf"] = {
            "channels": {"in": 2, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": cf_gain_direct, "inverted": False}, {"channel": 1, "gain": cf_gain_cross, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": cf_gain_direct, "inverted": False}, {"channel": 0, "gain": cf_gain_cross, "inverted": False}]},
            ],
        }
        y["pipeline"].insert(0, {"type": "Mixer", "name": "cf"})

    # ─────────────────────────────────────────────────────────────────────
    # MIXER: Recombine DRY (ch 0-1) + WET (ch 2-3) back to output (ch 0-1)
    # ─────────────────────────────────────────────────────────────────────
    if has_reverb:
        y["mixers"]["mix"] = {
            "channels": {"in": 4, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [
                    {"channel": 0, "gain": 0.0, "inverted": False},  # DRY L
                    {"channel": 2, "gain": 0.0, "inverted": False},  # WET L
                ]},
                {"dest": 1, "sources": [
                    {"channel": 1, "gain": 0.0, "inverted": False},  # DRY R
                    {"channel": 3, "gain": 0.0, "inverted": False},  # WET R
                ]},
            ],
        }
        y["pipeline"].append({"type": "Mixer", "name": "mix"})
        
        # Final headroom after mixing DRY + WET to prevent clipping
        y["filters"]["final_headroom"] = {
            "type": "Gain",
            "parameters": {"gain": -3.0, "inverted": False, "mute": False}
        }
        y["pipeline"].append({
            "type": "Filter",
            "channels": [0, 1],
            "names": ["final_headroom"]
        })

    # Remove empty pipelines
    y["pipeline"] = [p for p in y["pipeline"] if not (p.get("type") == "Filter" and len(p.get("names", [])) == 0)]
    
    # Fallback: ensure at least dummy filter
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
    try:
        normalized = _normalize_config_for_device(cfg)
        _ensure_dsp_prerequisites(normalized)
        yp = generate_camilladsp_yaml(normalized)
        result = subprocess.run(
            ["bash", SWITCH_AUDIO_SCRIPT, "dsp", normalized.device, yp],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return JSONResponse(
                status_code=422,
                content={"status": "error", "message": "switch_audio failed", "stdout": result.stdout, "stderr": result.stderr},
            )
        _schedule_init_vol(normalized.volume, fade_in=True, wait_for_restart=True)
        _save_last_config(normalized.model_dump())
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})


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
    
    # デバイスが無効または空の場合、自動的に利用可能なデバイスを選択
    if not config.device or config.device == "none" or config.device == "error":
        config.device = _get_first_valid_device(exclude_bluetooth=True)
    
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
        return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})


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