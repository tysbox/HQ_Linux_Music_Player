#include "alsa_io.h"

AlsaPcm::AlsaPcm(std::string device, Dir dir, int rate, int channels,
                 int periodFrames, int periodCount)
    : device(std::move(device)), dir(dir), rate(rate), channels(channels),
      periodFrames(periodFrames), periodCount(periodCount) {}

AlsaPcm::~AlsaPcm() { close(); }

bool AlsaPcm::open(std::string& err) {
  if (pcm) return true;  // 既に open 済み

  snd_pcm_t* handle = nullptr;
  const snd_pcm_stream_t stream =
      (dir == Dir::Capture) ? SND_PCM_STREAM_CAPTURE : SND_PCM_STREAM_PLAYBACK;
  if (snd_pcm_open(&handle, device.c_str(), stream, 0) != 0) {
    err = "snd_pcm_open failed: " + device;
    return false;
  }

  snd_pcm_hw_params_t* hw = nullptr;
  snd_pcm_hw_params_alloca(&hw);
  bool ok = true;

  do {
    if (snd_pcm_hw_params_any(handle, hw) < 0) { err = "hw_params_any failed"; ok = false; break; }
    if (snd_pcm_hw_params_set_access(handle, hw, SND_PCM_ACCESS_RW_INTERLEAVED) < 0) {
      err = "set_access RW_INTERLEAVED failed"; ok = false; break;
    }
    if (snd_pcm_hw_params_set_format(handle, hw, SND_PCM_FORMAT_S32_LE) < 0) {
      err = "set_format S32_LE failed"; ok = false; break;
    }
    if (snd_pcm_hw_params_set_channels(handle, hw, channels) < 0) {
      err = "set_channels failed"; ok = false; break;
    }
    unsigned r = static_cast<unsigned>(rate);
    if (snd_pcm_hw_params_set_rate_near(handle, hw, &r, nullptr) < 0) {
      err = "set_rate_near failed"; ok = false; break;
    }
    actualRateValue = static_cast<int>(r);
    if (actualRateValue != rate) {
      err = "rate mismatch: requested " + std::to_string(rate) + " got " +
            std::to_string(actualRateValue);
      ok = false;
      break;
    }
    snd_pcm_uframes_t per = static_cast<snd_pcm_uframes_t>(periodFrames);
    if (snd_pcm_hw_params_set_period_size_near(handle, hw, &per, nullptr) < 0) {
      err = "set_period_size_near failed"; ok = false; break;
    }
    snd_pcm_uframes_t bufFrames =
        static_cast<snd_pcm_uframes_t>(per * periodCount);
    if (snd_pcm_hw_params_set_buffer_size_near(handle, hw, &bufFrames) < 0) {
      err = "set_buffer_size_near failed"; ok = false; break;
    }
    if (snd_pcm_hw_params(handle, hw) < 0) { err = "hw_params apply failed"; ok = false; break; }
  } while (false);

  if (!ok) {
    snd_pcm_close(handle);
    return false;
  }
  pcm = handle;
  return true;
}

void AlsaPcm::close() {
  if (pcm) {
    snd_pcm_drain(pcm);  // capture では即返り、playback は残バッファ吐き出し
    snd_pcm_close(pcm);
    pcm = nullptr;
  }
}

snd_pcm_sframes_t AlsaPcm::read(int32_t* buf, snd_pcm_uframes_t frames) {
  if (!pcm) return -1;
  snd_pcm_sframes_t n = snd_pcm_readi(pcm, buf, frames);
  if (n < 0) {
    // -EPIPE (overrun) / -ESTRPIPE は自動復帰
    if (snd_pcm_recover(pcm, static_cast<int>(n), 1) == 0) {
      n = snd_pcm_readi(pcm, buf, frames);
    }
  }
  return n;
}

bool AlsaPcm::write(const int32_t* buf, snd_pcm_uframes_t frames) {
  if (!pcm) return false;
  snd_pcm_uframes_t written = 0;
  while (written < frames) {
    snd_pcm_sframes_t n = snd_pcm_writei(pcm, buf + written * channels, frames - written);
    if (n < 0) {
      if (snd_pcm_recover(pcm, static_cast<int>(n), 1) != 0) return false;
      n = 0;  // recover 後は次ループで再書き込み
    }
    written += static_cast<snd_pcm_uframes_t>(n);
  }
  return true;
}
