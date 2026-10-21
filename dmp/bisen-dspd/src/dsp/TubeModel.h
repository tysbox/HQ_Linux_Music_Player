#ifndef TUBE_MODEL_H
#define TUBE_MODEL_H

// Bisen-DSP-System android/app/src/main/cpp/dsp/TubeModel.{h,cpp} の移植。
//
// 改変点 (計画書 §3-B レート適応):
//   Bisen は 96kHz 前提のハードコード係数 (Sag attack 0.9992 / release 0.9998 /
//   DC blocker 0.9995)。本移植は時定数保存の a = exp(-1/(rate*tau)) に一般化し、
//   - 96kHz  → Bisen と完全一致 (0.9992 / 0.9998 / 0.9995)
//   - 192kHz → 計画書 §3-B の √f 変換値 (0.99960 / 0.99990 / 0.99975)
//   tanh 伝達自体はレート非依存のため無変更。
class TubeModel {
public:
  enum Type { TRIODE, PENTODE };

  explicit TubeModel(int sampleRate);
  void process(float* buffer, int frames);   // interleaved stereo float32
  void setParameters(Type type, float bias); // bias 0..1 (Bisen 仕様)
  void setEnabled(bool enabled);
  void setSampleRate(int sampleRate);
  void reset();

  // テスト用 (96kHz パリティ / 192kHz 変換値の検証)
  float sagAttackCoef() const { return sagAtt; }
  float sagReleaseCoef() const { return sagRel; }
  float dcBlockerCoef() const { return dcCoef; }

private:
  int sampleRate;
  Type type = TRIODE;
  float bias = 0.0f;
  bool enabled = false;

  // Power Supply Sag & DC Blocking (Stereo Independent)
  float sagEnv = 0.0f;
  float dcL = 0.0f, dcR = 0.0f;

  // rate-adaptive coefficients
  float sagAtt = 0.0f, sagRel = 0.0f, dcCoef = 0.0f;

  void applySag(float& l, float& r);
  float processSample(float x, float& dcState);
  void recomputeCoefficients();
};

#endif
