#!/usr/bin/env bash
set -eu

# Compare configured MPD_PORT (from backend/.env or env) and systemd mpd.socket ListenStream
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

MPD_PORT_ENV="$(grep -E '^MPD_PORT=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || true)"
MPD_PORT_ENV="${MPD_PORT_ENV:-$(printenv MPD_PORT || true)}"
MPD_PORT_ENV="${MPD_PORT_ENV:-6600}"

MPD_SOCKET_PORT="$(systemctl cat mpd.socket 2>/dev/null | grep -E '^\s*ListenStream=' | head -n1 | sed -E 's/\s*ListenStream=//')"
MPD_SOCKET_PORT="${MPD_SOCKET_PORT:-}
"

echo "Configured MPD_PORT (env/.env): ${MPD_PORT_ENV}"
if [ -z "$MPD_SOCKET_PORT" ]; then
  echo "Warning: could not read mpd.socket ListenStream; ensure mpd.socket exists or run as root"
  exit 1
fi
echo "mpd.socket ListenStream: ${MPD_SOCKET_PORT}"

if [ "$MPD_PORT_ENV" != "$MPD_SOCKET_PORT" ]; then
  echo "ERROR: MPD port mismatch: backend expects ${MPD_PORT_ENV} but mpd.socket binds ${MPD_SOCKET_PORT}" >&2
  exit 2
fi

echo "OK: MPD port values match (${MPD_PORT_ENV})"
exit 0
