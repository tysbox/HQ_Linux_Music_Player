#!/bin/bash
# Headphone Jack Auto-Switch Watcher
# Front Headphone Jackの接続状態を監視し、Pure/DSPモード両対応で出力切り替えを行う

LOG="/tmp/camilladsp/jack_watcher.log"
STATE_FILE="/tmp/camilladsp/current_state.json"
JACK_NUMID=19  # amixer numid for 'Front Headphone Jack'

mkdir -p /tmp/camilladsp
echo "[$(date)] Jack watcher started" >> "$LOG"

get_jack_state() {
    amixer -c 1 cget numid=$JACK_NUMID 2>/dev/null | grep ": values=" | awk -F= '{print $2}'
}

get_current_mode() {
    if [ -f "$STATE_FILE" ]; then
        python3 -c "import json,sys; d=json.load(open('$STATE_FILE')); print(d.get('mode','pure'))" 2>/dev/null || echo "pure"
    else
        echo "pure"
    fi
}

get_current_device() {
    if [ -f "$STATE_FILE" ]; then
        python3 -c "import json,sys; d=json.load(open('$STATE_FILE')); print(d.get('device','hw:1,0'))" 2>/dev/null || echo "hw:1,0"
    else
        echo "hw:1,0"
    fi
}

on_headphone_plugged() {
    local mode device
    mode=$(get_current_mode)
    device=$(get_current_device)
    echo "[$(date)] Headphone PLUGGED - mode=$mode device=$device" >> "$LOG"

    # ALSA: Headphone ON / Speaker OFF（両モード共通）
    amixer -c 1 sset "Headphone" 100% on >> "$LOG" 2>&1
    amixer -c 1 sset "Speaker" 0% mute >> "$LOG" 2>&1

    if [ "$mode" == "pure" ]; then
        pkill -x aplay 2>/dev/null; sleep 0.3
        [ -p /tmp/mpd.fifo ] || mkfifo /tmp/mpd.fifo
        nohup aplay -D "$device" -f S32_LE -r 192000 -c 2 /tmp/mpd.fifo >> "$LOG" 2>&1 &
        echo "[$(date)] Pure: aplay restarted -> $device" >> "$LOG"
    else
        echo "[$(date)] DSP: ALSA mixer switched to HP, CamillaDSP continues" >> "$LOG"
    fi
}

on_headphone_unplugged() {
    local mode device
    mode=$(get_current_mode)
    device=$(get_current_device)
    echo "[$(date)] Headphone UNPLUGGED - mode=$mode device=$device" >> "$LOG"

    # ALSA: Speaker ON / Headphone OFF（両モード共通）
    amixer -c 1 sset "Speaker" 100% on >> "$LOG" 2>&1
    amixer -c 1 sset "Headphone" 0% mute >> "$LOG" 2>&1

    if [ "$mode" == "pure" ]; then
        pkill -x aplay 2>/dev/null; sleep 0.3
        [ -p /tmp/mpd.fifo ] || mkfifo /tmp/mpd.fifo
        nohup aplay -D "$device" -f S32_LE -r 192000 -c 2 /tmp/mpd.fifo >> "$LOG" 2>&1 &
        echo "[$(date)] Pure: aplay restarted -> $device" >> "$LOG"
    else
        echo "[$(date)] DSP: ALSA mixer switched to Speaker, CamillaDSP continues" >> "$LOG"
    fi
}

# 初回状態取得と適用
PREV_STATE=$(get_jack_state)
echo "[$(date)] Initial jack state: $PREV_STATE" >> "$LOG"
if [ "$PREV_STATE" == "on" ]; then
    amixer -c 1 sset "Headphone" 100% on >> "$LOG" 2>&1
    amixer -c 1 sset "Speaker" 0% mute >> "$LOG" 2>&1
    echo "[$(date)] Init: Headphone ON, Speaker muted" >> "$LOG"
else
    amixer -c 1 sset "Speaker" 100% on >> "$LOG" 2>&1
    amixer -c 1 sset "Headphone" 0% mute >> "$LOG" 2>&1
    echo "[$(date)] Init: Speaker ON, Headphone muted" >> "$LOG"
fi

# メインループ
while true; do
    sleep 1
    CURRENT_STATE=$(get_jack_state)

    if [ "$CURRENT_STATE" != "$PREV_STATE" ]; then
        echo "[$(date)] Jack state changed: $PREV_STATE -> $CURRENT_STATE" >> "$LOG"

        if [ "$CURRENT_STATE" == "on" ]; then
            on_headphone_plugged
        elif [ "$CURRENT_STATE" == "off" ]; then
            on_headphone_unplugged
        fi

        PREV_STATE=$CURRENT_STATE
    fi
done
