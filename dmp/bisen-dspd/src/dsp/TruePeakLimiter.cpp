#include "TruePeakLimiter.h"
#include <cmath>
#include <algorithm>
#include <cstring>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

TruePeakLimiter::TruePeakLimiter(int sampleRate) : sampleRate(sampleRate) {
  init();
}

void TruePeakLimiter::setSampleRate(int rate) {
  if (this->sampleRate == rate) return;
  this->sampleRate = rate;
  init();
}

void TruePeakLimiter::reset() {
  std::fill(delayL.begin(), delayL.end(), 0.0f);
  std::fill(delayR.begin(), delayR.end(), 0.0f);
  std::memset(histL, 0, sizeof(histL));
  std::memset(histR, 0, sizeof(histR));
  writeIdx = 0;
  currentGain = 1.0f;
  lastTruePeakValue = 0.0f;
}

void TruePeakLimiter::init() {
  lookaheadSamples = static_cast<int>(sampleRate * 1.0f / 1000.0f);
  if (lookaheadSamples < 1) lookaheadSamples = 1;

  delayL.assign(lookaheadSamples + 1, 0.0f);
  delayR.assign(lookaheadSamples + 1, 0.0f);
  writeIdx = 0;

  // --- HIGH-QUALITY POLYPHASE FIR COEFFICIENTS (4x) ---
  for (int p = 0; p < 4; p++) {
    for (int i = 0; i < FIR_TAPS; i++) {
      float t = (float(i) - (FIR_TAPS - 1) / 2.0f) + (float(p) / 4.0f);
      if (std::abs(t) < 1e-6f) fir[p][i] = 1.0f;
      else {
        float x = M_PI * t;
        // Blackman-Harris Windowed Sinc
        float win = 0.35875f - 0.48829f * std::cos(2*M_PI*i/(FIR_TAPS-1)) + 0.14128f * std::cos(4*M_PI*i/(FIR_TAPS-1)) - 0.01168f * std::cos(6*M_PI*i/(FIR_TAPS-1));
        fir[p][i] = (std::sin(x) / x) * win;
      }
    }
  }

  std::memset(histL, 0, sizeof(histL));
  std::memset(histR, 0, sizeof(histR));

  attackStep = 1.0f / (sampleRate * 0.0001f);  // 0.1ms (Fast for safety)
  releaseStep = 1.0f / (sampleRate * 0.200f);   // 200ms (Musical release)
  currentGain = 1.0f;
}

float TruePeakLimiter::detectTruePeak(float sL, float sR) {
  // Shift history (scalar optimized)
  for (int i = FIR_TAPS - 1; i > 0; i--) {
    histL[i] = histL[i - 1]; histR[i] = histR[i - 1];
  }
  histL[0] = sL; histR[0] = sR;

  float maxP = 0.0f;
  for (int p = 0; p < 4; p++) {
    float iL = 0, iR = 0;
    for (int i = 0; i < FIR_TAPS; i++) {
      iL += histL[i] * fir[p][i];
      iR += histR[i] * fir[p][i];
    }
    maxP = std::max({maxP, std::abs(iL), std::abs(iR)});
  }
  return maxP;
}

void TruePeakLimiter::process(float* buffer, int frames) {
  const float threshold = 0.98f;
  const float knee = 0.02f;

  for (int i = 0; i < frames; i++) {
    const int idx = i * 2;

    // 0. Hard Input Clamp to prevent Limiter Internal Explosion
    float inL = std::max(-4.0f, std::min(4.0f, buffer[idx]));
    float inR = std::max(-4.0f, std::min(4.0f, buffer[idx + 1]));
    if (!std::isfinite(inL)) inL = 0.0f;
    if (!std::isfinite(inR)) inR = 0.0f;

    const float tp = detectTruePeak(inL, inR);
    if (tp > lastTruePeakValue) lastTruePeakValue = tp;
    float targetGain = 1.0f;

    if (tp > threshold - knee) {
      if (tp > threshold + knee) targetGain = threshold / tp;
      else {
        float x = (tp - (threshold - knee)) / (2.0f * knee);
        targetGain = 1.0f - (1.0f - threshold / (threshold + knee)) * x * x;
      }
    }

    // Apply Attack/Release smoothly
    if (currentGain > targetGain) currentGain = std::max(targetGain, currentGain - attackStep);
    else currentGain = std::min(1.0f, currentGain + releaseStep);

    // Circular Delay Line
    const int readIdx = (writeIdx + 1) % (lookaheadSamples + 1);
    buffer[idx] = delayL[readIdx] * currentGain;
    buffer[idx + 1] = delayR[readIdx] * currentGain;

    delayL[writeIdx] = inL;
    delayR[writeIdx] = inR;
    writeIdx = (writeIdx + 1) % (lookaheadSamples + 1);

    // Final sanity clamping
    if (!std::isfinite(buffer[idx])) buffer[idx] = 0.0f;
    if (!std::isfinite(buffer[idx + 1])) buffer[idx + 1] = 0.0f;
  }
}
