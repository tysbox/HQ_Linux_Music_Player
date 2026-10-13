// params.h — bisen-dspd 制御パラメータ (再生中に制御スレッドから安全に更新)
//
// Bisen (NativeDspChain.java) は std::atomic でパラメータ安全性を担保している。
// 本移植も同様に std::atomic のみを使用し、ロックフリーで音声スレッドから読む。
#pragma once
#include <atomic>
#include <cstdint>

struct DspParams {
  // ── 経路制御 ──
  // routing=1 のときのみ ALSA デバイス (capture hw:Loopback,1,1 / playback plughw:1,0)
  // を開く。standby 時は既存の CamillaDSP 直結構成に一切干渉しない。
  std::atomic<bool> routing{false};

  // ── DSP 制御 (hq_api が Unix socket 経由で更新) ──
  std::atomic<bool> bypass{true};          // true = チェーン全バイパス (bitwise passthrough)
  std::atomic<bool> tubeEnabled{false};
  std::atomic<int> tubeType{0};            // 0=TRIODE(300B) / 1=PENTODE(KT88)
  std::atomic<float> tubeBias{0.0f};       // 0..100 (Bisen 内部仕様 0..1 に正規化)
  std::atomic<bool> restoreEnabled{false};
  std::atomic<int> restoreMode{0};            // 0=LOSSY_STANDARD / 1=LOSSY_HIGH / 2=CD_HIRES

  // ── 状態 (GUI へ読み出し / Phase 4 VU true-peak 切替に使用) ──
  std::atomic<float> peakDbL{-60.0f};
  std::atomic<float> peakDbR{-60.0f};
  std::atomic<uint64_t> framesProcessed{0};
  std::atomic<uint64_t> xruns{0};
  std::atomic<bool> playbackOpen{false};   // DAC を掴んでいるか (hq_api 切替順序制御用)
};
