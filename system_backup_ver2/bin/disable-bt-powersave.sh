#!/bin/bash
set -eu
for H in /sys/class/bluetooth/hci*; do
  [ -e "$H" ] || continue
  DEV=$(readlink -f "$H/device")
  CUR="$DEV"
  while [ "$CUR" != "/" ]; do
    if [ -e "$CUR/power/control" ] && [ -e "$CUR/idVendor" ]; then
      if printf "on" > "$CUR/power/control" 2>/dev/null; then
        echo "set $CUR/power/control=on"
      else
        sudo sh -c "echo on > '$CUR/power/control'" 2>/dev/null || true
        echo "(sudo) set $CUR/power/control=on"
      fi
      break
    fi
    CUR=$(dirname "$CUR")
  done
done
