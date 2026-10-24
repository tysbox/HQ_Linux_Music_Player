// main.cpp — bisen-dspd: Bisen DSP (Tube / Restore / TruePeakLimiter) 移植デーモン
//
// 信号チェーン (Bisen NativeAudioEngine L227-252 忠実・計画書 §3-B):
//   [capture hw:Loopback,1,1] → RestorationEngine → TubeModel → TruePeakLimiter
//                          → [playback plughw:1,0]
//   (hum / EQ / crossfeed は CamillaDSP 担当のため本デーモンは持たない — 二重処理なし)
//
// 経路制御 (既存システム完全保護):
//   routing=0 (既定) の間は ALSA デバイスを一切開かない → CamillaDSP 直結構成に無影響。
//   hq_api / switch_audio.sh が `set routing 1` を送ってから CamillaDSP の YAML を
//   hw:Loopback,0,1 へ切替える (Step 3-5 オーケストレーション)。
//
// レート: S32_LE / 2ch / 192kHz 想定だが --rate で可変 (係数は全てレート適応)。
#include "alsa_io.h"
#include "control.h"
#include "params.h"
#include "sd_notify.h"
#include "dsp/RestorationEngine.h"
#include "dsp/TruePeakLimiter.h"
#include "dsp/TubeModel.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>
#include <vector>

#include <sched.h>

static std::atomic<bool> gRunning{true};
static void onSignal(int) { gRunning = false; }

namespace {

struct Args {
  std::string capture = "hw:Loopback,1,1";
  std::string playback = "plughw:1,0";
  std::string socket = "/run/bisen-dspd/control.sock";
  int rate = 192000;
  int channels = 2;
  int periodFrames = 1024;
  int periodCount = 4;
};

Args parseArgs(int argc, char** argv) {
  Args a;
  for (int i = 1; i < argc; i++) {
    const std::string k = argv[i];
    auto next = [&]() -> const char* {
      if (i + 1 >= argc) { std::fprintf(stderr, "missing value for %s\n", k.c_str()); std::exit(2); }
      return argv[++i];
    };
    if (k == "--capture") a.capture = next();
    else if (k == "--playback") a.playback = next();
    else if (k == "--socket") a.socket = next();
    else if (k == "--rate") a.rate = std::atoi(next());
    else if (k == "--period") a.periodFrames = std::atoi(next());
    else if (k == "--periods") a.periodCount = std::atoi(next());
    else { std::fprintf(stderr, "unknown arg: %s\n", k.c_str()); std::exit(2); }
  }
  return a;
}

void logLine(const char* fmt, ...) {
  std::printf("[bisen-dspd] ");
  va_list ap;
  va_start(ap, fmt);
  std::vprintf(fmt, ap);
  va_end(ap);
  std::printf("\n");
  std::fflush(stdout);
}

void tryRealtime(int prio) {
  struct sched_param sp {};
  sp.sched_priority = prio;
  if (sched_setscheduler(0, SCHED_FIFO, &sp) != 0) {
    logLine("WARN: SCHED_FIFO(%d) not granted (systemd LimitRTPRIO があれば有効)", prio);
  } else {
    logLine("SCHED_FIFO(%d) active", prio);
  }
}

}  // namespace

int main(int argc, char** argv) {
  const Args args = parseArgs(argc, argv);

  std::signal(SIGINT, onSignal);
  std::signal(SIGTERM, onSignal);
  std::signal(SIGHUP, SIG_IGN);

  logLine("starting: capture=%s playback=%s rate=%d period=%dx%d",
          args.capture.c_str(), args.playback.c_str(), args.rate,
          args.periodFrames, args.periodCount);

  DspParams params;
  ControlServer control(params, args.socket);
  if (!control.start()) {
    logLine("FATAL: cannot create control socket %s", args.socket.c_str());
    return 1;
  }
  logLine("control socket: %s", args.socket.c_str());

  tryRealtime(50);

  // ── DSP チェーン (Bisen 順: restoration → tube → limiter) ──
  RestorationEngine restoration(args.rate);
  TubeModel tube(args.rate);
  TruePeakLimiter limiter(args.rate);

  std::vector<int32_t> pcm(static_cast<size_t>(args.periodFrames) * args.channels);
  std::vector<float> flt(pcm.size());

  bool prevTubeEnabled = false;
  bool prevRestoreEnabled = false;

  AlsaPcm cap(args.capture, AlsaPcm::Dir::Capture, args.rate, args.channels,
              args.periodFrames, args.periodCount);
  AlsaPcm pb(args.playback, AlsaPcm::Dir::Playback, args.rate, args.channels,
             args.periodFrames, args.periodCount);
  bool routeActive = false;

  sd_notify_msg("READY=1");
  logLine("READY (standby — `set routing 1` で ALSA 経路を確保)");

  auto lastWatchdog = std::chrono::steady_clock::now();

  while (gRunning) {
    const auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration_cast<std::chrono::seconds>(now - lastWatchdog).count() >= 1) {
      sd_notify_msg("WATCHDOG=1");
      lastWatchdog = now;
    }

    // ── standby / active 切替 ──
    if (!params.routing) {
      if (routeActive) {
        pb.close();
        cap.close();
        params.playbackOpen = false;
        routeActive = false;
        logLine("routing released — back to standby (CamillaDSP 直結に復帰可)");
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
      continue;
    }
    if (!routeActive) {
      // 出力デバイス反映 (standby 中に set output_device が来た場合)
      {
        std::lock_guard<std::mutex> lock(params.deviceMutex);
        if (params.outputDevice != pb.currentDevice()) pb.setDevice(params.outputDevice);
      }
      params.deviceChanged = false;
      std::string err;
      if (!cap.open(err)) {
        logLine("WARN: capture open failed (%s) — retrying", err.c_str());
        params.xruns++;
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        continue;
      }
      if (!pb.open(err)) {
        cap.close();
        logLine("WARN: playback open failed (%s) — DAC は CamillaDSP 保持? retrying", err.c_str());
        params.xruns++;
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        continue;
      }
      routeActive = true;
      params.playbackOpen = true;
      restoration.reset();
      tube.reset();
      limiter.reset();
      logLine("routing active: %s -> DSP -> %s (%d Hz)", args.capture.c_str(),
              args.playback.c_str(), pb.actualRate());
    }

    // ── 再生中の出力デバイス切替 (set output_device) ──
    if (routeActive && params.deviceChanged.exchange(false)) {
      std::string dev;
      {
        std::lock_guard<std::mutex> lock(params.deviceMutex);
        dev = params.outputDevice;
      }
      if (!dev.empty() && dev != pb.currentDevice()) {
        logLine("output device change: %s -> %s (reopening)", pb.currentDevice().c_str(),
                dev.c_str());
        pb.close();
        pb.setDevice(dev);
        cap.close();
        params.playbackOpen = false;
        routeActive = false;  // 次ループで通常オープン経路から再確保
        continue;
      }
    }

    // ── capture ──
    const snd_pcm_sframes_t n =
        cap.read(pcm.data(), static_cast<snd_pcm_uframes_t>(args.periodFrames));
    if (n < 0) {
      params.xruns++;
      continue;
    }
    if (n == 0) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
      continue;
    }

    // ── パラメータ反映 (period 境界のみ — Bisen std::atomic 方式) ──
    const bool tubeEn = params.tubeEnabled.load();
    const bool restoreEn = params.restoreEnabled.load();
    if (tubeEn != prevTubeEnabled) { tube.reset(); prevTubeEnabled = tubeEn; }
    if (restoreEn != prevRestoreEnabled) { restoration.reset(); prevRestoreEnabled = restoreEn; }
    tube.setEnabled(tubeEn);
    tube.setParameters(params.tubeType == 1 ? TubeModel::PENTODE : TubeModel::TRIODE,
                       params.tubeBias.load() / 100.0f);  // GUI 0..100 → Bisen 0..1
    restoration.setEnabled(restoreEn);
    restoration.setMode(static_cast<RestorationEngine::Mode>(params.restoreMode.load() & 3));

    const bool dspActive = !params.bypass.load() && (tubeEn || restoreEn);

    if (dspActive) {
      // S32 → float32
      const size_t total = static_cast<size_t>(n) * args.channels;
      for (size_t i = 0; i < total; i++) {
        flt[i] = static_cast<float>(static_cast<double>(pcm[i]) / 2147483648.0);
      }
      // チェーン: restoration → tube → limiter (Bisen 順)
      restoration.process(flt.data(), static_cast<int>(n));
      tube.process(flt.data(), static_cast<int>(n));
      limiter.process(flt.data(), static_cast<int>(n));

      // Phase 4 (Step 4-1): true-peak (4x OS 検出値) を公開 — VU 切替用
      const float tp = limiter.lastTruePeak();
      params.truePeakDb = tp > 0.0f ? 20.0f * std::log10(tp) : -60.0f;

      // ピークメータ (DSP 後 = DAC へ出す実信号)
      float maxL = 0.0f, maxR = 0.0f;
      for (int i = 0; i < n; i++) {
        const float l = std::fabs(flt[static_cast<size_t>(i) * 2]);
        const float r = std::fabs(flt[static_cast<size_t>(i) * 2 + 1]);
        if (l > maxL) maxL = l;
        if (r > maxR) maxR = r;
      }
      params.peakDbL = maxL > 0.0f ? 20.0f * std::log10(maxL) : -60.0f;
      params.peakDbR = maxR > 0.0f ? 20.0f * std::log10(maxR) : -60.0f;

      // float32 → S32 (クランプ付き)
      for (size_t i = 0; i < total; i++) {
        float v = flt[i];
        if (!std::isfinite(v)) v = 0.0f;
        if (v > 1.0f) v = 1.0f;
        if (v < -1.0f) v = -1.0f;
        pcm[i] = static_cast<int32_t>(v * 2147483647.0);
      }
    } else {
      // バイパス = bitwise passthrough (S32 往復変換なし — 受け入れ条件)
      int64_t maxL = 0, maxR = 0;
      for (int i = 0; i < n; i++) {
        const int64_t l = std::llabs(static_cast<long long>(pcm[static_cast<size_t>(i) * 2]));
        const int64_t r = std::llabs(static_cast<long long>(pcm[static_cast<size_t>(i) * 2 + 1]));
        if (l > maxL) maxL = l;
        if (r > maxR) maxR = r;
      }
      params.peakDbL = maxL > 0 ? static_cast<float>(20.0 * std::log10(static_cast<double>(maxL) / 2147483648.0)) : -60.0f;
      params.peakDbR = maxR > 0 ? static_cast<float>(20.0 * std::log10(static_cast<double>(maxR) / 2147483648.0)) : -60.0f;
    }

    // ── playback ──
    if (!pb.write(pcm.data(), static_cast<snd_pcm_uframes_t>(n))) {
      params.xruns++;
      logLine("WARN: playback write failed (xrun) — recovering");
    }
    params.framesProcessed += static_cast<uint64_t>(n);

    // 2026-10-24: AlsaPcm が数えた実 xrun を公開 (音途切れの実測用)。
    params.alsaXruns = cap.xrunCount() + pb.xrunCount();
  }

  sd_notify_msg("STOPPING=1");
  logLine("shutting down: frames=%llu xruns=%llu",
          (unsigned long long)params.framesProcessed.load(),
          (unsigned long long)params.xruns.load());
  pb.close();
  cap.close();
  control.stop();
  return 0;
}
