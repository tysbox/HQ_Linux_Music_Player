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

# Step 1: unmask してから止める（DSPモードからの復帰時に mask が残っていても確実に解除）
sudo systemctl unmask loopback-drain.service 2>>"$LOG" || true
sudo systemctl stop loopback-drain.service 2>>"$LOG"

# Step 2: Clean kill
pkill -x camilladsp 2>/dev/null
pkill -x alsaloop 2>/dev/null
pkill -f "/tmp/mpd.fifo" 2>/dev/null
sleep 0.2
pkill -9 -x camilladsp 2>/dev/null
pkill -9 -x alsaloop 2>/dev/null
pkill -9 -f "/tmp/mpd.fifo" 2>/dev/null
sleep 0.3

STARTED=0
if [ "$MODE" == "pure" ]; then
    # Pureモード: デバイスに対応するMPD出力名を選択し直接再生
    # ALSAエイリアス不要・loopback不使用・ビットパーフェクト直結
    # NOTE: BT(bluealsa)はpureモード不可 → バックエンドがDSPに強制変換済みでここには来ない
    if [[ "$DEVICE" == *bluealsa* ]]; then
        OUTPUT_NAME="Bluetooth"
    elif [[ "$DEVICE" == *AUDIO* ]]; then
        OUTPUT_NAME="USB DAC"
    else
        # それ以外のローカルALSAデバイスはPC Speaker出力に割り当てる
        OUTPUT_NAME="PC Speaker"
    fi

    echo "[$(date)] Pure mode: enabling MPD output '$OUTPUT_NAME'" >> "$LOG"
    mpc enable only "$OUTPUT_NAME" >> "$LOG" 2>&1
    sleep 0.5
    mpc play >> "$LOG" 2>&1

    # PC Speaker → ヘッドフォンジャック時はスピーカーをミュート
    if [[ "$OUTPUT_NAME" == "PC Speaker" ]]; then
        JACK_STATE=$(amixer -c 2 cget numid=23 2>/dev/null | grep ": values=" | awk -F= '{print $2}')
        if [ "$JACK_STATE" == "on" ]; then
            amixer -c 2 sset "Speaker" 0% mute >> "$LOG" 2>&1
            amixer -c 2 sset "Headphone" 100% on >> "$LOG" 2>&1
        else
            amixer -c 2 sset "Speaker" 100% on >> "$LOG" 2>&1
            amixer -c 2 sset "Headphone" 0% mute >> "$LOG" 2>&1
        fi
    fi

    STARTED=1
elif [ "$MODE" == "dsp" ]; then
    # DSPモード: MPDの出力をLoopbackに切り替える
    mpc enable only "ALSA Loopback" >>"$LOG" 2>&1

    # Restart=always のドレインが2秒後に自動復帰してpcm1cに割り込まないよう mask する
    sudo systemctl mask loopback-drain.service 2>>"$LOG"

    nohup camilladsp -p 1234 "$YAML_PATH" >>"$LOG" 2>&1 &
    STARTED=1
fi

# DSP モードの場合は drain を起動しない（CamillaDSP が capture を保持するため）
# non-DSP の場合は pcm1c が空いていれば drain を起動する
if [ "$MODE" != "dsp" ]; then
    sleep 1
    if ! grep -q "^access:" /proc/asound/Loopback/pcm1c/sub0/hw_params 2>/dev/null; then
        sudo systemctl start loopback-drain.service 2>>"$LOG"
    fi
fi
