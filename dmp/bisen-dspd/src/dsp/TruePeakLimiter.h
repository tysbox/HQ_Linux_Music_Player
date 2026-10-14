#ifndef TRUE_PEAK_LIMITER_H
#define TRUE_PEAK_LIMITER_H

#include <vector>

// Bisen-DSP-System android/app/src/main/cpp/dsp/TruePeakLimiter.{h,cpp} の
// ほぼ無変更移植 (既にレート適応実装のため §3-B 変換不要)。
//
// Professional 4x Oversampling True Peak Limiter.
// Prevents ISP (Inter-sample Peaks) for absolute digital safety.
class TruePeakLimiter {
public:
  explicit TruePeakLimiter(int sampleRate);
  void process(float* buffer, int frames);
  void setSampleRate(int sampleRate);
  void reset();

  // Phase 4 (Step 4-1): 直近 period の true-peak (4x OS 検出値) を返す。
  // VU メータ供給用 — process() が呼ばれるたびに更新される。
  float lastTruePeak() const { return lastTruePeakValue; }

private:
  int sampleRate;
  static constexpr float LOOKAHEAD_MS = 1.0f;
  int lookaheadSamples;

  // Circ Buffers
  std::vector<float> delayL, delayR;
  int writeIdx = 0;

  // FIR 4x Interpolation
  static constexpr int FIR_TAPS = 24;
  float fir[4][FIR_TAPS];
  float histL[FIR_TAPS], histR[FIR_TAPS];

  float currentGain = 1.0f;
  float attackStep, releaseStep;
  float lastTruePeakValue = 0.0f;

  void init();
  float detectTruePeak(float sL, float sR);
};

#endif
