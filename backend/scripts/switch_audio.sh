#!/bin/bash
MODE=$1
DEVICE=$2
YAML_PATH=$3

LOG="/tmp/camilladsp/switch_audio.log"
mkdir -p /tmp/camilladsp
echo "[$(date)] switch_audio.sh called: MODE=$MODE DEVICE=$DEVICE YAML=$YAML_PATH" >> "$LOG"

if [ ! -d /tmp/camilladsp/ir ]; then
    mkdir -p /tmp/camilladsp/ir
    cp ~/.config/camilladsp/ir/*.wav /tmp/camilladsp/ir/ 2>/dev/null || true
fi

# Step 1: Stop drain
sudo systemctl stop loopback-drain.service 2>>"$LOG"

# Step 2: Clean kill
pkill -x camilladsp 2>/dev/null
pkill -x alsaloop 2>/dev/null
sleep 0.2
pkill -9 -x camilladsp 2>/dev/null
pkill -9 -x alsaloop 2>/dev/null
sleep 0.3

STARTED=0
if [ "$MODE" == "pure" ]; then
    # Pureモード: デバイスに対応するMPD出力名を選択し直接再生
    # ALSAエイリアス不要・loopback不使用・ビットパーフェクト直結
    if [[ "$DEVICE" == *bluealsa* ]]; then
        OUTPUT_NAME="Bluetooth"
    elif [[ "$DEVICE" == *hw:1* || "$DEVICE" == *plughw:1* ]]; then
        OUTPUT_NAME="PC Speakers"
    else
        # hw:2,0 / plughw:2,0 / その他 → USB DAC
        OUTPUT_NAME="USB DAC"
    fi

    echo "[$(date)] Pure mode: enabling MPD output '$OUTPUT_NAME'" >> "$LOG"
    mpc enable only "$OUTPUT_NAME" >> "$LOG" 2>&1

    STARTED=1
elif [ "$MODE" == "dsp" ]; then
    # DSPモード: MPDの出力をLoopbackに切り替える
    mpc enable only "ALSA Loopback" >>"$LOG" 2>&1

    nohup camilladsp -p 1234 "$YAML_PATH" >>"$LOG" 2>&1 &
    STARTED=1
fi

sleep 1
if ! grep -q "^access:" /proc/asound/Loopback/pcm1c/sub0/hw_params 2>/dev/null; then
    sudo systemctl start loopback-drain.service 2>>"$LOG"
fi
