#!/bin/bash
# block_other_bt.sh
# Usage: sudo ./block_other_bt.sh <preferred_hci_or_bdaddr>
# Example: sudo ./block_other_bt.sh hci1
# Example: sudo ./block_other_bt.sh AA:BB:CC:DD:EE:FF

set -euo pipefail
if [ "$EUID" -ne 0 ]; then
  echo "This script requires sudo/root." >&2
  exit 2
fi
if [ $# -ne 1 ]; then
  echo "Usage: $0 <preferred_hci_or_bdaddr>" >&2
  exit 2
fi
PREF=$1
STATE_FILE="/tmp/excl_bt_state_$(whoami)"
INTERVAL=5

# Resolve preferred to hciN if a BDADDR was supplied
resolve_hci() {
  arg="$1"
  if [[ "$arg" =~ ^hci[0-9]+$ ]]; then
    echo "$arg"
    return
  fi
  # search hciconfig for BD addr (case-insensitive)
  hciconfig -a 2>/dev/null | awk '/^hci[0-9]+/ {h=$1} /BD Address/ {print h,$3}' | while read h bd; do
    if [ "${bd,,}" = "${arg,,}" ]; then
      echo "$h"
      return
    fi
  done
}

PREF_HCI=$(resolve_hci "$PREF" || true)
if [ -z "$PREF_HCI" ]; then
  echo "Preferred controller '$PREF' not found via hciconfig. Use an hciX name or a BD address." >&2
  echo "Available controllers:" >&2
  hciconfig -a || true
  exit 3
fi

# all known hci controllers
list_hcis() {
  hciconfig -a 2>/dev/null | awk '/^hci[0-9]+/ {print $1}'
}

# prefer btmgmt when available for reliable power off/on
BTMGMT_AVAILABLE=0
if command -v btmgmt >/dev/null 2>&1; then
  BTMGMT_AVAILABLE=1
fi

# check connections on hci
hci_has_conn() {
  hci="$1"
  if [ "$BTMGMT_AVAILABLE" -eq 1 ]; then
    out=$(btmgmt -i "$hci" con 2>/dev/null || true)
    if [ -n "${out//[[:space:]]/}" ]; then
      return 0
    else
      return 1
    fi
  else
    # fallback: check bluetoothctl info for any connected device using this controller
    # this is less reliable but usable if btmgmt missing
    for dev in $(bluetoothctl devices | awk '{print $2}'); do
      if bluetoothctl info "$dev" 2>/dev/null | grep -q "Connected: yes"; then
        return 0
      fi
    done
    return 1
  fi
}

mark_down() {
  hci="$1"
  if [ "$BTMGMT_AVAILABLE" -eq 1 ]; then
    # use btmgmt to power off controller (safer than hciconfig down)
    echo "Powering off $hci via btmgmt"
    btmgmt -i "$hci" power off 2>/dev/null || hciconfig "$hci" down || true
  else
    if hciconfig "$hci" | grep -q "UP"; then
      echo "Bringing $hci down (hciconfig)"
      hciconfig "$hci" down || true
    fi
  fi
}

mark_up() {
  hci="$1"
  if [ "$BTMGMT_AVAILABLE" -eq 1 ]; then
    echo "Powering on $hci via btmgmt"
    btmgmt -i "$hci" power on 2>/dev/null || hciconfig "$hci" up || true
  else
    if ! hciconfig "$hci" | grep -q "UP"; then
      echo "Bringing $hci up (hciconfig)"
      hciconfig "$hci" up || true
    fi
  fi
}

# load previous state
declare -A DOWNED
if [ -f "$STATE_FILE" ]; then
  while read h; do DOWNED[$h]=1; done < "$STATE_FILE" || true
fi

echo "Exclusive BT monitor: preferred=$PREF_HCI interval=${INTERVAL}s"
while true; do
  # get latest controllers
  HCIS=($(list_hcis))
  PREF_CONNECTED=0
  if hci_has_conn "$PREF_HCI"; then
    PREF_CONNECTED=1
  fi

  if [ "$PREF_CONNECTED" -eq 1 ]; then
    # bring down others
    for h in "${HCIS[@]}"; do
      if [ "$h" != "$PREF_HCI" ]; then
        if hciconfig "$h" >/dev/null 2>&1; then
          mark_down "$h"
          DOWNED[$h]=1
        fi
      fi
    done
  else
    # restore any we previously downed
    for h in "${HCIS[@]}"; do
      if [ "$h" != "$PREF_HCI" ] && [ -n "${DOWNED[$h]:-}" ]; then
        mark_up "$h"
        unset DOWNED[$h]
      fi
    done
  fi

  # persist state
  printf "%s\n" "${!DOWNED[@]}" > "$STATE_FILE" || true
  sleep "$INTERVAL"
done
