// control.h — Unix domain socket 制御サーバ (localhost 専用・決定 D-8)
//
// ラインプロトコル (1 リクエスト 1 行 → 1 レスポンス 1 行):
//   ping
//   set routing 0|1          ← ALSA 経路の確保/解放 (hq_api / switch_audio.sh が使用)
//   set bypass 0|1
//   set tube_enabled 0|1
//   set tube_type TRIODE|PENTODE|0|1
//   set tube_bias <0..100>
//   set restore_enabled 0|1
//   set restore_mode lossy_standard|lossy_high|cd   (3 モード固定切替)
//   set output_device <alsa-device>   (DAC 動的切替 — 再生中は再オープン)
//   get params
//   get peaks
// 応答: "OK" / "ERROR <reason>" / 状態 1 行
#pragma once
#include <atomic>
#include <string>
#include <thread>

struct DspParams;

class ControlServer {
public:
  ControlServer(DspParams& params, std::string socketPath);
  ~ControlServer();

  bool start();  // ソケット作成 + 受付スレッド起動
  void stop();

private:
  DspParams& params;
  std::string path;
  int listenFd = -1;
  std::atomic<bool> running{false};
  std::thread thread;

  void serve();
  std::string handleLine(const std::string& line) const;
};
