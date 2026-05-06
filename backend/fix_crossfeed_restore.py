fp = '/home/tysbox/HQ_Linux_Music_Player/backend/main.py'
with open(fp, 'r') as f:
    content = f.read()

# FIX: Add crossfeed_intensity back to AudioConfig model
old_model = '''class AudioConfig(BaseModel):
    mode: str
    device: str
    volume: float
    music_type: str
    eq_output: str
    crossfeed: str
    hum_noise: str
    reverb: str
    reverb_intensity: int = 5'''

new_model = '''class AudioConfig(BaseModel):
    mode: str
    device: str
    volume: float
    music_type: str
    eq_output: str
    crossfeed: str
    crossfeed_intensity: int = 5
    hum_noise: str
    reverb: str
    reverb_intensity: int = 5'''

if old_model in content:
    content = content.replace(old_model, new_model)
    print('FIX A: Added crossfeed_intensity to AudioConfig model')
else:
    print('FIX A: AudioConfig pattern not found')

# FIX: Add crossfeed_intensity back to _default_audio_config
old_default = '''def _default_audio_config() -> dict:
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
      }'''

new_default = '''def _default_audio_config() -> dict:
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
      }'''

if old_default in content:
    content = content.replace(old_default, new_default)
    print('FIX B: Added crossfeed_intensity to _default_audio_config')
else:
    print('FIX B: _default_audio_config pattern not found')

# FIX: Add crossfeed_intensity back to _config_requires_restart
old_restart_check = '''    for key in [
          "mode",
          "device",
          "music_type",
          "eq_output",
          "crossfeed",
          "hum_noise",
          "reverb",
          "reverb_intensity",
      ]:
        if last_config.get(key) != getattr(config, key):
            return True'''

new_restart_check = '''    for key in [
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
            return True'''

if old_restart_check in content:
    content = content.replace(old_restart_check, new_restart_check)
    print('FIX C: Added crossfeed_intensity back to _config_requires_restart')
else:
    print('FIX C: _config_requires_restart pattern not found')

# FIX: Update _normalize_config_for_device to include crossfeed_intensity
old_normalize = '''        return AudioConfig(
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
          )'''

# Check if it's already there - if so, no need to change
if 'crossfeed_intensity=5' in old_normalize:
    print('FIX D: _normalize_config_for_device already has crossfeed_intensity')
else:
    print('FIX D: Need to update _normalize_config_for_device')
    new_norm = '''        return AudioConfig(
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
          )'''

# FIX: Update generate_camilladsp_yaml to use crossfeed_intensity for variable gains
old_cf_section = '''    if config.crossfeed != "none":
        cf_gain_direct = -3.5
        cf_gain_cross = -9.5
        if config.crossfeed == "light":
            cf_gain_cross = -14.0
            cf_gain_direct = -1.5'''

new_cf_section = '''    if config.crossfeed != "none":
        # Variable crossfeed gain based on intensity (1-100)
        intensity = config.crossfeed_intensity
        intensity_pct = max(0.01, min(1.0, intensity / 100.0))
        if config.crossfeed == "light":
            # Light: cross gains from -20dB (min) to -14dB (max)
            cf_gain_cross = round(-20 + 6 * intensity_pct, 1)
            cf_gain_direct = round(-1.5 * (1 - intensity_pct), 1)
        else:
            # Standard: cross gains from -20dB (min) to -9.5dB (max)
            cf_gain_cross = round(-20 + 10.5 * intensity_pct, 1)
            cf_gain_direct = round(-3.5 * (1 - intensity_pct), 1)'''

if old_cf_section in content:
    content = content.replace(old_cf_section, new_cf_section)
    print('FIX E: Updated crossfeed to use variable intensity')
else:
    print('FIX E: Crossfeed section pattern not found')

with open(fp, 'w') as f:
    f.write(content)

print('\nAll crossfeed fixes applied.')
