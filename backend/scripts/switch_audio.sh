#!/bin/bash
# switch_audio.sh — Pure / DSP モード切替スクリプト（状態機械版）
#
# 設計原則:
#   Pure モード : MPD → mpc enable only "USB DAC"|"PC Speaker" → ビットパーフェクト直結
#   DSP モード  : MPD → mpc enable only "ALSA Loopback" → CamillaDSP → 出力デバイス
#   BT + Pure  : BT はビットパーフェクト不可のため DSP パススルーに自動フォールバック
#
#   切替シーケンス（状態機械）:
#     ① mpc pause          書き込みを止める
#     ② stop downstream    下流プロセス (CamillaDSP / passthrough) を停止
#     ③ wait device free   ALSAデバイス解放を確認（最大2秒）
#     ④ mpc enable only X  MPD出力先を切替
#     ⑤ start downstream   新しい下流を起動（DSP時のみ）
#     ⑥ mpc play           再生再開
#
# 使用法: switch_audio.sh <pure|dsp> <device> [yaml_path]

MODE="$1"
DEVICE="$2"
YAML_PATH="$3"

LOG="/tmp/camilladsp/switch_audio.log"
PURE_PID_FILE="/tmp/camilladsp/pure_passthrough.pid"
mkdir -p /tmp/camilladsp
exec >> "$LOG" 2>&1

loopback_drain_ctl() {
    local action="$1"

    if sudo -n /bin/systemctl "$action" loopback-drain.service 2>/dev/null; then
        echo "[$(date '+%T')] loopback-drain: systemctl $action OK"
        return 0
    fi

    echo "[$(date '+%T')] WARNING: loopback-drain systemctl $action skipped (sudoers not configured)"
    return 1
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

log_mpc_state() {
    echo "[$(date '+%T')] MPD outputs:"
    mpc outputs 2>&1 | sed 's/^/    /'
    echo "[$(date '+%T')] MPD status:"
    mpc status 2>&1 | sed 's/^/    /'
}

mpc_normalize_name() {
    local line="$1"
    line="${line#*:}"
    line="${line#${line%%[![:space:]]*}}"
    line="${line%%(*}"
    line="${line%${line##*[![:space:]]}}"
    printf '%s' "$line"
}

find_mpc_output_by_keyword() {
    local keyword="$1"
    mpc outputs 2>/dev/null | while IFS= read -r line; do
        [ -z "$line" ] && continue
        local name
        name=$(mpc_normalize_name "$line")
        if printf '%s\n' "$name" | grep -q -i -F "$keyword"; then
            printf '%s' "$name"
            return 0
        fi
    done
    return 1
}

mpc_enable_only_name() {
    local name="$1"
    [ -z "$name" ] && return 1
    echo "[$(date '+%T')] Trying MPD enable only '$name'"
    if mpc enable only "$name" >> "$LOG" 2>&1; then
        return 0
    fi
    local fallback
    fallback=$(find_mpc_output_by_keyword "$name")
    if [ -n "$fallback" ] && [ "$fallback" != "$name" ]; then
        echo "[$(date '+%T')] Fallback MPD output name '$fallback' for requested '$name'"
        if mpc enable only "$fallback" >> "$LOG" 2>&1; then
            return 0
        fi
    fi
    return 1
}

mpc_disable_all_outputs() {
    local output_ids
    output_ids=$(mpc outputs 2>/dev/null | awk -F: '/^[0-9]+:/ {gsub(/^[ \t]+|[ \t]+$/, "", $1); print $1}')
    if [ -n "$output_ids" ]; then
        echo "[$(date '+%T')] Disabling MPD outputs: $output_ids"
        for id in $output_ids; do
            mpc disable $id 2>/dev/null || true
        done
    else
        echo "[$(date '+%T')] No MPD outputs found to disable"
    fi
}

detect_pure_output_name() {
    local device="$1"
    local usb_card
    local pch_card

    if [[ "$device" == *bluealsa* ]]; then
        echo "Bluetooth"
        return
    fi

    usb_card=$(aplay -l 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /card/ && /USB/ {for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+:$/) {gsub(":", "", $i); print $i; exit}}')
    pch_card=$(aplay -l 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /card/ && (/PCH/ || /CS4208/ || (/HDA/ && $0 !~ /HDMI/)) {for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+:$/) {gsub(":", "", $i); print $i; exit}}')

    if [ -n "$usb_card" ] && [[ "$device" == *"hw:${usb_card},"* || "$device" == *"plughw:${usb_card},"* ]]; then
        echo "USB DAC"
    elif [ -n "$pch_card" ] && [[ "$device" == *"hw:${pch_card},"* || "$device" == *"plughw:${pch_card},"* ]]; then
        echo "PC Speaker"
    elif [[ "$device" == *"hw:"* || "$device" == *"plughw:"* ]]; then
        # If the selected device is a direct ALSA card but doesn't match the known PCH card,
        # prefer USB DAC as the direct Pure output target.
        echo "USB DAC"
    else
        echo "PC Speaker"
    fi
}

echo ""
echo "══════════════════════════════════════════════════════"
echo "[$(date '+%T')] switch_audio.sh  MODE=$MODE  DEVICE=$DEVICE"

EFFECTIVE_MODE="$MODE"
if [ "$MODE" == "pure" ] && [[ "$DEVICE" == *bluealsa* ]]; then
    echo "[$(date '+%T')] BT + Pure 検出 → DSP パススルーに自動フォールバック"
    EFFECTIVE_MODE="dsp"
fi

echo "[$(date '+%T')] Step1: mpc pause"
mpc pause > /dev/null 2>&1
sleep 0.3

echo "[$(date '+%T')] Step2: stop downstream processes"

if [ -f "$PURE_PID_FILE" ]; then
    OLD_PGID=$(cat "$PURE_PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PGID" ] && kill -0 -- "-$OLD_PGID" 2>/dev/null; then
        kill -- "-$OLD_PGID" 2>/dev/null || true
        sleep 0.3
    fi
    rm -f "$PURE_PID_FILE"
fi

if pgrep -x camilladsp > /dev/null 2>&1; then
    pkill -x camilladsp 2>/dev/null || true
    sleep 0.5
    pkill -9 -x camilladsp 2>/dev/null || true
fi

loopback_drain_ctl unmask || true
loopback_drain_ctl stop || true

echo "[$(date '+%T')] Step3: wait for ALSA device release"
for i in $(seq 1 8); do
    if ! pgrep -x camilladsp > /dev/null 2>&1; then break; fi
    sleep 0.25
done

echo "[$(date '+%T')] Step4: switch MPD output"
log_mpc_state >> "$LOG" 2>&1

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    MPD_OUTPUT=$(detect_pure_output_name "$DEVICE")
    mpc_disable_all_outputs >> "$LOG" 2>&1
    echo "[$(date '+%T')] Pure: mpc enable only '$MPD_OUTPUT'"
    if ! mpc_enable_only_name "$MPD_OUTPUT"; then
        echo "[$(date '+%T')] WARNING: Failed to enable pure MPD output '$MPD_OUTPUT'"
    fi
elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    mpc_disable_all_outputs >> "$LOG" 2>&1
    echo "[$(date '+%T')] DSP: mpc enable only 'ALSA Loopback'"
    if ! mpc_enable_only_name "ALSA Loopback"; then
        echo "[$(date '+%T')] WARNING: Failed to enable DSP MPD output 'ALSA Loopback'"
    fi
fi

echo "[$(date '+%T')] After switch:" >> "$LOG" 2>&1
log_mpc_state >> "$LOG" 2>&1
sleep 0.3

echo "[$(date '+%T')] Step5: start downstream"

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    echo "[$(date '+%T')] Pure mode: no downstream process needed"
elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    if [ -z "$YAML_PATH" ] || [ ! -f "$YAML_PATH" ]; then
        echo "[$(date '+%T')] ERROR: YAML not found: $YAML_PATH"
        loopback_drain_ctl start || true
        exit 1
    fi

    loopback_drain_ctl mask || true

    if [ ! -d /tmp/camilladsp/ir ]; then
        mkdir -p /tmp/camilladsp/ir
        cp ~/.config/camilladsp/ir/*.wav /tmp/camilladsp/ir/ 2>/dev/null || true
    fi

    echo "[$(date '+%T')] Starting CamillaDSP: $YAML_PATH"
    nohup camilladsp -p 1234 "$YAML_PATH" &
    CDSP_PID=$!
    echo "[$(date '+%T')] CamillaDSP PID=$CDSP_PID"

    CAPTURED=0
    for i in $(seq 1 20); do
        if loopback_capture_active; then
            echo "[$(date '+%T')] CamillaDSP: Loopback capture confirmed (${i}×0.25s)"
            CAPTURED=1
            break
        fi
        sleep 0.25
    done

    if [ "$CAPTURED" -eq 0 ]; then
        echo "[$(date '+%T')] WARNING: CamillaDSP did not open Loopback in time"
    fi
fi

sleep 0.2
echo "[$(date '+%T')] Step6: mpc play"
mpc play > /dev/null 2>&1

sleep 0.5
if [ "$EFFECTIVE_MODE" == "pure" ]; then
    echo "[$(date '+%T')] Pure mode: loopback-drain not needed"
    loopback_drain_ctl unmask || true
elif ! loopback_capture_active; then
    echo "[$(date '+%T')] WARNING: Loopback capture not active → starting loopback-drain"
    loopback_drain_ctl unmask || true
    loopback_drain_ctl start || true
else
    echo "[$(date '+%T')] Loopback capture active (drain not needed)"
fi

echo "[$(date '+%T')] switch_audio.sh: complete"
echo "══════════════════════════════════════════════════════"