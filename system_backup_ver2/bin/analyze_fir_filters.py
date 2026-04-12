#!/usr/bin/env python3
"""
Analyze Noise Reduction FIR filters: compute frequency response, compare attenuation levels.
"""
import numpy as np
from scipy import signal
import os
import sys

# FIR filter files
FIR_BASE_PATH = "/home/tysbox/bin/"
FIR_TYPES = ["default", "light", "medium", "strong"]

def load_fir_coefficients(fir_type):
    """Load FIR coefficients from .txt file"""
    fir_file = f"{FIR_BASE_PATH}noise_fir_{fir_type}.txt"
    try:
        with open(fir_file, 'r') as f:
            lines = f.readlines()
        
        coeffs = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                coeffs.append(float(line))
            except ValueError:
                pass
        
        return np.array(coeffs), fir_file
    except FileNotFoundError:
        print(f"ERROR: {fir_file} not found")
        return None, fir_file

def compute_frequency_response(b, fs=192000, n_fft=8192):
    """Compute frequency response of FIR filter"""
    w, h = signal.freqz(b, worN=n_fft, fs=fs)
    magnitude_db = 20 * np.log10(np.abs(h) + 1e-10)  # Convert to dB
    phase = np.angle(h)
    return w, magnitude_db, phase

def find_cutoff_frequency(w, magnitude_db, cutoff_db=-3):
    """Find -3dB (half power) frequency"""
    dc_level = magnitude_db[0]
    target_level = dc_level + cutoff_db
    idx = np.argmin(np.abs(magnitude_db - target_level))
    return w[idx]

def find_stopband_attenuation(magnitude_db):
    """Find maximum attenuation in stopband (estimate from tail)"""
    return np.min(magnitude_db)

def analyze_all_filters():
    """Analyze all noise reduction filters"""
    
    print("=" * 80)
    print("NOISE REDUCTION FIR FILTER ANALYSIS")
    print("=" * 80)
    print()
    
    # Load all filters
    filters = {}
    for fir_type in FIR_TYPES:
        coeffs, path = load_fir_coefficients(fir_type)
        if coeffs is not None:
            filters[fir_type] = {
                'coeffs': coeffs,
                'path': path,
                'taps': len(coeffs)
            }
    
    if not filters:
        print("ERROR: No FIR filters found")
        return
    
    # Compute all frequency responses
    fs = 192000  # Sample rate
    for fir_type, data in filters.items():
        w, magnitude_db, phase = compute_frequency_response(data['coeffs'], fs=fs)
        data['w'] = w
        data['magnitude_db'] = magnitude_db
        data['phase'] = phase
        
        # Compute metrics
        data['dc_gain_db'] = magnitude_db[0]
        data['-3db_freq'] = find_cutoff_frequency(w, magnitude_db, -3)
        data['-20db_freq'] = find_cutoff_frequency(w, magnitude_db, -20)
        data['min_attenuation_db'] = find_stopband_attenuation(magnitude_db)
    
    # Print detailed analysis
    print("FILTER METRICS:")
    print("-" * 80)
    print(f"{'Type':<12} {'Taps':<8} {'DC Gain':<12} {'-3dB Freq':<15} {'Atten @ 10kHz':<15}")
    print("-" * 80)
    
    for fir_type in FIR_TYPES:
        if fir_type not in filters:
            continue
        
        data = filters[fir_type]
        w, magnitude_db = data['w'], data['magnitude_db']
        
        # Find attenuation at 10kHz
        idx_10k = np.argmin(np.abs(w - 10000))
        atten_10k = magnitude_db[idx_10k]
        
        print(f"{fir_type:<12} {data['taps']:<8} {data['dc_gain_db']:>10.3f} dB  "
              f"{data['-3db_freq']:>12.0f} Hz     {atten_10k:>13.3f} dB")
    
    print()
    
    # Extended frequency analysis
    print("FREQUENCY-DOMAIN ANALYSIS (Select frequencies):")
    print("-" * 80)
    test_freqs = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 96000]
    
    print(f"{'Frequency':<15}", end="")
    for fir_type in FIR_TYPES:
        if fir_type in filters:
            print(f"{fir_type:<15}", end="")
    print()
    print("-" * 80)
    
    for freq in test_freqs:
        print(f"{freq:<15}", end="")
        for fir_type in FIR_TYPES:
            if fir_type not in filters:
                continue
            w, magnitude_db = filters[fir_type]['w'], filters[fir_type]['magnitude_db']
            idx = np.argmin(np.abs(w - freq))
            actual_freq = w[idx]
            atten = magnitude_db[idx]
            if abs(actual_freq - freq) < 500:  # Close enough
                print(f"{atten:>6.2f} dB       ", end="")
            else:
                print(f"{'N/A':<15}", end="")
        print()
    
    print()
    
    # Comparative analysis
    print("COMPARATIVE ATTENUATION (relative to 'default' filter):")
    print("-" * 80)
    
    if 'default' in filters:
        default_w = filters['default']['w']
        default_mag = filters['default']['magnitude_db']
        
        for fir_type in FIR_TYPES:
            if fir_type not in filters or fir_type == 'default':
                continue
            
            other_mag = filters[fir_type]['magnitude_db']
            diff = other_mag - default_mag
            
            # Find maximum additional attenuation
            max_diff = np.max(np.abs(diff))
            max_diff_freq = default_w[np.argmax(np.abs(diff))]
            
            print(f"{fir_type:<12}: Max difference {max_diff:>7.3f} dB at {max_diff_freq:>8.0f} Hz")
    
    print()
    
    # Skipping plot generation (matplotlib not available)
    print("NOTE: For visual frequency response plots, install matplotlib:")
    print("  pip install matplotlib pillow")

if __name__ == "__main__":
    analyze_all_filters()
