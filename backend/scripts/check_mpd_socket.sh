#!/bin/bash
# check_mpd_socket.sh — verify mpd listen port matches backend config
set -eu
REPO=/home/tysbox/HQ_Linux_Music_Player
ENV_FILE="$REPO/backend/.env"
MPD_PORT_DEFAULT=6601

MPD_PORT=${MPD_PORT:-}
if [ -z "$MPD_PORT" ] && [ -f "$ENV_FILE" ]; then
  MPD_PORT=$(grep -E '^\s*MPD_PORT=' "$ENV_FILE" | head -n1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]') || true
fi
MPD_PORT=${MPD_PORT:-$MPD_PORT_DEFAULT}

# get systemd ListenStream for mpd.socket
LS=$(systemctl show -p ListenStream mpd.socket 2>/dev/null | cut -d'=' -f2 || true)
LS_PORT=""
if [ -n "$LS" ]; then
  # LS may be like '6600' or '127.0.0.1:6600' or '::1:6600' or multiple values
  LS_PORT=$(echo "$LS" | awk -F"," '{print $1}' | sed -E 's/.*:([0-9]+)$/\1/; t; s/^([0-9]+)$/\1/;') || true
fi

if [ -z "$LS_PORT" ]; then
  # fallback: try mpd.conf
  if [ -f /etc/mpd.conf ]; then
    LS_PORT=$(grep -E '^\s*port\s+' /etc/mpd.conf | awk '{print $2}' | tr -d '"' | tr -d "'" | head -n1 || true)
  fi
fi

if [ -z "$LS_PORT" ]; then
  echo "check_mpd_socket: could not determine mpd listen port; assuming MPD_PORT=${MPD_PORT}" >&2
  exit 0
fi

if [ "$LS_PORT" -eq "$MPD_PORT" ]; then
  echo "check_mpd_socket: ok (mpd listens on ${LS_PORT}, backend expects ${MPD_PORT})"
  exit 0
else
  echo "check_mpd_socket: ERROR: mpd listens on ${LS_PORT} but backend expects ${MPD_PORT}" >&2
  exit 1
fi
