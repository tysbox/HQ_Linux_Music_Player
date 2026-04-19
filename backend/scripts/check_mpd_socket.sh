#!/usr/bin/env bash
set -eu

# Compare configured MPD_PORT (from backend/.env or env) and systemd mpd.socket ListenStream
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

MPD_PORT_ENV="$(grep -E '^MPD_PORT=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || true)"
MPD_PORT_ENV="${MPD_PORT_ENV:-$(printenv MPD_PORT || true)}"
MPD_PORT_ENV="${MPD_PORT_ENV:-6600}"

MPD_SOCKET_LINE_VALUES=( )
while IFS= read -r line; do
  line="${line#ListenStream=}"
  if [ -n "$line" ]; then
    MPD_SOCKET_LINE_VALUES+=("$line")
  fi
done < <(systemctl cat mpd.socket 2>/dev/null | sed -n 's/^[[:space:]]*ListenStream=//p')

printf 'Configured MPD_PORT (env/.env): %s\n' "${MPD_PORT_ENV}"
if [ ${#MPD_SOCKET_LINE_VALUES[@]} -eq 0 ]; then
  echo "Warning: could not read mpd.socket ListenStream; ensure mpd.socket exists or run as root"
  exit 1
fi

printf 'mpd.socket ListenStream values:\n'
for value in "${MPD_SOCKET_LINE_VALUES[@]}"; do
  printf '  %s\n' "$value"
done

MPD_SOCKET_PORTS="${MPD_SOCKET_LINE_VALUES[*]}"
MATCHED=false
for value in "${MPD_SOCKET_LINE_VALUES[@]}"; do
  if [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" = "$MPD_PORT_ENV" ]; then
    MATCHED=true
    break
  fi
done

if [ "$MATCHED" != true ]; then
  echo "ERROR: MPD port mismatch: backend expects ${MPD_PORT_ENV} but mpd.socket binds ${MPD_SOCKET_PORTS}" >&2
  exit 2
fi

echo "OK: MPD port values match (${MPD_PORT_ENV})"
exit 0
