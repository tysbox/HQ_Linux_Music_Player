#include "RestorationEngine.h"
#include <cmath>
#include <algorithm>

// Bisen 96kHz 実装係数 0.9996 からの逆算時定数: tau = 0.0260363s
//   96kHz → exp(-1/(96000*0.0260363)) = 0.9996  (Bisen と完全一致)
//   192kHz → exp(-1/(192000*0.0260363)) = 0.99980 (計画書 §3-B 変換値)
static constexpr float RELEASE_TAU = 0.0260363f;

// ── 3 モード プリセット (2026-10-13 利用者指示) ──────────────────
// Bisen V4.5.6 基準値: punch=0.65 / harmonicGain=0.08 (LOSSY_STANDARD がこれ)。
//   LOSSY_HIGH : 低ビットレート (128kbps 級) の 16kHz 帯域欠損を重点補完
//                → 過渡・高調波とも強め + HF 強調
//   CD_HIRES   : Lossless は過渡が無傷のため punch を絞り、
//                HF 強調で 10-20kHz 倍音 → 20kHz 超の疑似ハイレゾ帯を生成
static constexpr float HF_EMPHASIS_FC = 6000.0f;

const RestorationEngine::ModeProfile RestorationEngine::PROFILES[3] = {
    /* LOSSY_STANDARD */ {0.65f, 0.08f, 0.00f},
    /* LOSSY_HIGH     */ {0.85f, 0.13f, 0.25f},
    /* CD_HIRES       */ {0.30f, 0.06f, 0.50f},
};

RestorationEngine::RestorationEngine(int sampleRate) : sampleRate(sampleRate) {
  reset();
  recomputeCoefficients();
}

void RestorationEngine::setSampleRate(int rate) {
  this->sampleRate = rate;
  recomputeCoefficients();
}

void RestorationEngine::setEnabled(bool en) { this->enabled = en; }

void RestorationEngine::setMode(Mode m) {
  if (m < LOSSY_STANDARD || m > CD_HIRES) m = LOSSY_STANDARD;
  this->mode = m;
  this->profile = PROFILES[m];
}

void RestorationEngine::reset() {
  derivEnvL = 0.0f; derivEnvR = 0.0f;
  punchPrevL = 0.0f; punchPrevR = 0.0f;
  lpL = 0.0f; lpR = 0.0f;
}

void RestorationEngine::recomputeCoefficients() {
  if (sampleRate <= 0) return;
  releaseCoefValue = std::exp(-1.0f / (static_cast<float>(sampleRate) * RELEASE_TAU));
  const float w = 2.0f * 3.14159265358979f * HF_EMPHASIS_FC;
  hfCoef = w / (w + static_cast<float>(sampleRate));  // 1-pole LPF fc≈6kHz
}

void RestorationEngine::process(float* buffer, int frames) {
  if (!enabled || frames <= 0) return;

  const float punch = profile.punch;
  const float harmonicGain = profile.harmonicGain;
  const float hfEmphasis = profile.hfEmphasis;
  const float release = releaseCoefValue;

  for (int i = 0; i < frames; i++) {
    for (int ch = 0; ch < 2; ch++) {
      const int idx = i * 2 + ch;
      const float x = buffer[idx];
      float& p = (ch == 0) ? punchPrevL : punchPrevR;
      float& env = (ch == 0) ? derivEnvL : derivEnvR;
      float& lp = (ch == 0) ? lpL : lpR;

      // 1. High-Pass Delta Detection (過渡検出)
      const float diff = std::abs(x - p);
      p = x;

      if (diff > env) env = diff;
      else env *= release;

      // 2. Harmonic Excitation (High-frequency focus)
      //    Bisen: wet = tanh(x*1.05) / harmonics = (wet - x) * gain
      //    モード拡張: hfEmphasis > 0 のとき tanh へのドライブに
      //    1-pole HPF (fc≈6kHz) 成分を加算 → 高域の曲率が増え、
      //    HF/超音波帯の倍音が強化される (CD = 疑似ハイレゾ、LOW = 帯域補完)。
      float drive = x;
      if (hfEmphasis > 0.0f) {
        lp += hfCoef * (x - lp);      // 1-pole LPF
        const float hp = x - lp;       // 高域成分
        drive = x + hfEmphasis * hp;   // HF 強調ドライブ
      }
      const float wet = std::tanh(drive * 1.05f);
      const float harmonics = (wet - x) * harmonicGain;

      // 3. Adaptive Transient Punch (上向き伸張)
      const float gain = 1.0f + std::min(0.5f, env * punch * 15.0f);

      buffer[idx] = (x + harmonics) * gain;

      if (!std::isfinite(buffer[idx])) buffer[idx] = 0.0f;
    }
  }
}

