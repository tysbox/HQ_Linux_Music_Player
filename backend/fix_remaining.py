fp = '/home/tysbox/HQ_Linux_Music_Player/backend/main.py'
with open(fp, 'r') as f:
    content = f.read()

# FIX 1: Remove nested dead code (lines 234-271 approx)
# Use line-based approach for reliability
lines = content.split('\n')

# Find the dead code block
in_dead = False
new_lines = []
skip_until = -1

for i, line in enumerate(lines):
    # Skip dead code from "def _has_loopback_capture_device" inside _restore_last_config
    # until "@asynccontextmanager"
    if '    def _has_loopback_capture_device() -> bool:' in line and i > 200:
        in_dead = True
        continue
    if in_dead and line.strip() == '@asynccontextmanager':
        in_dead = False
        # Don't skip this line - keep @asynccontextmanager
        # But we already added one, so check if it's a duplicate
        # Actually we want to keep leading newlines
        new_lines.append('')
        new_lines.append(line)
        continue
    if in_dead:
        continue
    new_lines.append(line)

content = '\n'.join(new_lines)

# Verify fix
if '    def _has_loopback_capture_device() -> bool:' in content:
     # Check if it's now only appearing once (at module level)
    count = content.count('def _has_loopback_capture_device')
    if count == 1:
        print(f'FIX 1: Removed dead nested code (now {count} definition left)')
    else:
        print(f'FIX 1: WARNING - still {count} definitions found')
else:
    print('FIX 1: All nested definitions removed')

# FIX 3: Add Conv gain parameter
old_conv = '''            add_f("rev", {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path}})'''
new_conv = '''             # Conv gain controls wet-level: intensity=50 -> ~-6dB, intensity=100 -> 0dB
            wet_rate = max(0.01, min(1.0, config.reverb_intensity / 100.0))
            wet_gain_db = round(20 * math.log10(max(wet_rate, 0.0001)), 2)
            add_f("rev", {"type": "Conv", "parameters": {"type": "Wav", "filename": ir_path, "gain": wet_gain_db}})'''

if old_conv in content:
    content = content.replace(old_conv, new_conv)
    print('FIX 3: Added Conv gain parameter')
else:
    print('FIX 3: Pattern not found (already applied?)')

with open(fp, 'w') as f:
    f.write(content)

print('Remaining fixes applied.')
