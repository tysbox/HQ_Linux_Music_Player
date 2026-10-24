// sd_notify.h — libsystemd 不要の最小 sd_notify 実装 (READY / WATCHDOG 通知)
#pragma once
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

inline bool sd_notify_msg(const std::string& payload) {
  const char* sock = std::getenv("NOTIFY_SOCKET");
  if (!sock || !*sock) return false;  // systemd 経由起動でない → 何もしない

  int fd = ::socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
  if (fd < 0) return false;

  struct sockaddr_un addr;
  std::memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  // systemd の抽象ソケットは '@' 接頭辞 → 実際のアドレスは '\0'
  const char* path = sock;
  if (sock[0] == '@') {
    addr.sun_path[0] = '\0';
    std::strncpy(addr.sun_path + 1, sock + 1, sizeof(addr.sun_path) - 2);
  } else {
    std::strncpy(addr.sun_path, sock, sizeof(addr.sun_path) - 1);
    path = sock;
  }
  socklen_t len;
  if (sock[0] == '@') {
    len = static_cast<socklen_t>(offsetof(struct sockaddr_un, sun_path) + 1 + std::strlen(sock + 1));
  } else {
    len = static_cast<socklen_t>(offsetof(struct sockaddr_un, sun_path) + 1 + std::strlen(sock));
  }
  (void)path;
  const bool ok = ::sendto(fd, payload.data(), payload.size(), 0,
                           reinterpret_cast<struct sockaddr*>(&addr), len) >= 0;
  ::close(fd);
  return ok;
}
