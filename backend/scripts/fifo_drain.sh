#!/bin/bash
# FIFO Drain - Safety net: FIFOを常に読み捨ててMPDのブロックを防ぐ
# aplayが起動したら自動的にaplayが読み取り側になる（FIFOは1readerのみ）ため、
# このプロセスはaplayが起動するまでの間だけ有効に機能する

FIFO="/tmp/mpd.fifo"

while true; do
    [ -p "$FIFO" ] || mkfifo "$FIFO" && chmod 666 "$FIFO"
    # FIFOを読み捨て（MPDがブロックしないよう常に消費）
    cat "$FIFO" > /dev/null 2>&1
    sleep 0.1
done
