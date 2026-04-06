from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, RedirectResponse
from pydantic import BaseModel
from mpd import MPDClient
from camilladsp import CamillaClient
import subprocess, requests, yaml, os, re, time, wave, array, socket, json, asyncio
from urllib.parse import urlparse, parse_qs

MPD_HOST = os.getenv("MPD_HOST", "127.0.0.1")
try:
    MPD_PORT = int(os.getenv("MPD_PORT", "6600"))
except ValueError:
    MPD_PORT = 6600

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

app = FastAPI()
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

MUSIC_EQ = {
    "none": [],
    "jazz":       [{"freq": 80,   "q": 0.9, "gain": 2.5},
                   {"freq": 300,  "q": 1.0, "gain": 1.0},
                   {"freq": 7000, "q": 0.8, "gain": 0.7}],
    "classical":  [{"freq": 60,   "q": 0.7, "gain": 1.0},
                   {"freq": 400,  "q": 0.9, "gain": -0.5},
                   {"freq": 8000, "q": 0.8, "gain": 1.0}],
    "electronic": [{"freq": 50,   "q": 0.8, "gain": 4.0},
                   {"freq": 400,  "q": 1.2, "gain": -2.0},
                   {"freq": 10000,"q": 0.9, "gain": 2.5}],
    "vocal":      [{"freq": 150,  "q": 1.0, "gain": -1.0},
                   {"freq": 1000, "q": 0.8, "gain": 3.0},
                   {"freq": 3000, "q": 0.9, "gain": 2.0}],
}

OUTPUT_EQ = {
    "none": [],
    "studio-monitors": [{"freq": 80,    "q": 0.8, "gain": 3.0},
                        {"freq": 2500,  "q": 1.0, "gain": -0.8},
                        {"freq": 20000, "q": 1.0, "gain": 3.0}],
    "JBL-Speakers":    [{"freq": 70,    "q": 0.7, "gain": 3.0},
                        {"freq": 1200,  "q": 1.0, "gain": -2.0},
                        {"freq": 13000, "q": 0.8, "gain": 5.0}],
    "planar-magnetic": [{"freq": 30,    "q": 0.7, "gain": 1.0},
                        {"freq": 180,   "q": 0.9, "gain": -1.0},
                        {"freq": 15000, "q": 0.8, "gain": 1.0}],
    "loud-speaker":   [{"freq": 70,    "q": 0.7, "gain": 4.0},
                        {"freq": 300,   "q": 1.0, "gain": 1.0},
                        {"freq": 8000,  "q": 0.7, "gain": 4.0},
                        {"freq": 16000, "q": 0.9, "gain": 2.5}],
    "Tube-Warmth":     [{"freq": 200,   "q": 0.8, "gain": 2.5},
                        {"freq": 4000,  "q": 1.0, "gain": -1.5},
                        {"freq": 10000, "q": 0.8, "gain": -2.0}],
    "Crystal-Clarity": [{"freq": 100,   "q": 1.2, "gain": -2.0},
                        {"freq": 8000,  "q": 0.7, "gain": 4.0},
                        {"freq": 16000, "q": 0.9, "gain": 2.5}],
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
                # Prefer non-HDMI HDA/PCH devices for PC speaker output.
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
    is_bt  = "bluealsa" in config.device
    is_usb = "hw:2" in config.device

    samplerate = 48000 if is_usb else (96000 if is_bt else 192000)
    pb_format  = "S16_LE" if is_usb else "S32_LE"
    cap_format = "S32_LE"

    pb_device = config.device.replace("hw:", "plughw:") if config.device.startswith("hw:") else config.device

    filt = {"type": "Filter", "channels": [0, 1], "names": []}
    devices_block = {
        "samplerate": samplerate, "chunksize": 16384 if is_bt else 4096, "enable_rate_adjust": True,
        "capture":  {"type": "Alsa", "channels": 2, "device": "hw:Loopback,1,0", "format": cap_format},
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
        f = 50 if config.hum_noise == "50hz" else 60
        add_f("hum", {"type": "Biquad", "parameters": {"type": "Notch", "freq": f, "q": 30.0}})

    if config.reverb != "none" and config.reverb_intensity > 0:
        src_ir  = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        ir_path = f"/tmp/camilladsp/ir/{config.reverb}.wav"
        os.makedirs("/tmp/camilladsp/ir", exist_ok=True)
        scale = config.reverb_intensity / 100.0
        try:
            with wave.open(src_ir, "rb") as w:
                params = w.getparams(); raw = w.readframes(w.getnframes())
            samples = array.array("h", raw)
            scaled  = array.array("h", [max(-32768, min(32767, int(s * scale))) for s in samples])
            with wave.open(ir_path, "wb") as w:
                w.setparams(params); w.writeframes(scaled.tobytes())
            add_f("rev", {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path}})
        except Exception:
            pass

    if config.crossfeed != "none":
        cf_gain_direct = -3.5; cf_gain_cross = -9.5
        if config.crossfeed == "light":
            cf_gain_cross = -14.0; cf_gain_direct = -1.5
        if "mixers" not in y: y["mixers"] = {}
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
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _init_vol(v: float):
    """CamillaDSP 起動直後にボリュームを設定（バックグラウンドタスク）"""
    for _ in range(20):
        time.sleep(0.1)
        try:
            c = CamillaClient("127.0.0.1", 1234)
            c.connect()
            c.volume.set_main_volume(v)
            c.disconnect()
            return
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# 設定適用
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/apply")
def apply_audio(config: AudioConfig, bt: BackgroundTasks):
    s = os.path.abspath("./scripts/switch_audio.sh")
    try:
        if config.mode == "dsp":
            yp = generate_camilladsp_yaml(config)
            subprocess.Popen(["bash", s, config.mode, config.device, yp])
            bt.add_task(_init_vol, config.volume)
        else:
            subprocess.Popen(["bash", s, config.mode, config.device, "none"])
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
        title    = so.get("title",  "Unknown")
        artist   = so.get("artist", "Unknown").split(";")[0].split(",")[0].strip()
        album    = so.get("album",  "Unknown")

        # ストリーム URL のクエリパラメータからメタデータを補完
        if "http" in file_url and (title == "Unknown" or artist == "Unknown"):
            q = parse_qs(urlparse(file_url).query)
            if "title"       in q: title  = q["title"][0]
            if "artist"      in q: artist = q["artist"][0]
            elif "albumartist" in q: artist = q["albumartist"][0]
            if "album"       in q: album  = q["album"][0]

        return {
            "song_id":  st.get("songid", ""),
            "title":    title,
            "artist":   artist,
            "album":    album,
            "file":     file_url,
            "state":    st.get("state", "stop"),
            "audio":    st.get("audio", ""),
            "elapsed":  float(st.get("elapsed", 0) or 0),
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
        title    = so.get("title",  "Unknown")
        artist   = so.get("artist", "Unknown").split(";")[0].split(",")[0].strip()
        album    = so.get("album",  "Unknown")

        if "http" in file_url and (title == "Unknown" or artist == "Unknown"):
            q = parse_qs(urlparse(file_url).query)
            if "title"         in q: title  = q["title"][0]
            if "artist"        in q: artist = q["artist"][0]
            elif "albumartist" in q: artist = q["albumartist"][0]
            if "album"         in q: album  = q["album"][0]

        return {
            "song_id":  st.get("songid", ""),
            "title":    title,
            "artist":   artist,
            "album":    album,
            "file":     file_url,
            "state":    st.get("state", "stop"),
            "audio":    st.get("audio", ""),
            "elapsed":  float(st.get("elapsed", 0) or 0),
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
    # 接続直後に現在状態を即送信
    await ws.send_json(_mpd_current_data())

    loop = asyncio.get_event_loop()
    try:
        while True:
            # idle はブロッキング呼び出しなので executor で実行
            def _idle():
                try:
                    c = mpd_connect(timeout=60)
                    # player / mixer イベントを待機（最大60秒）
                    changed = c.idle("player", "mixer")
                    c.disconnect()
                    return changed
                except Exception:
                    return None

            changed = await loop.run_in_executor(None, _idle)
            if changed is None:
                # MPD が落ちている場合は2秒待ってリトライ
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
        p = os.path.join(dirname, name)
        if os.path.exists(p):
            return p
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
                p = getattr(c, method)(file)
                if p and "binary" in p:
                    c.disconnect()
                    return Response(content=p["binary"], media_type="image/jpeg")
            except Exception:
                pass
        c.disconnect()
    except Exception:
        pass

    if artist and album and artist != "Unknown":
        try:
            r = requests.get(
                f"https://itunes.apple.com/search?term={artist}+{album}&entity=album&limit=1",
                timeout=3,
            )
            results = r.json().get("results")
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
