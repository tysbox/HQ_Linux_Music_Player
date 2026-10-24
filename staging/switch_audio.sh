#!/bin/bash
# switch_audio.sh — Pure / DSP モード切替スクリプト（Root Fix B: systemd 委譲版）
#
# 設計原則:
#   Pure モード : MPD → mpc enable only "USB DAC"|"PC Speaker" → ビットパーフェクト直結
#   DSP モード  : MPD → mpc enable only "ALSA Loopback" → CamillaDSP → 出力デバイス
#   BT + Pure  : BT はビットパーフェクト不可のため DSP パススルーに自動フォールバック
#
#   切替シーケンス（状態機械）:
#     ① mpc pause          書き込みを止める
#     ② stop downstream    下流プロセス (CamillaDSP / passthrough) を停止 → systemctl stop
#     ③ wait device free   ALSAデバイス解放を確認（最大2秒）
#     ④ mpc enable only X  MPD出力先を切替
#     ⑤ start downstream   新しい下流を起動 → systemctl reload-or-restart (DSP時のみ)
#     ⑥ mpc play           再生再開
#
# 使用法: switch_audio.sh <pure|dsp> <device> [yaml_path]
#
# Root Fix B (2026-10-03):
#   CamillaDSP の起動・停止・再起動を systemd に完全委譲。
#   - nohup camilladsp & を廃止し、systemctl reload-or-restart camilladsp に置換
#   - Type=notify で camilladsp の ready 通知を systemd が受信
#   - 孤児プロセス・RT喪失・再起動ループを根絶

set -euo pipefail

MODE="$1"
DEVICE="$2"
YAML_PATH="$3"

# 環境変数でパスを上書き可能（Single Source: backend/dsp/paths.py）
CAMILLA_STATE_DIR="${CAMILLA_STATE_DIR:-/var/lib/camilladsp}"
CAMILLA_STATE_FILE="${CAMILLA_STATE_FILE:-/var/lib/camilladsp/state.yml}"

LOG="${CAMILLA_STATE_DIR}/switch_audio.log"
PURE_PID_FILE="${CAMILLA_STATE_DIR}/pure_passthrough.pid"
mkdir -p "${CAMILLA_STATE_DIR}"
exec >> "$LOG" 2>&1
logger -t switch_audio "MODE=$MODE DEVICE=$DEVICE YAML=$YAML_PATH STATE_DIR=$CAMILLA_STATE_DIR"

log() {
    echo "[$(date '+%T')] $*"
}

loopback_capture_active() {
    for params in /proc/asound/Loopback/pcm1c/sub*/hw_params; do
        [ -f "$params" ] || continue
        if grep -q '^access:' "$params" 2>/dev/null; then
            return 0
        fi
    done
    return 1
}

loopback_params_ok() {
    local f
    for f in /proc/asound/Loopback/pcm0p/sub0/hw_params /proc/asound/Loopback/pcm1c/sub0/hw_params; do
        [ -r "$f" ] || return 1
        grep -q '^format: S32_LE' "$f" 2>/dev/null || return 1
        grep -q '^rate: 192000 ' "$f" 2>/dev/null || return 1
    done
    return 0
}


detect_pure_output_name() {
    local device="$1"
    local usb_card
    local pch_card

    if [[ "$device" == *bluealsa* ]]; then
        echo "Bluetooth"
        return
    fi

    usb_card=$(aplay -l 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /AUDIO.*USB|USB.*AUDIO/ {for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+:$/) {gsub(":", "", $i); print $i; exit}}')
    pch_card=$(aplay -l 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /PCH|CS4208|HDA/ && !/HDMI/ {for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+:$/) {gsub(":", "", $i); print $i; exit}}')

    if [ -n "$usb_card" ] && [[ "$device" == *"hw:${usb_card},"* || "$device" == *"plughw:${usb_card},"* ]]; then
        echo "USB DAC"
    elif [ -n "$pch_card" ] && [[ "$device" == *"hw:${pch_card},"* || "$device" == *"plughw:${pch_card},"* ]]; then
        echo "PC Speaker"
    else
        echo "PC Speaker"
    fi
}

stop_downstream() {
    local mode="$1"
    log "Step2: stop downstream processes (mode=$mode)"

    if [ "$mode" == "pure" ]; then
        if [ -f "$PURE_PID_FILE" ]; then
            OLD_PGID=$(cat "$PURE_PID_FILE" 2>/dev/null)
            if [ -n "$OLD_PGID" ] && kill -0 -- "-$OLD_PGID" 2>/dev/null; then
                kill -- "-$OLD_PGID" 2>/dev/null || true
            fi
            rm -f "$PURE_PID_FILE"
        fi
    fi

    if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
        log "Stopping camilladsp via systemctl..."
        systemctl stop camilladsp.service
        for i in $(seq 1 50); do
            if ! systemctl is-active --quiet camilladsp.service 2>/dev/null; then
                break
            fi
            sleep 0.1
        done
        log "camilladsp stopped"
    else
        if pgrep -x camilladsp > /dev/null 2>&1; then
            log "Killing orphaned camilladsp processes..."
            pkill -x camilladsp 2>/dev/null || true
            sleep 0.3
        fi
    fi
}


start_downstream() {
    local mode="$1"
    local yaml_path="$2"
    log "Step5: start downstream (mode=$mode)"

    if [ "$mode" == "pure" ]; then
        log "Pure mode: no downstream process needed"
        return 0
    fi

    if [ -z "$yaml_path" ] || [ ! -f "$yaml_path" ]; then
        log "ERROR: YAML not found: $yaml_path"
        return 1
    fi

    if [ ! -d "${CAMILLA_STATE_DIR}/ir" ]; then
        mkdir -p "${CAMILLA_STATE_DIR}/ir"
        cp ~/.config/camilladsp/ir/*.wav "${CAMILLA_STATE_DIR}/ir/" 2>/dev/null || true
    fi

    log "Starting CamillaDSP via systemctl: $yaml_path (statefile=$CAMILLA_STATE_FILE)"

    if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
        log "Reloading camilladsp with new YAML..."
        systemctl reload camilladsp.service
    else
        log "Starting camilladsp..."
        systemctl start camilladsp.service
    fi

    local ready=0
    for i in $(seq 1 100); do
        if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
            ready=1
            break
        fi
        sleep 0.1
    done

    if [ "$ready" -eq 0 ]; then
        log "WARNING: camilladsp did not become active in time"
        return 1
    fi

    local captured=0
    for i in $(seq 1 20); do
        if loopback_capture_active; then
            log "CamillaDSP: Loopback capture confirmed (${i}x0.25s)"
            captured=1
            break
        fi
        if ! systemctl is-active --quiet camilladsp.service 2>/dev/null; then
            log "CamillaDSP died unexpectedly"
            return 1
        fi
        sleep 0.25
    done

    if [ "$captured" -eq 0 ]; then
        log "WARNING: CamillaDSP did not open Loopback in time"
        return 1
    fi

    log "CamillaDSP started successfully"
    return 0
}


start_pure_passthrough() {
    local device="$1"
    log "Starting pure passthrough for $device"

    if [ -f "$PURE_PID_FILE" ]; then
        OLD_PGID=$(cat "$PURE_PID_FILE" 2>/dev/null)
        if [ -n "$OLD_PGID" ] && kill -0 -- "-$OLD_PGID" 2>/dev/null; then
            kill -- "-$OLD_PGID" 2>/dev/null || true
        fi
        rm -f "$PURE_PID_FILE"
    fi

    setsid alsaloop -C hw:Loopback,0,0 -P "$device" -f S32_LE -r 192000 -g 100 >/dev/null 2>&1 &
    local pgid=$!
    echo "$pgid" > "$PURE_PID_FILE"
    log "Pure passthrough started (PGID=$pgid)"
}

# ── メイン処理 ────────────────────────────────────────────────

MODE="$1"
DEVICE="$2"
YAML_PATH="$3"

CAMILLA_STATE_DIR="${CAMILLA_STATE_DIR:-/var/lib/camilladsp}"
CAMILLA_STATE_FILE="${CAMILLA_STATE_FILE:-/var/lib/camilladsp/state.yml}"

LOG="${CAMILLA_STATE_DIR}/switch_audio.log"
PURE_PID_FILE="${CAMILLA_STATE_DIR}/pure_passthrough.pid"
mkdir -p "${CAMILLA_STATE_DIR}"
exec >> "$LOG" 2>&1
logger -t switch_audio "MODE=$MODE DEVICE=$DEVICE YAML=$YAML_PATH STATE_DIR=$CAMILLA_STATE_DIR"

EFFECTIVE_MODE="$MODE"
if [ "$MODE" == "pure" ] && [[ "$DEVICE" == *bluealsa* ]]; then
    log "BT + Pure 検出 → DSP パススルーに自動フォールバック"
    EFFECTIVE_MODE="dsp"
fi

log "Step1: mpc pause (ALSA 切替前の安全停止)"
mpc pause > /dev/null 2>&1

stop_downstream "$EFFECTIVE_MODE"

for i in $(seq 1 20); do
    if ! loopback_capture_active; then
        break
    fi
    sleep 0.1
done

log "Step4: mpc enable only (出力切替)"
PURE_OUTPUT_NAME=$(detect_pure_output_name "$DEVICE")
log "Effective output: $PURE_OUTPUT_NAME"
mpc enable only "$PURE_OUTPUT_NAME" > /dev/null 2>&1

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    start_pure_passthrough "$DEVICE"
else
    if ! start_downstream "$EFFECTIVE_MODE" "$YAML_PATH"; then
        log "ERROR: Failed to start downstream"
        exit 1
    fi
fi

sleep 0.2
log "Step6: mpc play"
mpc play > /dev/null 2>&1

sleep 1.0

if [ "$EFFECTIVE_MODE" == "dsp" ]; then
    if loopback_capture_active && ! loopback_params_ok; then
        log "WARNING: Loopback params mismatch (MPD native format?) — reopening MPD output in S32_LE/192000"
        mpc pause > /dev/null 2>&1
        sleep 0.3
        if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
            systemctl restart camilladsp.service
            sleep 0.3
        fi
        if [ -f "$YAML_PATH" ]; then
            start_downstream "dsp" "$YAML_PATH"
        fi
        mpc play > /dev/null 2>&1
        sleep 0.5
    fi
fi

sleep 0.2
if [ "$EFFECTIVE_MODE" == "pure" ]; then
    log "Pure mode: loopback-drain not needed"
elif ! loopback_capture_active; then
    log "WARNING: Loopback capture not active"
elif ! loopback_params_ok; then
    log "WARNING: Loopback params are NOT S32_LE/192000 (check /proc/asound/Loopback/pcm*/sub0/hw_params)"
else
    log "Loopback capture active S32_LE/192000"
fi

log "switch_audio.sh: complete"
log "═══════════════════════════════════════════════════════"

