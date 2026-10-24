// alsa_io.h — ALSA PCM ラッパ (S32_LE / 2ch / 指定レート、blocking RW interleaved)
#pragma once
#include <cstdint>
#include <string>
#include <alsa/asoundlib.h>

class AlsaPcm {
public:
  enum class Dir { Capture, Playback };

  AlsaPcm(std::string device, Dir dir, int rate, int channels,
          int periodFrames, int periodCount);
  ~AlsaPcm();

  // 成功=true。err に人間可読エラー。複数回呼んでも安全 (二重 open は skip)。
  bool open(std::string& err);
  void close();

  // Capture: 読めたフレーム数 (>=0)。エラー時は内部で recover を試み、負値を返す。
  snd_pcm_sframes_t read(int32_t* buf, snd_pcm_uframes_t frames);
  // Playback: 全フレーム書き込み。false の場合は recover 済み (呼び出し側は継続可)。
  bool write(const int32_t* buf, snd_pcm_uframes_t frames);

  bool isOpen() const { return pcm != nullptr; }
  int actualRate() const { return actualRateValue; }
  const std::string& currentDevice() const { return device; }
  void setDevice(const std::string& newDevice) { device = newDevice; }  // close 後に呼ぶこと

  // 2026-10-24 追加: xrun (overrun/underrun) 検出回数。
  //   read()/write() は内部で snd_pcm_recover() するため、復帰に成功すると
  //   呼び出し側からは異常が見えず、音途切れが統計に現れなかった。
  //   復帰を試みた時点でカウントし、実測可能にする。
  uint64_t xrunCount() const { return xruns; }
  void resetXrunCount() { xruns = 0; }

private:
  snd_pcm_t* pcm = nullptr;
  std::string device;
  Dir dir;
  int rate;
  int channels;
  int periodFrames;
  int periodCount;
  int actualRateValue = 0;
  uint64_t xruns = 0;
};
