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

# MPD接続設定 — /etc/mpd.conf の port と一致させること
MPD_HOST="${MPD_HOST:-127.0.0.1}"
MPD_PORT="${MPD_PORT:-6601}"
MPC="mpc -h $MPD_HOST -p $MPD_PORT"

LOG="/tmp/camilladsp/switch_audio.log"
PURE_PID_FILE="/tmp/camilladsp/pure_passthrough.pid"
mkdir -p /tmp/camilladsp
exec >> "$LOG" 2>&1

loopback_capture_active() {
    for params in /proc/asound/Loopback/pcm1c/sub*/hw_params; do
        [ -f "$params" ] || continue
        if grep -q '^access:' "$params" 2>/dev/null; then
            return 0
        fi
    done
    return 1
}

detect_pure_output_name() {
    local device="$1"
    local usb_card
    local pch_card

    if [[ "$device" == *bluealsa* ]]; then
        echo "Bluetooth"
        return
    fi

    # LANG=C で英語出力を強制（日本語ロケールだと "カード" になり /card/ マッチ失敗するため）
    usb_card=$(LANG=C aplay -l 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /card/ && /USB/ {for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+:$/) {gsub(":", "", $i); print $i; exit}}')
    pch_card=$(LANG=C aplay -l 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /card/ && (/PCH/ || /CS4208/ || (/HDA/ && $0 !~ /HDMI/)) {for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+:$/) {gsub(":", "", $i); print $i; exit}}')

    if [ -n "$usb_card" ] && [[ "$device" == *"hw:${usb_card},"* || "$device" == *"plughw:${usb_card},"* ]]; then
        echo "USB DAC"
    elif [ -n "$pch_card" ] && [[ "$device" == *"hw:${pch_card},"* || "$device" == *"plughw:${pch_card},"* ]]; then
        echo "PC Speaker"
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
$MPC pause > /dev/null 2>&1
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

sudo systemctl unmask loopback-drain.service 2>/dev/null || true
sudo systemctl stop loopback-drain.service 2>/dev/null || true

echo "[$(date '+%T')] Step3: wait for ALSA device release"
for i in $(seq 1 8); do
    if ! pgrep -x camilladsp > /dev/null 2>&1; then break; fi
    sleep 0.25
done

echo "[$(date '+%T')] Step4: switch MPD output"

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    MPD_OUTPUT=$(detect_pure_output_name "$DEVICE")
    $MPC disable 1 >> "$LOG" 2>&1
    echo "[$(date '+%T')] Pure: mpc enable only '$MPD_OUTPUT'"
    $MPC enable only "$MPD_OUTPUT" >> "$LOG" 2>&1
elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    echo "[$(date '+%T')] DSP: mpc enable only 'ALSA Loopback'"
    $MPC enable only "ALSA Loopback" >> "$LOG" 2>&1
fi

sleep 0.3

echo "[$(date '+%T')] Step5: start downstream"

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    echo "[$(date '+%T')] Pure mode: no downstream process needed"
elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    if [ -z "$YAML_PATH" ] || [ ! -f "$YAML_PATH" ]; then
        echo "[$(date '+%T')] ERROR: YAML not found: $YAML_PATH"
        sudo systemctl start loopback-drain.service 2>/dev/null || true
        exit 1
    fi

    sudo systemctl mask loopback-drain.service 2>/dev/null || true

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
$MPC play > /dev/null 2>&1

sleep 0.5
if [ "$EFFECTIVE_MODE" == "pure" ]; then
    echo "[$(date '+%T')] Pure mode: loopback-drain not needed"
    sudo systemctl unmask loopback-drain.service 2>/dev/null || true
elif ! loopback_capture_active; then
    echo "[$(date '+%T')] WARNING: Loopback capture not active → starting loopback-drain"
    sudo systemctl unmask loopback-drain.service 2>/dev/null || true
    sudo systemctl start loopback-drain.service 2>/dev/null || true
else
    echo "[$(date '+%T')] Loopback capture active (drain not needed)"
fi

echo "[$(date '+%T')] switch_audio.sh: complete"
echo "══════════════════════════════════════════════════════"