#!/bin/bash
# MPD曲切り替え監視＆自動再起動スクリプト
# ログは /var/log/mpd_watcher.log へ出力

LOGFILE="/home/tysbox/mpd_watcher.log"

# ログファイルがなければ作成
if [ ! -f "$LOGFILE" ]; then
    touch "$LOGFILE"
    chmod 666 "$LOGFILE"
fi

echo "[INFO] mpd_watcher started at $(date)" >> "$LOGFILE"

while true; do
    # 曲切り替えを監視
    mpc idle player
    echo "[INFO] Song change detected at $(date)" >> "$LOGFILE"
    # 【修正】MPD/run_sox_fifo の強制再起動は廃止。
    # run_sox_fifo.sh 内部の Python MPD モニターが既にトラック変更を
    # 検出してシグナルファイル経由でgapless対応の再起動を行っているため、
    # ここで外部から再起動すると逆にアンダーランを誘発する。
    echo "[INFO] (no restart: sox pipeline handles gapless internally)" >> "$LOGFILE"
    # ループ継続
done
