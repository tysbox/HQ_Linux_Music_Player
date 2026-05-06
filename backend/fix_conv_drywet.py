fp = '/home/tysbox/HQ_Linux_Music_Player/backend/main.py'
with open(fp, 'r') as f:
    content = f.read()

# Fix: Remove gain parameter from Conv, use proper dry/wet mixer instead
old_reverb_block = '''    if config.reverb != "none" and config.reverb_intensity > 0:
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

new_reverb_block = '''    if config.reverb != "none" and config.reverb_intensity > 0:
        src_ir = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        ir_path = f"/tmp/camilladsp/ir/{config.reverb}.wav"
        os.makedirs("/tmp/camilladsp/ir", exist_ok=True)
        try:
            if not os.path.exists(src_ir):
                raise FileNotFoundError(f"IR source missing: {src_ir}")
             _write_ambience_ir(src_ir, ir_path, config.reverb_intensity)
             # Use proper dry/wet mixer: dry passes through, wet conv signal mixed in
            wet_rate = max(0.0, min(1.0, config.reverb_intensity / 100.0))
            add_f("conv", {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path}})
            add_f("wet", {"type": "Gain", "parameters": {"gain": round(wet_rate * 5, 2), "inverted": False, "mute": False}})
             # Mixer: dry (ch 0) + wet (ch 2) -> L, dry (ch 1) + wet (ch 3) -> R
            if "mixers" not in y:
                y["mixers"] = {}
            y["mixers"]["rev_mix"] = {
                 "channels": {"in": 4, "out": 2},
                 "mapping": [
                     {"dest": 0, "sources": [
                         {"channel": 0, "gain": 0.0, "inverted": False},
                         {"channel": 2, "gain": 0.0, "inverted": False},
                     ]},
                     {"dest": 1, "sources": [
                         {"channel": 1, "gain": 0.0, "inverted": False},
                         {"channel": 3, "gain": 0.0, "inverted": False},
                     ]},
                 ],
             }
            # Insert rev pipeline: conv filter -> wet gain -> mixer
            rev_conv = {"type": "Filter", "channels": [0, 1], "names": ["conv"]}
            rev_wet = {"type": "Filter", "channels": [0, 1], "names": ["wet"]}
            rev_mixer = {"type": "Mixer", "name": "rev_mix"}
             # Find and replace the main filter in pipeline
            for idx, p in enumerate(y["pipeline"]):
                if p.get("type") == "Mixer" or p.get("type") == "Filter":
                     # Insert before the main processing block
                    y["pipeline"].insert(idx, rev_conv)
                    y["pipeline"].insert(idx + 1, rev_wet)
                    y["pipeline"].insert(idx + 2, rev_mixer)
                    break
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

if old_reverb_block in content:
    content = content.replace(old_reverb_block, new_reverb_block)
    print("FIX: Updated reverb processing with proper dry/wet mixer")
else:
    print("FIX: Pattern not found")

with open(fp, 'w') as f:
    f.write(content)
