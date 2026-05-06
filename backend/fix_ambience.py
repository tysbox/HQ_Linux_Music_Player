import math

fp = '/home/tysbox/HQ_Linux_Music_Player/backend/main.py'
with open(fp, 'r') as f:
    content = f.read()

# FIX 0: Add math import
if 'import math\n' not in content:
    first_import = content.find('from urllib.parse import urlparse, parse_qs')
    if first_import >= 0:
        content = content[:first_import] + 'import math\n' + content[first_import:]
        print('FIX 0: Added import math')
    else:
        content = 'import math\n' + content
        print('FIX 0: Added import math at top')

# FIX 1: Remove nested dead code from _restore_last_config  (lines ~230-259)
old_chunk = '''    except Exception:
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



@asynccontextmanager'''

new_chunk = '''    except Exception:
        pass


@asynccontextmanager'''

if old_chunk in content:
    content = content.replace(old_chunk, new_chunk)
    print('FIX 1: Removed nested dead code from _restore_last_config')
else:
    print('FIX 1: Pattern not found')

# FIX 2: Fix _write_ambience_ir - remove DC offset bug
old_ir = '''def _write_ambience_ir(src_ir: str, dest_ir: str, intensity: int):
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
        wav_file.writeframes(blended.tobytes())'''

new_ir = '''def _write_ambience_ir(src_ir: str, dest_ir: str, intensity: int):
    """Process IR file with intensity-based amplitude scaling.

    CamillaDSP Conv filter convolves the input with this IR.
    The dry signal passes through by default in CamillaDSP.
    We scale the IR amplitude here; the Conv gain parameter in YAML
    controls the actual wet-level of the reverb effect.
    """
    with wave.open(src_ir, "rb") as wav_file:
        params = wav_file.getparams()
        raw = wav_file.readframes(wav_file.getnframes())

    if params.sampwidth != 2:
        raise ValueError(f"Unsupported IR sample width: {params.sampwidth * 8}-bit")

    samples = array.array("h", raw)
    wet_rate = max(0.01, min(1.0, intensity / 100.0))
    blended = array.array("h", [0] * len(samples))
    for index, sample in enumerate(samples):
        value = int(sample * wet_rate)
        blended[index] = max(-32768, min(32767, value))

    with wave.open(dest_ir, "wb") as wav_file:
        wav_file.setparams(params)
        wav_file.writeframes(blended.tobytes())'''

if old_ir in content:
    content = content.replace(old_ir, new_ir)
    print('FIX 2: Fixed _write_ambience_ir (removed DC offset bug)')
else:
    print('FIX 2: Pattern not found (already fixed by FIX 1?)')

# FIX 3: Add Conv gain parameter for proper wet/dry mixing
old_reverb = '''    if config.reverb != "none" and config.reverb_intensity > 0:
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
                    lof.write(f"Failed to process IR {config.reverb}: {str(e)}\\n")
                    lof.write(tb + "\\n")
            except Exception:
                pass
            raise'''

new_reverb = '''    if config.reverb != "none" and config.reverb_intensity > 0:
        src_ir = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        ir_path = f"/tmp/camilladsp/ir/{config.reverb}.wav"
        os.makedirs("/tmp/camilladsp/ir", exist_ok=True)
        try:
            if not os.path.exists(src_ir):
                raise FileNotFoundError(f"IR source missing: {src_ir}")
             _write_ambience_ir(src_ir, ir_path, config.reverb_intensity)
            # Conv gain controls wet-level: intensity=50 -> ~-6dB, intensity=100 -> 0dB
            wet_rate = max(0.01, min(1.0, config.reverb_intensity / 100.0))
            wet_gain_db = round(20 * math.log10(max(wet_rate, 0.0001)), 2)
            add_f("rev", {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path, "gain": wet_gain_db}})
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            try:
                with open("/tmp/hq_api_apply.log", "a") as lof:
                    lof.write(f"Failed to process IR {config.reverb}: {str(e)}\\n")
                    lof.write(tb + "\\n")
            except Exception:
                pass
            raise'''

if old_reverb in content:
    content = content.replace(old_reverb, new_reverb)
    print('FIX 3: Added Conv gain parameter to reverb YAML generation')
else:
    print('FIX 3: Pattern not found')

# FIX 4: Add CamillaDSP health-check and restart API
health_code = '''
# ---- CamillaDSP Health Check & Restart API ----
@app.get("/api/dsp_status")
def get_dsp_status():
    """Check if CamillaDSP is running on port 1234."""
    try:
        c = CamillaClient("127.0.0.1", 1234)
        c.connect()
        v = c.version()
        c.disconnect()
        return {"status": "running", "version": v}
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
        _schedule_init_vol(normalized.volume, fade_in=True, wait_for_restart=True)
        _save_last_config(normalized.model_dump())
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}


'''

insert_marker = '''# 設定適用'''
if insert_marker in content:
    idx = content.index(insert_marker)
    content = content[:idx] + health_code + content[idx:]
    print('FIX 4: Added DSP health-check and restart endpoints')
else:
    print('FIX 4: Insert marker not found')

with open(fp, 'w') as f:
    f.write(content)
print('\nAll fixes applied successfully.')
