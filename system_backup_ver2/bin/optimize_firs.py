#!/usr/bin/env python3
"""
FIR analysis and optimization utility.
- Moves extraneous FIR files (not in allowed names) to a timestamped backup dir.
- Analyzes noise and harmonic FIRs (tap count, max|h|, sum, L2)
- Designs optimized versions using firwin2 to match magnitude response while reducing peak coefficient amplitude (optionally increasing taps).
- Writes .opt.txt files and prints a summary. Use --apply to replace originals.
"""
import os, sys, shutil, time
import numpy as np
from scipy import signal

BASEDIR = os.path.dirname(__file__)
NOISE_PATTERN = 'noise_fir'
HARM_PATTERN = 'harmonic'

# Allowed names (from GUI)
ALLOWED_NOISE = ['noise_fir_default.txt','noise_fir_light.txt','noise_fir_medium.txt','noise_fir_strong.txt']
ALLOWED_HARM = ['harmonic_dead.txt','harmonic_base.txt','harmonic_med.txt','harmonic_high.txt','harmonic_dynamic.txt']

BACKUP_DIR = os.path.join(BASEDIR, 'firs_backup_' + time.strftime('%Y%m%dT%H%M%S'))

os.makedirs(BACKUP_DIR, exist_ok=True)


def read_coefs(path):
    with open(path,'r') as f:
        lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
    coefs = np.array([float(l) for l in lines], dtype=float)
    return coefs


def write_coefs(path, coefs, header=None):
    with open(path,'w') as f:
        if header:
            f.write(header + '\n')
        for c in coefs:
            f.write(f"{c:.12g}\n")


def freq_response(coefs, nfft=16384):
    # compute magnitude on normalized freq [0,1] (1=Nyquist)
    H = np.fft.rfft(coefs, n=nfft)
    mag = np.abs(H)
    # normalize freq points
    freqs = np.linspace(0,1,len(mag))
    return freqs, mag


def design_by_firwin2(target_mag, freqs, numtaps):
    # firwin2 expects freq in [0,1] and desired magnitude (linear)
    # Interpolate target_mag (already on freqs) to fewer points
    # We'll sample at e.g. 512 points
    m = 1024
    samp_freqs = np.linspace(0,1,m)
    samp_mag = np.interp(samp_freqs, freqs, target_mag)
    # Ensure endpoints
    samp_freqs[0] = 0.0
    samp_freqs[-1] = 1.0
    h = signal.firwin2(numtaps, samp_freqs, samp_mag, window='hamming')
    return h


def analyze_and_optimize(path, increase_taps_factor=1.0, apply=False):
    print('---', os.path.basename(path))
    h = read_coefs(path)
    n = len(h)
    mx = np.max(np.abs(h))
    s = np.sum(h)
    l2 = np.linalg.norm(h)
    print(f'taps={n} max|h|={mx:.6g} sum={s:.6g} L2={l2:.6g}')

    freqs, mag = freq_response(h, nfft=32768)
    # target_mag: normalized 0..1
    target_mag = mag / np.max(mag)

    # decide new taps
    new_taps = int(n * increase_taps_factor)
    if new_taps % 2 == 0:
        new_taps += 1
    if new_taps < 3:
        new_taps = n

    h_new = design_by_firwin2(target_mag, freqs, new_taps)

    # scale to preserve DC gain (sum)
    sum_new = np.sum(h_new)
    if abs(sum_new) > 1e-20:
        h_new *= (s / sum_new)

    # Additional scaling to reduce peak coefficient magnitude while preserving effect via gain compensation
    mx_new = np.max(np.abs(h_new))
    # choose target_max heuristically based on original peak
    # aim to bring peaks down to 0.5 if original > 0.9, otherwise reduce by 10-20% conservatively
    if mx_new > 0.9:
        target_max = 0.5
    elif mx_new > 0.6:
        target_max = mx_new * 0.7
    else:
        target_max = mx_new  # already small enough

    scale_factor = 1.0
    comp_db = 0.0
    if mx_new > target_max and target_max > 0:
        scale_factor = target_max / mx_new
        h_new = h_new * scale_factor
        comp_db = -20.0 * np.log10(scale_factor)  # dB to ADD during playback to compensate

    l2_new = np.linalg.norm(h_new)
    mx_new = np.max(np.abs(h_new))
    print(f'new_taps={len(h_new)} max|h|={mx_new:.6g} sum={np.sum(h_new):.6g} L2={l2_new:.6g} scale_factor={scale_factor:.6g} comp_db={comp_db:.3f}')

    outpath = path + '.opt.txt'
    header = (f'# optimized from {os.path.basename(path)} on {time.strftime("%Y-%m-%dT%H:%M:%S")}\n'
              f'# original_taps={n} new_taps={len(h_new)}\n'
              f'# scale_factor={scale_factor:.12g} # comp_db={comp_db:.3f}')
    write_coefs(outpath, h_new, header=header)
    print('wrote', outpath)

    if apply:
        bak = path + '.bak.' + time.strftime('%Y%m%dT%H%M%S')
        shutil.copy2(path, bak)
        shutil.copy2(outpath, path)
        print('replaced original (backup at', bak, ')')

    return {'orig_n':n,'orig_max':mx,'new_n':len(h_new),'new_max':mx_new,'scale':scale_factor,'comp_db':comp_db,'out':outpath}


# 1) Move extraneous FIR files (not in allowed lists) to backup dir
all_files = os.listdir(BASEDIR)
extras = []
for fn in all_files:
    if fn.startswith('noise') and fn not in ALLOWED_NOISE:
        extras.append(fn)
    if fn.startswith('harmonic') and fn not in ALLOWED_HARM:
        extras.append(fn)

if extras:
    print('found extra FIR files to move to backup:', extras)
    for e in extras:
        src = os.path.join(BASEDIR,e)
        dst = os.path.join(BACKUP_DIR,e)
        shutil.move(src,dst)
        print('moved', e, '->', dst)
else:
    print('no extraneous FIR files found')

# 2) Optimize default noise filter (increase taps to reduce peak)
def_results = analyze_and_optimize(os.path.join(BASEDIR,'noise_fir_default.txt'), increase_taps_factor=2.0, apply=False)

# 3) Optimize other noise filters with smaller increase taps (preserve latency)
others = ['noise_fir_light.txt','noise_fir_medium.txt','noise_fir_strong.txt']
other_results = []
for of in others:
    p = os.path.join(BASEDIR, of)
    if os.path.exists(p):
        other_results.append(analyze_and_optimize(p, increase_taps_factor=1.0, apply=False))

# 4) Optimize harmonic filters (use modest tap increase)
harms = ['harmonic_dead.txt','harmonic_base.txt','harmonic_med.txt','harmonic_high.txt','harmonic_dynamic.txt']
harm_results = []
for hfn in harms:
    p = os.path.join(BASEDIR,hfn)
    if os.path.exists(p):
        harm_results.append(analyze_and_optimize(p, increase_taps_factor=1.0, apply=False))

print('\nSummary:')
print('default:', def_results)
print('others:', other_results)
print('harmonic:', harm_results)

print('\nIf you want to apply the optimized files to replace originals, run with --apply')

if __name__ == '__main__':
    if '--apply' in sys.argv:
        print('\nApplying optimized files into place...')
        # Move originals to backup dir already created
        for res in [def_results]+other_results+harm_results:
            try:
                src = res['out']
                orig = src.replace('.opt.txt','')
                bak = os.path.join(BACKUP_DIR, os.path.basename(orig))
                # original file already present unless it was moved earlier
                if os.path.exists(orig):
                    shutil.copy2(orig, bak)
                shutil.copy2(src, orig)
                print('applied', orig, 'backup->', bak)
            except Exception as e:
                print('failed to apply', res, e)
