#!/bin/bash
# switch_audio.sh — Pure / DSP モード切替スクリプト（無停止切替版 2026-10-03）
#
# 設計原則:
#   DSP→DSP  : MPD出力 (ALSA Loopback) は不変。pause/play しない。
#              CamillaDSP は WebSocket (SetConfigFilePath + Reload) で
#              YAML をホットリロード → 出力デバイス切替 (USB/PCH/BT) が
#              音途切れなし・sudo 不要で完結する。
#   →Pure    : MPD出力を USB DAC / PC Speaker へ。CamillaDSP は WS Stop で
#              ALSA デバイスを解放する (systemctl stop は sudo 要のため
#              フォールバック扱い。プロセスは生存するため再起動ループなし)。
#   Pure→DSP : MPD出力を ALSA Loopback へ。CamillaDSP 稼働中なら WS リロード、
#              停止中なら systemctl start を試行 (要sudo、失敗時はログのみ)。
#   BT + Pure : BT はビットパーフェクト不可のため DSP パススルーに自動フォールバック。
#
# 使用法: switch_audio.sh <pure|dsp> <device> [yaml_path]
#
# 重要:
#   - 本スクリプトは last_config.json を書き込まない。設定の永続化は
#     hq_api (backend.dsp.state_manager.save_last_config) のみが行う。
#     (旧版がハードコード値で上書きし、ダイヤル設定が勝手にリセットされる
#      事故の根治。二重書き込みレースも同時に解消)
#   - パスは backend/dsp/paths.py と同一の環境変数・既定値 (単一ソース)。

set -euo pipefail

CAMILLA_STATE_DIR="${CAMILLA_STATE_DIR:-/var/lib/camilladsp}"
CAMILLA_STATE_FILE="${CAMILLA_STATE_FILE:-/var/lib/camilladsp/state.yml}"
CAMILLA_HOST="${CAMILLA_HOST:-127.0.0.1}"
CAMILLA_PORT="${CAMILLA_PORT:-1234}"

LOG="${CAMILLA_STATE_DIR}/switch_audio.log"
PURE_PID_FILE="${CAMILLA_STATE_DIR}/pure_passthrough.pid"
mkdir -p "${CAMILLA_STATE_DIR}"
exec >> "$LOG" 2>&1

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

# ── Phase 3 (bisen-dspd): Tube/Restore デーモンの経路解放 ──────────────
# pure モードでは MPD が直接 DAC を開くため、bisen-dspd が routing 中
# (DAC 所有中) だと出力を開けない。先に解放してからモード切替する。
# dsp モードの routing 確保は hq_api (backend.dsp.bisen_daemon) が
# オーケストレーションするため、本スクリプトは解放のみ担当 (単一責務)。
bisen_release() {
    local sock="${BISEN_DPD_SOCKET:-/run/bisen-dspd/control.sock}"
    [ -S "$sock" ] || { log "bisen-dspd socket absent — skip release"; return 0; }
    python3 - "$sock" <<'PYEOF'
import socket, sys, time

sock_path = sys.argv[1]

def cmd(c):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(sock_path)
        s.sendall((c + "\n").encode())
        r = s.recv(4096).decode().strip()
        s.close()
        return r
    except Exception:
        return None

if cmd("ping") == "pong":
    cmd("set routing 0")
    for _ in range(40):  # 最大 4s 待機
        r = cmd("get params") or ""
        if "routing=0" in r and "playback_open=0" in r:
            print("BISEN_RELEASED")
            break
        time.sleep(0.1)
    else:
        print("BISEN_RELEASE_TIMEOUT")
else:
    print("BISEN_DAEMON_DOWN")
PYEOF
    log "bisen-dspd routing released (pure mode)"
}

# ── WebSocket ヘルパー (sudo 不要の CamillaDSP 操作) ─────────────

ws_reload_yaml() {
    # CamillaDSP に設定ファイルパスを渡してホットリロードする。
    # camilladsp 4.1.3 の python lib に reload_config は無いため general.reload を使う。
    local yaml_path="$1"
    python3 -c "
import sys
from camilladsp import CamillaClient
c = CamillaClient('${CAMILLA_HOST}', ${CAMILLA_PORT})
try:
    c.connect()
    c.config.set_file_path('${yaml_path}')
    c.general.reload()
    print('WS_RELOAD_OK')
except Exception as e:
    print('WS_RELOAD_FAIL: %s' % e, file=sys.stderr)
    sys.exit(1)
finally:
    try:
        c.disconnect()
    except Exception:
        pass
" 2>&1
}

ws_stop_dsp() {
    # CamillaDSP の処理を停止して ALSA デバイスを解放する (プロセスは生存)。
    python3 -c "
import sys
from camilladsp import CamillaClient
c = CamillaClient('${CAMILLA_HOST}', ${CAMILLA_PORT})
try:
    c.connect()
    c.general.stop()
    print('WS_STOP_OK')
except Exception as e:
    print('WS_STOP_FAIL: %s' % e, file=sys.stderr)
    sys.exit(1)
finally:
    try:
        c.disconnect()
    except Exception:
        pass
" 2>&1
}

# ── デバイス検出 ───────────────────────────────────────────────

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

# ── 下流プロセス制御 ──────────────────────────────────────────

stop_downstream() {
    local mode="$1"
    log "Step2: downstream control (mode=$mode)"

    # Pure 遷移時のみ CamillaDSP を停止 (デバイス解放) する。
    # DSP→DSP は停止しない (Step5 で WS ホットリロード)。
    if [ "$mode" != "pure" ]; then
        if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
            log "DSP mode: keep CamillaDSP running (hot-reload in Step5)"
        else
            log "DSP mode: CamillaDSP not running (Step5 will try to start)"
        fi
        return 0
    fi

    # Pure: 旧 pure passthrough を停止
    if [ -f "$PURE_PID_FILE" ]; then
        OLD_PGID=$(cat "$PURE_PID_FILE" 2>/dev/null)
        if [ -n "$OLD_PGID" ] && kill -0 -- "-$OLD_PGID" 2>/dev/null; then
            kill -- "-$OLD_PGID" 2>/dev/null || true
        fi
        rm -f "$PURE_PID_FILE"
    fi

    # Pure: CamillaDSP を停止して ALSA デバイスを解放。
    # 第一手段は WS Stop (sudo 不要・プロセス生存で再起動ループなし)。
    # フォールバックの systemctl stop は hq-api 実行ユーザーには
    # 権限が無い場合があるため、失敗しても致命扱いにしない。
    if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
        if ws_stop_dsp | grep -q 'WS_STOP_OK'; then
            log "CamillaDSP: WS stop OK (devices released, process alive)"
        else
            log "WARNING: WS stop failed; trying systemctl stop (may need sudo)"
            systemctl stop camilladsp.service 2>/dev/null || \
            sudo systemctl stop camilladsp.service 2>/dev/null || \
            log "WARNING: could not stop camilladsp — continuing (MPD switches away anyway)"
        fi
        sleep 0.2
    fi

    # 孤立プロセス掃除 (systemd 管理外の残骸)
    if pgrep -x camilladsp > /dev/null 2>&1 && ! systemctl is-active --quiet camilladsp.service 2>/dev/null; then
        log "Killing orphaned camilladsp processes..."
        pkill -x camilladsp 2>/dev/null || true
        sleep 0.3
    fi
    return 0
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

    if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
        # 稼働中: WS ホットリロード (停止なし・sudo 不要)
        log "Hot-reloading CamillaDSP via websocket: $yaml_path"
        if ws_reload_yaml "$yaml_path" | grep -q 'WS_RELOAD_OK'; then
            log "CamillaDSP reloaded (hot)"
        else
            log "WARNING: WS reload failed; trying systemctl reload-or-restart"
            systemctl reload-or-restart camilladsp.service 2>/dev/null || \
            sudo systemctl reload-or-restart camilladsp.service 2>/dev/null || {
                log "ERROR: hot-reload and systemctl both failed"
                return 1
            }
        fi
    else
        # 停止中: 起動を試みる (要 sudo。失敗時は systemd の自動復帰に委ねる)
        log "CamillaDSP not active; trying systemctl start"
        if ! (systemctl start camilladsp.service 2>/dev/null || \
              sudo systemctl start camilladsp.service 2>/dev/null); then
            log "ERROR: cannot start camilladsp without sudo"
            return 1
        fi
        local started=0
        for i in $(seq 1 100); do
            if systemctl is-active --quiet camilladsp.service 2>/dev/null; then
                started=1
                break
            fi
            sleep 0.1
        done
        if [ "$started" -eq 0 ]; then
            log "WARNING: camilladsp did not become active in time"
            return 1
        fi
    fi

    # 処理開始 (Loopback capture オープン) 待ち — ホットリロード時は即完了
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

    log "CamillaDSP ready"
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

logger -t switch_audio "MODE=$MODE DEVICE=$DEVICE YAML=$YAML_PATH STATE_DIR=$CAMILLA_STATE_DIR"

EFFECTIVE_MODE="$MODE"
if [ "$MODE" == "pure" ] && [[ "$DEVICE" == *bluealsa* ]]; then
    log "BT + Pure 検出 → DSP パススルーに自動フォールバック"
    EFFECTIVE_MODE="dsp"
fi

# DSP→DSP では MPD 出力 (ALSA Loopback) が変わらないため、
# pause/play とデバイス解放待ちをスキップし、再生を途切れさせない。
SKIP_PAUSE=0
if [ "$EFFECTIVE_MODE" == "dsp" ]; then
    LAST_MODE=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/audiophile/last_config.json'))).get('mode',''))" 2>/dev/null || echo "")
    if [ "$LAST_MODE" == "dsp" ]; then
        SKIP_PAUSE=1
        log "DSP->DSP: hot switch (skip pause/play, skip device-free wait)"
    fi
fi

if [ "$SKIP_PAUSE" -eq 0 ]; then
    log "Step1: mpc pause (ALSA 切替前の安全停止)"
    mpc pause > /dev/null 2>&1 || log "WARNING: mpc pause failed"
fi

# Phase 3: pure 切替時は bisen-dspd の DAC 所有を先に解放する
if [ "$EFFECTIVE_MODE" == "pure" ]; then
    bisen_release
fi

stop_downstream "$EFFECTIVE_MODE"

if [ "$SKIP_PAUSE" -eq 0 ]; then
    for i in $(seq 1 20); do
        if ! loopback_capture_active; then
            break
        fi
        sleep 0.1
    done
fi

log "Step4: mpc enable only (出力切替)"
if [ "$EFFECTIVE_MODE" == "dsp" ]; then
    # DSP モード: MPD は常に ALSA Loopback へ。
    # 出力デバイス (USB/PCH/BT) の切替は CamillaDSP の YAML が担う。
    # (旧バグ: DSP 時にデバイス名を MPD 出力へ enable していたため
    #  BT/USB 切替が不能・無音化していた)
    log "DSP mode: MPD output -> ALSA Loopback (device switch = CamillaDSP YAML)"
    mpc enable only "ALSA Loopback" > /dev/null 2>&1 || \
    mpc enable "ALSA Loopback" > /dev/null 2>&1 || \
    log "WARNING: mpc enable ALSA Loopback failed"
else
    PURE_OUTPUT_NAME=$(detect_pure_output_name "$DEVICE")
    log "Effective output: $PURE_OUTPUT_NAME"
    mpc enable only "$PURE_OUTPUT_NAME" > /dev/null 2>&1 || log "WARNING: mpc enable $PURE_OUTPUT_NAME failed"
fi

if [ "$EFFECTIVE_MODE" == "pure" ]; then
    start_pure_passthrough "$DEVICE"
else
    if ! start_downstream "$EFFECTIVE_MODE" "$YAML_PATH"; then
        log "ERROR: Failed to start downstream"
        exit 1
    fi
fi

if [ "$SKIP_PAUSE" -eq 0 ]; then
    sleep 0.2
    log "Step6: mpc play"
    mpc play > /dev/null 2>&1 || log "WARNING: mpc play failed"

    sleep 1.0

    # Loopback フォーマット不一致 (MPD ネイティブ形式) の是正 — 冷間切替時のみ
    if [ "$EFFECTIVE_MODE" == "dsp" ]; then
        if loopback_capture_active && ! loopback_params_ok; then
            log "WARNING: Loopback params mismatch — reopening MPD output in S32_LE/192000"
            mpc pause > /dev/null 2>&1 || true
            sleep 0.3
            if [ -f "$YAML_PATH" ]; then
                start_downstream "dsp" "$YAML_PATH" || true
            fi
            mpc play > /dev/null 2>&1 || true
            sleep 0.5
        fi
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

log "switch_audio.sh: complete (mode=$EFFECTIVE_MODE device=$DEVICE)"
log "═══════════════════════════════════════════════════════"
