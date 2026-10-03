#!/bin/bash
# Root Fix B 検証スクリプト
set -euo pipefail
LOG=/var/log/verify_root_fix_$(date +%Y%m%d_%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
echo "=== Root Fix B 検証開始: $(date) ==="
echo
1. systemd unit ファイル確認
if [ -f /etc/systemd/system/camilladsp.service ]; then
    echo "  ✅ /etc/systemd/system/camilladsp.service 存在"
    if grep -q 'Type=notify' /etc/systemd/system/camilladsp.service; then
        echo "  ✅ Type=notify 設定済み"
    else
        echo "  ❌ Type=notify 未設定"
        exit 1
    fi
    if grep -q '--notify' /etc/systemd/system/camilladsp.service; then
        echo "  ✅ ExecStart に --notify あり"
    else
        echo "  ❌ ExecStart に --notify なし"
        exit 1
    fi
    if grep -q 'Restart=always' /etc/systemd/system/camilladsp.service; then
        echo "  ✅ Restart=always 設定済み"
    else
        echo "  ❌ Restart=always なし"
        exit 1
    fi
else
    echo "  ❌ camilladsp.service が見つからない"
    exit 1
fi
echo
2. switch_audio.sh 確認
if [ -f /home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh ]; then
    if grep -q 'systemctl reload\|systemctl restart\|systemctl start' /home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh; then
        echo "  ✅ systemctl 呼び出しあり"
    else
        echo "  ❌ systemctl 呼び出しなし"
        exit 1
    fi
    if ! grep -q 'nohup camilladsp' /home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh; then
        echo "  ✅ nohup camilladsp 直接起動なし"
    else
        echo "  ❌ nohup camilladsp 直接起動が残存"
        exit 1
    fi
else
    echo "  ❌ switch_audio.sh が見つからない"
    exit 1
fi
echo
3. CamillaDSP 単独起動テスト
echo "  停止中の camilladsp を systemctl start..."
systemctl stop camilladsp.service 2>/dev/null || true
sleep 1
systemctl start camilladsp.service
sleep 3
if systemctl is-active --quiet camilladsp.service; then
    echo "  ✅ systemctl start 成功"
    if ss -ltn | grep -q ':1234 '; then
        echo "  ✅ ポート 1234 LISTEN 確認"
    else
        echo "  ❌ ポート 1234 LISTEN なし"
        exit 1
    fi
else
    echo "  ❌ systemctl start 失敗"
    journalctl -u camilladsp -n 20 --no-pager
    exit 1
fi
echo
4. switch_audio.sh 経由切替テスト pure -> dsp
echo "  pure モードへ切替..."
/home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh pure "plughw:1,0"
sleep 2
if systemctl is-active --quiet camilladsp.service; then
    echo "  ⚠️ pure モードなのに camilladsp が動いている (想定外)"
    systemctl stop camilladsp.service
else
    echo "  ✅ pure モードで camilladsp 停止確認"
fi
echo "  dsp モードへ切替..."
YAML=$(find /var/lib/camilladsp -name '*.yml' -o -name '*.yaml' 2>/dev/null | head -1)
if [ -z "$YAML" ]; then
    echo "  ⚠️ YAML ファイルが見つからない、スキップ"
else
    /home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh dsp "plughw:1,0" "$YAML"
    sleep 3
    if systemctl is-active --quiet camilladsp.service; then
        echo "  ✅ dsp モードで camilladsp 起動確認"
        if ss -ltn | grep -q ':1234 '; then
            echo "  ✅ ポート 1234 LISTEN 確認"
        fi
        # Loopback capture チェック
        for params in /proc/asound/Loopback/pcm1c/sub*/hw_params; do
            [ -f "$params" ] || continue
            if grep -q '^access:' "$params" 2>/dev/null; then
                echo "  ✅ Loopback capture active 確認"
                break
            fi
        done
    else
        echo "  ❌ dsp モードで camilladsp 起動失敗"
        journalctl -u camilladsp -n 20 --no-pager
        exit 1
    fi
fi
echo
5. 孤児プロセス確認
ORPHANS=$(ps -eo pid,ppid,comm | awk '$2==1 && $3=="camilladsp" {print $1}')
if [ -z "$ORPHANS" ]; then
    echo "  ✅ 孤児プロセスなし"
else
    echo "  ❌ 孤児プロセス検出: $ORPHANS"
    exit 1
fi
echo
6. RT 優先度確認
CAMILLA_PID=$(systemctl show camilladsp.service --property=MainPID --value)
if [ "$CAMILLA_PID" != "0" ] && [ -n "$CAMILLA_PID" ]; then
    CHRT_OUT=$(chrt -p "$CAMILLA_PID" 2>/dev/null || echo "failed")
    if echo "$CHRT_OUT" | grep -q 'SCHED_FIFO'; then
        echo "  ✅ SCHED_FIFO 適用済み: $CHRT_OUT"
    else
        echo "  ⚠️ RT 未適用: $CHRT_OUT"
    fi
else
    echo "  ⚠️ PID 取得失敗"
fi
echo
echo "=== Root Fix B 検証完了: $(date) ==="
echo "ログ: $LOG"
