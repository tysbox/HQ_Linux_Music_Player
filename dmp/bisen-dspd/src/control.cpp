#include "control.h"
#include "params.h"

#include <cctype>
#include <cstring>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <sys/stat.h>

ControlServer::ControlServer(DspParams& params, std::string socketPath)
    : params(params), path(std::move(socketPath)) {}

ControlServer::~ControlServer() { stop(); }

bool ControlServer::start() {
  ::unlink(path.c_str());  // 古いソケット掃除

  listenFd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (listenFd < 0) return false;

  struct sockaddr_un addr;
  std::memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  if (path.size() >= sizeof(addr.sun_path)) { ::close(listenFd); listenFd = -1; return false; }
  std::strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);

  if (::bind(listenFd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) != 0) {
    ::close(listenFd);
    listenFd = -1;
    return false;
  }
  // 所有者のみアクセス可能 (localhost 専用設計・決定 D-8)
  ::chmod(path.c_str(), 0600);

  if (::listen(listenFd, 4) != 0) {
    ::close(listenFd);
    listenFd = -1;
    return false;
  }

  running = true;
  thread = std::thread([this] { serve(); });
  return true;
}

void ControlServer::stop() {
  running = false;
  if (listenFd >= 0) {
    ::shutdown(listenFd, SHUT_RDWR);
    ::close(listenFd);
    listenFd = -1;
  }
  if (thread.joinable()) thread.join();
  if (!path.empty()) ::unlink(path.c_str());
}

void ControlServer::serve() {
  char buf[512];
  while (running) {
    const int fd = ::accept(listenFd, nullptr, nullptr);
    if (fd < 0) {
      if (!running) break;
      continue;
    }
    // 1 接続 1 コマンド (シンプル・ステートレス)。残りデータは破棄。
    std::string line;
    for (;;) {
      const ssize_t n = ::read(fd, buf, sizeof(buf));
      if (n <= 0) break;
      line.append(buf, static_cast<size_t>(n));
      if (line.find('\n') != std::string::npos) break;
    }
    // 末尾の改行/CR を除去
    while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) line.pop_back();

    const std::string resp = handleLine(line) + "\n";
    (void)::write(fd, resp.data(), resp.size());
    ::close(fd);
  }
}

static std::string trimCopy(const std::string& s) {
  size_t b = 0, e = s.size();
  while (b < e && std::isspace(static_cast<unsigned char>(s[b]))) b++;
  while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) e--;
  return s.substr(b, e - b);
}

static bool parseBool(const std::string& v, bool& out) {
  if (v == "1" || v == "true" || v == "on") { out = true; return true; }
  if (v == "0" || v == "false" || v == "off") { out = false; return true; }
  return false;
}

static bool parseFloat01(const std::string& v, float lo, float hi, float& out) {
  try {
    const float f = std::stof(v);
    if (f < lo || f > hi) return false;
    out = f;
    return true;
  } catch (...) { return false; }
}

std::string ControlServer::handleLine(const std::string& raw) const {
  const std::string line = trimCopy(raw);
  if (line == "ping") return "pong";

  // ── get ──
  if (line == "get params") {
    const char* restoreModeName[] = {"lossy_standard", "lossy_high", "cd"};
    char out[512];
    std::snprintf(out, sizeof(out),
      "routing=%d bypass=%d tube_enabled=%d tube_type=%s tube_bias=%.1f "
      "restore_enabled=%d restore_mode=%s playback_open=%d",
      params.routing ? 1 : 0, params.bypass ? 1 : 0,
      params.tubeEnabled ? 1 : 0, params.tubeType ? "PENTODE" : "TRIODE",
      params.tubeBias.load(), params.restoreEnabled ? 1 : 0,
      restoreModeName[params.restoreMode.load() & 3],
      params.playbackOpen ? 1 : 0);
    return out;
  }
  if (line == "get peaks") {
    char out[256];
    std::snprintf(out, sizeof(out),
      "peak_db_l=%.2f peak_db_r=%.2f frames=%llu xruns=%llu",
      params.peakDbL.load(), params.peakDbR.load(),
      (unsigned long long)params.framesProcessed.load(),
      (unsigned long long)params.xruns.load());
    return out;
  }

  // ── set <key> <value> ──
  if (line.rfind("set ", 0) == 0) {
    const std::string body = line.substr(4);
    const size_t sp = body.find(' ');
    if (sp == std::string::npos) return "ERROR usage: set <key> <value>";
    const std::string key = body.substr(0, sp);
    const std::string val = trimCopy(body.substr(sp + 1));
    bool b = false;
    float f = 0;

    if (key == "routing" && parseBool(val, b)) { params.routing = b; return "OK"; }
    if (key == "bypass" && parseBool(val, b)) { params.bypass = b; return "OK"; }
    if (key == "tube_enabled" && parseBool(val, b)) { params.tubeEnabled = b; return "OK"; }
    if (key == "restore_enabled" && parseBool(val, b)) { params.restoreEnabled = b; return "OK"; }
    if (key == "tube_bias" && parseFloat01(val, 0.0f, 100.0f, f)) { params.tubeBias = f; return "OK"; }
    if (key == "restore_mode") {
      // 3 モード固定切替 (2026-10-13 利用者指示 — 強度スライダ廃止)
      if (val == "lossy_standard" || val == "0" || val == "standard") { params.restoreMode = 0; return "OK"; }
      if (val == "lossy_high" || val == "1" || val == "high") { params.restoreMode = 1; return "OK"; }
      if (val == "cd" || val == "2" || val == "cd_hires") { params.restoreMode = 2; return "OK"; }
      return "ERROR restore_mode must be lossy_standard|lossy_high|cd";
    }
    if (key == "tube_type") {
      if (val == "TRIODE" || val == "0" || val == "300B") { params.tubeType = 0; return "OK"; }
      if (val == "PENTODE" || val == "1" || val == "KT88") { params.tubeType = 1; return "OK"; }
      return "ERROR tube_type must be TRIODE|PENTODE";
    }
    return "ERROR unknown key or bad value: " + key;
  }

  return "ERROR unknown command";
}
