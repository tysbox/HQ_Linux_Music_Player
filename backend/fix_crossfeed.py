fp = '/home/tysbox/HQ_Linux_Music_Player/backend/main.py'
with open(fp, 'r') as f:
    content = f.read()

# FIX: Remove crossfeed_intensity from _config_requires_restart keys
# AudioConfig doesn't have this attribute, causing 500 errors on /api/apply
old_keys = '''    for key in [
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

new_keys = '''    for key in [
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

if old_keys in content:
    content = content.replace(old_keys, new_keys)
    print('FIX: Removed crossfeed_intensity from _config_requires_restart keys')
else:
    print('FIX: Pattern not found - already fixed?')

with open(fp, 'w') as f:
    f.write(content)
