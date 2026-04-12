#!/bin/bash
# bt_connect_watcher.sh
# - moniters BlueZ connected A2DP devices and restarts run_sox_fifo.service
# - when a connected A2DP device appears/disappears, restart sox pipeline so it picks correct PLAY_DEVICE

LOGFILE="/var/log/bt_connect_watcher.log"
: > "$LOGFILE"
chmod 644 "$LOGFILE" 2>/dev/null || true

prev_connected=""

# helper: return space-separated list of connected A2DP device MACs
get_connected_a2dp() {
  local out=""
  if ! command -v bluetoothctl >/dev/null 2>&1; then
    echo ""
    return
  fi

  for mac in $(bluetoothctl devices | awk '{print $2}'); do
    info=$(bluetoothctl info "$mac" 2>/dev/null)
    if echo "$info" | grep -q "Connected: yes"; then
      # check for Audio Sink / A2DP service UUID
      if echo "$info" | grep -Eq "Audio Sink|0000110b"; then
        out="$out $mac"
      fi
    fi
  done
  # normalize whitespace
  echo "$out" | xargs
}

logger -t bt-connect-watcher "started"

# main loop (original lightweight behavior — immediate restart on connect/disconnect)
while true; do
  connected=$(get_connected_a2dp)
  if [ "$connected" != "$prev_connected" ]; then
    logger -t bt-connect-watcher "connected set changed: '$prev_connected' -> '$connected'"
    echo "$(date -Is) connected set changed: '$prev_connected' -> '$connected'" >> "$LOGFILE"

    # Switch to LDAC if available (2s delay for BlueALSA PCM to register)
    if [ -n "$connected" ]; then
      sleep 2
      for pcm in $(bluealsa-cli list-pcms 2>/dev/null); do
        if bluealsa-cli codec "$pcm" LDAC 2>/dev/null; then
          logger -t bt-connect-watcher "LDAC activated on $pcm"
          echo "$(date -Is) LDAC activated on $pcm" >> "$LOGFILE"
        fi
      done
    fi

    # restart run_sox_fifo so the script will select bluealsa or fallback automatically
    if systemctl restart run_sox_fifo.service; then
      logger -t bt-connect-watcher "run_sox_fifo.service restarted"
      echo "$(date -Is) restarted run_sox_fifo.service" >> "$LOGFILE"
    else
      logger -t bt-connect-watcher "failed to restart run_sox_fifo.service"
      echo "$(date -Is) FAILED restart run_sox_fifo.service" >> "$LOGFILE"
    fi

    prev_connected="$connected"
  fi
  sleep 2
done
