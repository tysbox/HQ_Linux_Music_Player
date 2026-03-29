from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, RedirectResponse
from pydantic import BaseModel
from mpd import MPDClient
from camilladsp import CamillaClient
import subprocess, requests, yaml, os, re, time, wave, array, socket
from urllib.parse import urlparse, parse_qs

def mpd_connect(timeout=3):
    c = MPDClient()
    c.timeout = timeout
    c.idletimeout = timeout
    # Pre-check with socket timeout so connect() won't hang
    s = socket.create_connection(("localhost", 6600), timeout=timeout)
    s.close()
    c.connect("localhost", 6600)
    return c

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    "jazz": [{"freq": 80, "q": 0.9, "gain": 2.5}, {"freq": 300, "q": 1.0, "gain": 1.0}, {"freq": 7000, "q": 0.8, "gain": 0.7}],
    "classical": [{"freq": 60, "q": 0.7, "gain": 1.0}, {"freq": 400, "q": 0.9, "gain": -0.5}, {"freq": 8000, "q": 0.8, "gain": 1.0}],
    "electronic": [{"freq": 50, "q": 0.8, "gain": 4.0}, {"freq": 400, "q": 1.2, "gain": -2.0}, {"freq": 10000, "q": 0.9, "gain": 2.5}],
    "vocal": [{"freq": 150, "q": 1.0, "gain": -1.0}, {"freq": 1000, "q": 0.8, "gain": 3.0}, {"freq": 3000, "q": 0.9, "gain": 2.0}]
}

OUTPUT_EQ = {
    "none": [],
    "studio-monitors": [{"freq": 80, "q": 0.8, "gain": 3.0}, {"freq": 2500, "q": 1.0, "gain": -0.8}, {"freq": 20000, "q": 1.0, "gain": 3.0}],
    "JBL-Speakers": [{"freq": 70, "q": 0.7, "gain": 3.0}, {"freq": 1200, "q": 1.0, "gain": -2.0}, {"freq": 13000, "q": 0.8, "gain": 5.0}],
    "planar-magnetic": [{"freq": 30, "q": 0.7, "gain": 1.0}, {"freq": 180, "q": 0.9, "gain": -1.0}, {"freq": 15000, "q": 0.8, "gain": 1.0}],
    "bt-earphones": [{"freq": 60, "q": 1.0, "gain": 1.0}, {"freq": 3000, "q": 1.0, "gain": -0.5}, {"freq": 18000, "q": 1.0, "gain": 3.0}],
    "Tube-Warmth": [{"freq": 200, "q": 0.8, "gain": 2.5}, {"freq": 4000, "q": 1.0, "gain": -1.5}, {"freq": 10000, "q": 0.8, "gain": -2.0}],
    "Crystal-Clarity": [{"freq": 100, "q": 1.2, "gain": -2.0}, {"freq": 8000, "q": 0.7, "gain": 4.0}, {"freq": 16000, "q": 0.9, "gain": 2.5}]
}

@app.get("/api/devices")
def get_devices():
    devices = [{"id": "plug:bluealsa", "name": "BlueALSA (Bluetooth)"}]
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        res = subprocess.run(["aplay", "-l"], capture_output=True, text=True, env=env)
        usb_card = None
        for line in res.stdout.splitlines():
            if "USB" in line.upper() and re.search(r'(?:card|カード)\s+\d+', line, re.IGNORECASE):
                m = re.search(r'(?:card|カード)\s+(\d+)', line, re.IGNORECASE)
                if m:
                    usb_card = m.group(1)
                    break
        if usb_card: devices.append({"id": f"hw:{usb_card},0", "name": f"USB-DAC (hw:{usb_card},0)"})
        else: devices.append({"id": "none", "name": "USB-DAC (Not Connected)"})
        devices.append({"id": "hw:1,0", "name": "PC Speakers (hw:1,0)"})
    except Exception as e: devices.append({"id": "error", "name": str(e)})
    return devices

def generate_camilladsp_yaml(config: AudioConfig):
    # BT (bluealsa) uses LDAC @ 96kHz/S32_LE; HIFIMAN DAC uses max 48kHz/16bit
    is_bt = "bluealsa" in config.device
    is_usb = "USB-DAC" in config.device or "hw:2" in config.device
    
    samplerate = 48000 if is_usb else (96000 if is_bt else 192000)
    pb_format = "S16_LE" if is_usb else "S32_LE"
    
    # Loopback capture format from MPD
    cap_format = "S32_LE"

    # Single filter step covering both channels (CamillaDSP v4: "channels" is a list)
    filt = {"type": "Filter", "channels": [0, 1], "names": []}
    devices_block = {
        "samplerate": samplerate, "chunksize": 4096, "enable_rate_adjust": True,
        "capture": {"type": "Alsa", "channels": 2, "device": "hw:Loopback,1,0", "format": cap_format},
        "playback": {"type": "Alsa", "channels": 2, "device": config.device.replace("hw:", "plughw:") if config.device.startswith("hw:") else config.device, "format": pb_format}
    }
    # Resampling configuration if rates don't match MPD's 192000 output
    if samplerate != 192000:
        devices_block["capture_samplerate"] = 192000
        devices_block["resampler"] = {"type": "AsyncPoly", "interpolation": "Cubic"}
    else:
        devices_block["resampler"] = {"type": "Synchronous"}
        
    y = {
        "devices": devices_block,
        "filters": {},
        "pipeline": [filt]
    }
    def add_f(n, d):
        y["filters"][n] = d
        filt["names"].append(n)

    if config.hum_noise in ["50hz", "60hz"] and config.hum_noise != "none":
        add_f("rumble_cut", {"type": "Biquad", "parameters": {"type": "HighpassFO", "freq": 15}})
        f = 50 if config.hum_noise == "50hz" else 60
        add_f("hum", {"type": "Biquad", "parameters": {"type": "Notch", "freq": f, "q": 30.0}})

    if config.reverb != "none" and config.reverb_intensity > 0:
        import wave, array
        src_ir = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        os.makedirs("/tmp/camilladsp/ir", exist_ok=True)
        ir_path = f"/tmp/camilladsp/ir/{config.reverb}.wav"
        
        # Original simple scaling
        scale = config.reverb_intensity / 100.0  # reduced intensity
        with wave.open(src_ir, 'rb') as w:
            params = w.getparams()
            raw = w.readframes(w.getnframes())
        
        samples = array.array('h', raw)
        scaled = array.array('h', [max(-32768, min(32767, int(s * scale))) for s in samples])
        with wave.open(ir_path, 'wb') as w:
            w.setparams(params)
            w.writeframes(scaled.tobytes())

        add_f("rev", {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path}})
        
        y["pipeline"].append({"type": "Mixer", "name": "split_rev"})
        y["pipeline"].append({"type": "Filter", "channels": [2, 3], "names": ["rev"]})
        y["pipeline"].append({"type": "Mixer", "name": "join_rev"})
        
        # We must add a mixer to parallelize dry and wet!
        if "mixers" not in y:
            y["mixers"] = {}
        
        y["mixers"]["split_rev"] = {
            "channels": {"in": 2, "out": 4},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": 0, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": 0, "inverted": False}]},
                {"dest": 2, "sources": [{"channel": 0, "gain": 0, "inverted": False}]},
                {"dest": 3, "sources": [{"channel": 1, "gain": 0, "inverted": False}]}
            ]
        }
        y["mixers"]["join_rev"] = {
            "channels": {"in": 4, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": 0, "inverted": False}, {"channel": 2, "gain": 0, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": 0, "inverted": False}, {"channel": 3, "gain": 0, "inverted": False}]}
            ]
        }

        # Instead of generic filter, insert split, filter just 2,3, then join
        # Replace the direct "rev" from generic pipeline since we need specific routing
        if "rev" in filt["names"]: filt["names"].remove("rev")
        
        y["pipeline"].append({"type": "Mixer", "name": "split_rev"})
        y["pipeline"].append({"type": "Filter", "channels": [2, 3], "names": ["rev"]})
        y["pipeline"].append({"type": "Mixer", "name": "join_rev"})

    if config.crossfeed != "none":
        cf_gain_direct = -3.5
        cf_gain_cross = -9.5
        if config.crossfeed == "light":
            cf_gain_cross = -14.0  # Much weaker crossfeed
            cf_gain_direct = -1.5   # Less volume loss
        
        cf_mixer = {
            "channels": {"in": 2, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": cf_gain_direct, "inverted": False}, {"channel": 1, "gain": cf_gain_cross, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": cf_gain_direct, "inverted": False}, {"channel": 0, "gain": cf_gain_cross, "inverted": False}]}
            ]
        }
        
        if "mixers" not in y:
            y["mixers"] = {}
        y["mixers"]["cf"] = cf_mixer
        y["pipeline"].insert(0, {"type": "Mixer", "name": "cf"})

    for i, eq in enumerate(MUSIC_EQ.get(config.music_type, [])):
        add_f(f"m_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})
    for i, eq in enumerate(OUTPUT_EQ.get(config.eq_output, [])):
        add_f(f"o_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})

    # Add headroom gain to prevent digital clipping when applying EQ / IR Reverb
    if config.music_type != "none" or config.eq_output != "none" or config.reverb != "none":
        add_f("headroom", {"type": "Gain", "parameters": {"gain": -4.0, "inverted": False, "mute": False}})

    # Remove empty Filter steps (no names) so camilladsp doesn't fail on empty filter chains
    y["pipeline"] = [p for p in y["pipeline"] if not (p.get("type") == "Filter" and len(p.get("names", [])) == 0)]
    # If pipeline is completely empty, omit the key entirely (pure passthrough)
    if not y["pipeline"]:
        y["filters"]["dummy"] = {"type": "Gain", "parameters": {"gain": 0.0, "inverted": False, "mute": False}}; y["pipeline"] = [{"type": "Filter", "channels": [0, 1], "names": ["dummy"]}]

    os.makedirs("/tmp/camilladsp", exist_ok=True)
    with open("/tmp/camilladsp/active_dsp.yml", "w") as f: yaml.dump(y, f, sort_keys=False)
    return "/tmp/camilladsp/active_dsp.yml"

@app.post("/api/volume")
def set_volume(vol: VolumeControl):
    try:
        c = CamillaClient("127.0.0.1", 1234)
        c.connect(); c.volume.set_main_volume(vol.volume); c.disconnect()
        return {"status": "success"}
    except: return {"status": "error"}

def init_vol(v):
    time.sleep(1)
    try:
        c = CamillaClient("127.0.0.1", 1234)
        c.connect(); c.volume.set_main_volume(v); c.disconnect()
    except: pass

@app.post("/api/apply")
def apply_audio(config: AudioConfig, bt: BackgroundTasks):
    s = os.path.abspath("./scripts/switch_audio.sh")
    try:
        if config.mode == "dsp":
            yp = generate_camilladsp_yaml(config)
            subprocess.Popen(["bash", s, config.mode, config.device, yp])
            bt.add_task(init_vol, config.volume)
        else: subprocess.Popen(["bash", s, config.mode, config.device, "none"])
        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.get("/api/now_playing")
def get_np():
    try:
        c = mpd_connect()
        st = c.status()
        so = c.currentsong()
        c.disconnect()
        file_url = so.get("file", "")
        title = so.get("title", "Unknown")
        artist = so.get("artist", "Unknown").split(";")[0].split(",")[0].strip()
        album = so.get("album", "Unknown")
        
        # fallback to HTTP URL query info
        if "http" in file_url and (title == "Unknown" or artist == "Unknown"):
            q = parse_qs(urlparse(file_url).query)
            if "title" in q: title = q["title"][0]
            if "artist" in q: artist = q["artist"][0]
            elif "albumartist" in q: artist = q["albumartist"][0]
            if "album" in q: album = q["album"][0]
            
        return {"song_id": st.get("songid", ""), "title": title, "artist": artist, "album": album, "file": file_url}
    except: return {"error": "MPD offline"}

import urllib.parse

def check_local_art(filepath):
    if filepath.startswith("http"):
        try:
            parsed = urllib.parse.urlparse(filepath)
            filepath = urllib.parse.unquote(parsed.path)
        except:
            pass
    if os.path.exists(filepath):
        dirname = os.path.dirname(filepath)
    else:
        dirname = filepath
    for f in ["Folder.jpg", "folder.jpg", "cover.jpg", "Cover.jpg"]:
        p = os.path.join(dirname, f)
        if os.path.exists(p):
            return p
    return None

@app.get("/api/art")
def get_art(file: str, artist: str, album: str):
    local_art = check_local_art(file)
    if local_art:
        try:
            with open(local_art, "rb") as f:
                return Response(content=f.read(), media_type="image/jpeg")
        except: pass
    
    try:
        c = mpd_connect()
        try:
            p = c.readpicture(file)
            if p and "binary" in p: c.disconnect(); return Response(content=p["binary"], media_type="image/jpeg")
        except: pass
        try:
            a = c.albumart(file)
            if a and "binary" in a: c.disconnect(); return Response(content=a["binary"], media_type="image/jpeg")
        except: pass
        c.disconnect()
    except: pass
    if artist and album and artist != "Unknown":
        try:
            r = requests.get(f"https://itunes.apple.com/search?term={artist}+{album}&entity=album&limit=1", timeout=3)
            if r.json().get("results"): return RedirectResponse(r.json()["results"][0].get("artworkUrl100").replace("100x100", "600x600"))
        except: pass
    return Response(content='''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><rect width="300" height="300" fill="#1f2937"/><text x="50%" y="50%" fill="#4b5563" font-size="16" font-family="sans-serif" text-anchor="middle" dy=".3em">No Artwork</text></svg>''', media_type="image/svg+xml")
