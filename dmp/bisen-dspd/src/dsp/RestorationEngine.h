#ifndef RESTORATION_ENGINE_H
#define RESTORATION_ENGINE_H

// Bisen-DSP-System android/app/src/main/cpp/dsp/RestorationEngine.{h,cpp} の移植。
//
// 改変点:
//   1. レート適応 (計画書 §3-B): release 0.9996 (96kHz 前提) を
//      a = exp(-1/(rate*tau)) に一般化。192kHz → 0.99980。
//   2. 3 モード固定切替 (2026-10-13 利用者指示 — Bisen 将来構想に合わせた設計):
//        LOSSY_STANDARD: Lossy (MP3) 標準ビットレート → 擬似ロスレス
//        LOSSY_HIGH:     Lossy (MP3) 低ビットレート   → 補完度を高くした擬似ロスレス
//        CD_HIRES:       Lossless (CD)                → 疑似ハイレゾ (超音波帯倍音生成)
//      各モードは punch / harmonicGain / HF 強調 の 3 パラメータのプリセット。
class RestorationEngine {
public:
  enum Mode { LOSSY_STANDARD = 0, LOSSY_HIGH = 1, CD_HIRES = 2 };

  explicit RestorationEngine(int sampleRate);
  void process(float* buffer, int frames);  // interleaved stereo float32
  void setSampleRate(int sampleRate);
  void setEnabled(bool enabled);
  void setMode(Mode mode);
  void reset();

  float releaseCoef() const { return releaseCoefValue; }  // テスト用
  float punch() const { return profile.punch; }           // テスト用
  float harmonicGain() const { return profile.harmonicGain; }
  float hfEmphasis() const { return profile.hfEmphasis; }

private:
  struct ModeProfile {
    float punch;         // 過渡伸張の深さ
    float harmonicGain;  // 高調波添加ゲイン
    float hfEmphasis;    // 高域パス強調 (tanh ドライブへの加算 → HF/超音波倍音)
  };
  static const ModeProfile PROFILES[3];

  int sampleRate;
  bool enabled = false;
  Mode mode = LOSSY_STANDARD;
  ModeProfile profile = PROFILES[LOSSY_STANDARD];

  // Transient Punch state (Stereo Pair)
  float derivEnvL = 0.0f, derivEnvR = 0.0f;
  float punchPrevL = 0.0f, punchPrevR = 0.0f;

  // HF 強調用 1-pole LPF 状態 (hp = x - lp)
  float lpL = 0.0f, lpR = 0.0f;
  float hfCoef = 0.0f;  // fc ≈ 6kHz

  float releaseCoefValue = 0.9996f;

  void recomputeCoefficients();
};

#endif
