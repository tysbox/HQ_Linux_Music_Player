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

echo ""
echo "══════════════════════════════════════════════════════"
echo "[$(date '+%T')] switch_audio.sh  MODE=$MODE  DEVICE=$DEVICE"

# ── BT + Pure の自動フォールバック検出 ─────────────────────────────────────
EFFECTIVE_MODE="$MODE"
if [ "$MODE" == "pure" ] && [[ "$DEVICE" == *bluealsa* ]]; then
    echo "[$(date '+%T')] BT + Pure 検出 → DSP パススルーに自動フォールバック"
    EFFECTIVE_MODE="dsp"
    # YAML_PATH は main.py 側で BT 用パススルー設定として生成済みのものを受け取る
    # （呼び出し元の main.py が bt_fallback=True で generate_camilladsp_yaml を呼ぶ）
fi

# ── ① MPD を一時停止（バッファ書き込みを止める）──────────────────────────
echo "[$(date '+%T')] Step1: mpc pause"
mpc pause > /dev/null 2>&1
sleep 0.3

# ── ② 既存の下流プロセスを停止 ──────────────────────────────────────────────
echo "[$(date '+%T')] Step2: stop downstream processes"

# Pure パススループロセス (arecord | aplay) を停止
if [ -f "$PURE_PID_FILE" ]; then
    OLD_PGID=$(cat "$PURE_PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PGID" ] && kill -0 -- "-$OLD_PGID" 2>/dev/null; then
        kill -- "-$OLD_PGID" 2>/dev/null || true
        sleep 0.3
    fi
    rm -f "$PURE_PID_FILE"
fi

# CamillaDSP を停止
if pgrep -x camilladsp > /dev/null 2>&1; then
    pkill -x camilladsp 2>/dev/null || true
    sleep 0.5
    pkill -9 -x camilladsp 2>/dev/null || true
fi

# loopback-drain を停止（下流プロセスが Loopback capture を開く前に解放）
sudo systemctl stop loopback-drain.service 2>/dev/null || true

# ── ③ ALSAデバイスの解放を最大2秒待つ ─────────────────────────────────────
echo "[$(date '+%T')] Step3: wait for ALSA device release"
for i in $(seq 1 8); do
    if ! pgrep -x camilladsp > /dev/null 2>&1; then break; fi
    sleep 0.25
done

# ── ④ MPD の出力先を切替 ───────────────────────────────────────────────────
echo "[$(date '+%T')] Step4: switch MPD output"

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    # Pure: MPD → デバイス直結（ビットパーフェクト）
    if [[ "$DEVICE" == *bluealsa* ]]; then
        MPD_OUTPUT="Bluetooth"
    elif [[ "$DEVICE" == *hw:1* ]] || [[ "$DEVICE" == *plughw:1* ]] || [[ "$DEVICE" == *PCH* ]]; then
        MPD_OUTPUT="PC Speaker"
    else
        MPD_OUTPUT="USB DAC"
    fi
    echo "[$(date '+%T')] Pure: mpc enable only '$MPD_OUTPUT'"
    mpc enable only "$MPD_OUTPUT" >> "$LOG" 2>&1

elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    # DSP: MPD → ALSA Loopback → CamillaDSP → 出力デバイス
    echo "[$(date '+%T')] DSP: mpc enable only 'ALSA Loopback'"
    mpc enable only "ALSA Loopback" >> "$LOG" 2>&1
fi

sleep 0.3

# ── ⑤ 下流プロセスを起動 ───────────────────────────────────────────────────
echo "[$(date '+%T')] Step5: start downstream"

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    # Pure モード: 下流プロセス不要（MPD がデバイスに直接書く）
    echo "[$(date '+%T')] Pure mode: no downstream process needed"

elif [ "$EFFECTIVE_MODE" == "dsp" ]; then
    # DSP モード: CamillaDSP を起動
    if [ -z "$YAML_PATH" ] || [ ! -f "$YAML_PATH" ]; then
        echo "[$(date '+%T')] ERROR: YAML not found: $YAML_PATH"
        # フォールバック: loopback-drain を再起動して MPD をフリーズさせない
        sudo systemctl start loopback-drain.service 2>/dev/null || true
        exit 1
    fi

    # IR ファイルを /tmp にコピー（初回のみ）
    if [ ! -d /tmp/camilladsp/ir ]; then
        mkdir -p /tmp/camilladsp/ir
        cp ~/.config/camilladsp/ir/*.wav /tmp/camilladsp/ir/ 2>/dev/null || true
    fi

    echo "[$(date '+%T')] Starting CamillaDSP: $YAML_PATH"
    nohup camilladsp -p 1234 "$YAML_PATH" &
    CDSP_PID=$!
    echo "[$(date '+%T')] CamillaDSP PID=$CDSP_PID"

    # CamillaDSP が Loopback capture を開くまで待つ（最大 5 秒）
    CAPTURED=0
    for i in $(seq 1 20); do
        if grep -q "^access:" /proc/asound/Loopback/pcm1c/sub0/hw_params 2>/dev/null; then
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

# ── ⑥ MPD 再生を再開 ───────────────────────────────────────────────────────
sleep 0.2
echo "[$(date '+%T')] Step6: mpc play"
mpc play > /dev/null 2>&1

# ── loopback-drain の起動判定 ───────────────────────────────────────────────
# Loopback capture 側が誰にも開かれていない場合のみ drain を起動。
# Pure モード時は常に drain が必要（MPD が Loopback に書き続けるため）。
sleep 0.5
if [ "$EFFECTIVE_MODE" == "pure" ]; then
    echo "[$(date '+%T')] Pure mode: starting loopback-drain"
    sudo systemctl start loopback-drain.service 2>/dev/null || true
elif ! grep -q "^access:" /proc/asound/Loopback/pcm1c/sub0/hw_params 2>/dev/null; then
    echo "[$(date '+%T')] WARNING: Loopback capture not active → starting loopback-drain"
    sudo systemctl start loopback-drain.service 2>/dev/null || true
else
    echo "[$(date '+%T')] Loopback capture active (drain not needed)"
fi

echo "[$(date '+%T')] switch_audio.sh: complete"
echo "══════════════════════════════════════════════════════"
