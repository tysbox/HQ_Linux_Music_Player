fp = '/home/tysbox/HQ_Linux_Music_Player/backend/main.py'
with open(fp, 'r') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    
    # FIX B: Add crossfeed_intensity to _default_audio_config
    if '"crossfeed": "none",' in line and i > 50 and i < 130:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(f'{indent}"crossfeed_intensity": 5,\n')
        print(f'FIX B: Added crossfeed_intensity to _default_audio_config at line {i+1}')
    
    # FIX C: Add crossfeed_intensity to _config_requires_restart
    if '"crossfeed",' in line and i > 130 and i < 160:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(f'{indent}"crossfeed_intensity",\n')
        print(f'FIX C: Added crossfeed_intensity to _config_requires_restart at line {i+1}')

with open(fp, 'w') as f:
    f.writelines(new_lines)
