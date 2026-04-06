#!/bin/bash
set -euo pipefail

PORT=${1:-6601}
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONF_SRC="$BASE_DIR/config/mpd.conf"
TMP_DIR="/tmp/hq_mpd"
CONF_DST="$TMP_DIR/mpd_${PORT}.conf"

if ! command -v mpd >/dev/null 2>&1; then
  echo "ERROR: mpd command not found. Install MPD before running this script." >&2
  exit 1
fi

mkdir -p "$TMP_DIR/playlists"

sed \
  -e "s#^playlist_directory.*#playlist_directory \"$TMP_DIR/playlists\"#" \
  -e "s#^db_file.*#db_file \"$TMP_DIR/tag_cache\"#" \
  -e "s#^log_file.*#log_file \"$TMP_DIR/mpd.log\"#" \
  -e "s#^state_file.*#state_file \"$TMP_DIR/state\"#" \
  -e "s#^sticker_file.*#sticker_file \"$TMP_DIR/sticker.sql\"#" \
  -e "s#^port.*#port \"$PORT\"#" \
  "$CONF_SRC" > "$CONF_DST"

chmod 700 "$TMP_DIR"

echo "Using MPD config: $CONF_DST"
echo "Starting MPD on port $PORT..."
exec mpd --no-daemon --config "$CONF_DST"
