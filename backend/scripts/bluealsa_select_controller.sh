#!/usr/bin/env bash
set -euo pipefail

find_hci_nodes() {
  gdbus introspect --system --dest org.bluez --object-path /org/bluez 2>/dev/null \
    | awk '/node hci[0-9]+/ { gsub(/[{}]/, "", $2); print $2 }'
}

find_connected_controller() {
  local device_mac device_node hci

  while read -r device_mac; do
    [[ -n "$device_mac" ]] || continue
    device_node="dev_${device_mac//:/_}"

    while read -r hci; do
      [[ -n "$hci" ]] || continue
      if gdbus introspect --system --dest org.bluez --object-path "/org/bluez/${hci}" 2>/dev/null | grep -q "node ${device_node} "; then
        printf '%s\n' "$hci"
        return 0
      fi
    done < <(find_hci_nodes)
  done < <(bluetoothctl devices Connected 2>/dev/null | awk '{print $2}')

  return 1
}

find_default_controller() {
  local default_addr hci

  default_addr=$(bluetoothctl list 2>/dev/null | sed -n 's/^Controller \([^ ]*\).*\[default\]$/\1/p' | head -n1)
  [[ -n "$default_addr" ]] || return 1

  while read -r hci; do
    [[ -n "$hci" ]] || continue
    if gdbus introspect --system --dest org.bluez --object-path "/org/bluez/${hci}" 2>/dev/null | grep -q "readonly s Address = '${default_addr}'"; then
      printf '%s\n' "$hci"
      return 0
    fi
  done < <(find_hci_nodes)

  return 1
}

controller="$(find_connected_controller || true)"

if [[ -z "$controller" ]]; then
  controller="$(find_default_controller || true)"
fi

if [[ -z "$controller" ]]; then
  controller="$(find_hci_nodes | head -n1)"
fi

if [[ -z "$controller" ]]; then
  echo "bluealsa_select_controller: no Bluetooth controller found" >&2
  exit 1
fi

exec /usr/bin/bluealsa -i "$controller" "$@"