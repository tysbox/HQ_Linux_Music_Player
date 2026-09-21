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

loopback_capture_active() {
    for params in /proc/asound/Loopback/pcm1c/sub*/hw_params; do
        [ -f "$params" ] || continue
        if grep -q '^access:' "$params" 2>/dev/null; then
            return 0
        fi
    done
    return 1
}

# Loopback の両側 (MPD 書き込み pcm0p / CamillaDSP 読み出し pcm1c) が
# S32_LE/192000 で一致しているか確認する。
# 背景 (2026-09-21 調査): snd-aloop は相手側と同一フォーマットしか許さない。
# MPD が DSD (.dsf) を DSD_U8/705600 で先に開くと、CamillaDSP の
# S32_LE/192000 キャプチャは hw_params_set_rate/set_format で EINVAL となり
# CamillaDSP が起動直後に死ぬ（たまに無音・不安定になる本体原因）。
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

    # Use pattern that works with both English and Japanese output
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

echo ""
echo "══════════════════════════════════════════════════════"
echo "[$(date '+%T')] switch_audio.sh  MODE=$MODE  DEVICE=$DEVICE"

EFFECTIVE_MODE="$MODE"
if [ "$MODE" == "pure" ] && [[ "$DEVICE" == *bluealsa* ]]; then
    echo "[$(date '+%T')] BT + Pure 検出 → DSP パススルーに自動フォールバック"
    EFFECTIVE_MODE="dsp"
fi

echo "[$(date '+%T')] Step1: mpc pause (ALSA 切替前の安全停止)"
mpc pause > /dev/null 2>&1
# sleep 0.3 → 0.05 に短縮 (2026-09-05: 反応速度改善)

echo "[$(date '+%T')] Step2: stop downstream processes"

if [ -f "$PURE_PID_FILE" ]; then
    OLD_PGID=$(cat "$PURE_PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PGID" ] && kill -0 -- "-$OLD_PGID" 2>/dev/null; then
        kill -- "-$OLD_PGID" 2>/dev/null || true
    fi
    rm -f "$PURE_PID_FILE"
fi

if pgrep -x camilladsp > /dev/null 2>&1; then
    pkill -x camilladsp 2>/dev/null || true
    # sleep 0.5 → 0.2 に短縮
    sleep 0.2
    pkill -9 -x camilladsp 2>/dev/null || true
fi

echo "[$(date '+%T')] Step3: wait for ALSA device release"
for i in $(seq 1 4); do
    if ! pgrep -x camilladsp > /dev/null 2>&1; then break; fi
    sleep 0.25
done

echo "[$(date '+%T')] Step4: switch MPD output"

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    MPD_OUTPUT=$(detect_pure_output_name "$DEVICE")
    mpc disable 1 >> "$LOG" 2>&1
    echo "[$(date '+%T')] Pure: mpc enable only '$MPD_OUTPUT'"
    mpc enable only "$MPD_OUTPUT" >> "$LOG" 2>&1
elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    echo "[$(date '+%T')] DSP: mpc enable only 'ALSA Loopback'"
    mpc enable only "ALSA Loopback" >> "$LOG" 2>&1
fi

sleep 0.3

echo "[$(date '+%T')] Step5: start downstream"

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    echo "[$(date '+%T')] Pure mode: no downstream process needed"
elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    if [ -z "$YAML_PATH" ] || [ ! -f "$YAML_PATH" ]; then
        echo "[$(date '+%T')] ERROR: YAML not found: $YAML_PATH"
        exit 1
    fi

    if [ ! -d /tmp/camilladsp/ir ]; then
        mkdir -p /tmp/camilladsp/ir
        cp ~/.config/camilladsp/ir/*.wav /tmp/camilladsp/ir/ 2>/dev/null || true
    fi

    # Phase 2-B (2026-09-07): --statefile で音量・mute を永続化
    # HANDOVER0907 §2 根治: YAML の devices.state_file_path は CamillaDSP 4.1.3 で削除済み。
    # 代わりに -s/--statefile コマンドラインオプションで指定する。
    STATE_FILE="/tmp/camilladsp/state.yml"
    echo "[$(date '+%T')] Starting CamillaDSP: $YAML_PATH (statefile=$STATE_FILE)"
    nohup camilladsp -p 1234 -s "$STATE_FILE" "$YAML_PATH" &
    CDSP_PID=$!
    echo "[$(date '+%T')] CamillaDSP PID=$CDSP_PID"

    CAPTURED=0
    for i in $(seq 1 20); do
        if loopback_capture_active; then
            echo "[$(date '+%T')] CamillaDSP: Loopback capture confirmed (${i}×0.25s)"
            CAPTURED=1
            break
        fi
        if ! kill -0 "$CDSP_PID" 2>/dev/null; then
            echo "[$(date '+%T')] CamillaDSP died before opening Loopback (PID=$CDSP_PID gone)"
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

sleep 1.0
if [ "$EFFECTIVE_MODE" == "dsp" ]; then
    # Format 競合チェック (2026-09-21): MPD が DSD_U8/705600 等で開いた場合、
    # CamillaDSP はキャプチャを S32_LE/192000 で開けず死んでいるはず。
    # → loopback を解放させて CamillaDSP を起動し直す (最大1回リトライ)。
    if loopback_capture_active && ! loopback_params_ok; then
        echo "[$(date '+%T')] WARNING: Loopback params mismatch (MPD native format?) — reopening MPD output in S32_LE/192000"
        mpc pause > /dev/null 2>&1
        sleep 0.3
        if pgrep -x camilladsp > /dev/null 2>&1; then
            pkill -x camilladsp > /dev/null 2>&1 || true
            sleep 0.3
        fi
        if [ -f "$YAML_PATH" ]; then
            nohup camilladsp -p 1234 -s "$STATE_FILE" "$YAML_PATH" &
            echo "[$(date '+%T')] CamillaDSP restarted PID=$!"
            for i in $(seq 1 20); do
                if loopback_capture_active && loopback_params_ok; then
                    echo "[$(date '+%T')] CamillaDSP: Loopback params confirmed S32_LE/192000 (${i}×0.25s)"
                    break
                fi
                if ! pgrep -x camilladsp > /dev/null 2>&1; then
                    echo "[$(date '+%T')] CamillaDSP died during restart wait"
                    break
                fi
                sleep 0.25
            done
            mpc play > /dev/null 2>&1
            sleep 0.5
        fi
    fi
fi

sleep 0.2
if [ "$EFFECTIVE_MODE" == "pure" ]; then
    echo "[$(date '+%T')] Pure mode: loopback-drain not needed"
elif ! loopback_capture_active; then
    echo "[$(date '+%T')] WARNING: Loopback capture not active (drain disabled)"
elif ! loopback_params_ok; then
    echo "[$(date '+%T')] WARNING: Loopback params are NOT S32_LE/192000 (check /proc/asound/Loopback/pcm*/sub0/hw_params)"
else
    echo "[$(date '+%T')] Loopback capture active S32_LE/192000 (drain not needed)"
fi

echo "[$(date '+%T')] switch_audio.sh: complete"
echo "══════════════════════════════════════════════════════"