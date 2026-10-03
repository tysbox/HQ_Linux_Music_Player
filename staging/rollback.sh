#!/bin/bash
# Root Fix B ロールバックスクリプト
# 実行: sudo ./staging/rollback.sh

set -euo pipefail

echo "=== Root Fix B ロールバック開始: $(date) ==="

echo "1. 既存 unit のバックアップから復元"
LATEST_BAK=$(ls -t /etc/systemd/system/camilladsp.service.bak.* 2>/dev/null | head -1)
if [ -n "$LATEST_BAK" ]; then
    echo "  復元: $LATEST_BAK -> /etc/systemd/system/camilladsp.service"
    cp "$LATEST_BAK" /etc/systemd/system/camilladsp.service
else
    echo "  ⚠️ バックアップが見つからない、デフォルト template から復元"
    /home/tysbox/HQ_Linux_Music_Player/scripts/install_systemd_units.sh --stage=/tmp/rollback-$(date +%s)
    cp /tmp/rollback-*/camilladsp.service /etc/systemd/system/camilladsp.service
fi

echo "2. systemd デーモンリロード"
systemctl daemon-reload

echo "3. CamillaDSP 再起動"
systemctl restart camilladsp.service
sleep 3

echo "4. switch_audio.sh を元のバージョンに戻す (必要なら)"
if [ -f /home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh.orig ]; then
    cp /home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh.orig /home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh
    echo "  switch_audio.sh を元に戻しました"
else
    echo "  元の switch_audio.sh は git で管理されているため、git restore で復元可能"
fi

echo "5. CamillaDSP 再起動（元の設定で）"
systemctl restart camilladsp.service
sleep 3

echo "=== ロールバック完了: $(date) ==="
echo "確認: systemctl status camilladsp.service"
