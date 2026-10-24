#include "TubeModel.h"
#include <cmath>
#include <algorithm>

// Bisen 96kHz 実装係数からの逆算時定数 (秒):
//   tau = -1 / (96000 * ln(a))
//   attack 0.9992 → 0.0130155s / release 0.9998 → 0.0520784s / DC 0.9995 → 0.0208281s
// これにより任意レートで時定数が保存され、96kHz で Bisen 値を正確に再現する。
static constexpr float SAG_ATTACK_TAU  = 0.0130155f;
static constexpr float SAG_RELEASE_TAU = 0.0520784f;
static constexpr float DC_BLOCKER_TAU   = 0.0208281f;

TubeModel::TubeModel(int sampleRate) : sampleRate(sampleRate) {
  recomputeCoefficients();
}

void TubeModel::setSampleRate(int rate) {
  this->sampleRate = rate;
  recomputeCoefficients();
}

void TubeModel::setEnabled(bool en) { this->enabled = en; }

void TubeModel::setParameters(Type t, float b) {
  this->type = t;
  this->bias = b;
}

void TubeModel::reset() {
  sagEnv = 0.0f;
  dcL = 0.0f;
  dcR = 0.0f;
}

void TubeModel::recomputeCoefficients() {
  if (sampleRate <= 0) return;
  const float sr = static_cast<float>(sampleRate);
  sagAtt = std::exp(-1.0f / (sr * SAG_ATTACK_TAU));
  sagRel = std::exp(-1.0f / (sr * SAG_RELEASE_TAU));
  dcCoef = std::exp(-1.0f / (sr * DC_BLOCKER_TAU));
}

float TubeModel::processSample(float x, float& dcState) {
  // 1. Grid Bias Offset - Recalibrated for 0dBFS headroom
  const float offset = bias * 0.20f;
  const float input = (x + offset);  // Reduced gain to prevent clipping

  // 2. Nonlinear Transfer (Harmonic Depth enhancement)
  float output;
  if (type == TRIODE) {
    const float s = std::tanh(input * 1.1f);
    output = s + 0.12f * (s * s);  // 偶数次高調波 (Bisen そのまま)
  } else {
    output = std::tanh(input * 1.3f) / 1.05f;  // Pentode saturation
  }

  // 3. DC Blocker (One-pole HPF — 係数のみレート適応)
  const float res = output - std::tanh(offset);
  dcState = dcState * dcCoef + res * (1.0f - dcCoef);
  const float out = res - dcState;

  return std::isfinite(out) ? out : 0.0f;
}

void TubeModel::applySag(float& l, float& r) {
  const float pwr = (l * l + r * r) * 0.5f;

  if (pwr > sagEnv) sagEnv = sagEnv * sagAtt + pwr * (1.0f - sagAtt);
  else              sagEnv = sagEnv * sagRel + pwr * (1.0f - sagRel);

  const float sagFactor = 1.0f / (1.0f + sagEnv * 0.35f);
  l *= sagFactor;
  r *= sagFactor;
}

void TubeModel::process(float* buffer, int frames) {
  if (!enabled || frames <= 0) return;

  for (int i = 0; i < frames; i++) {
    const int idx = i * 2;
    float L = buffer[idx];
    float R = buffer[idx + 1];

    // 1. Summed Power Supply Sag
    applySag(L, R);

    // 2. Discrete Grid Saturation & DC Removal
    buffer[idx] = processSample(L, dcL);
    buffer[idx + 1] = processSample(R, dcR);

    // Safety
    if (!std::isfinite(buffer[idx])) buffer[idx] = 0.0f;
    if (!std::isfinite(buffer[idx + 1])) buffer[idx + 1] = 0.0f;
  }
}
