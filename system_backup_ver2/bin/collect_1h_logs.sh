#!/bin/bash
# collect_1h_logs.sh
# Collect journal (bluealsa, run_sox_fifo, exclusive-bt), top samples and hciconfig snapshots for 1 hour.
set -euo pipefail
OUTDIR="/tmp/collect_bt_$(date +%Y%m%dT%H%M%S)"
mkdir -p "$OUTDIR"
echo "Collecting logs to $OUTDIR"

# journal (needs sudo to see everything)
timeout 3600s journalctl -f -u bluealsa -u run_sox_fifo.service -u exclusive-bt.service --no-pager > "$OUTDIR/journal.log" 2>&1 &
J1=$!

# top samples every 5s for 1 hour
timeout 3600s top -b -d 5 -n 720 > "$OUTDIR/top.log" 2>&1 &
J2=$!

# hciconfig snapshots every 5s
timeout 3600s bash -c 'while true; do date -Iseconds; hciconfig -a; sleep 5; done' > "$OUTDIR/hci.log" 2>&1 &
J3=$!

# optional: capture `ps aux` once at start
ps aux > "$OUTDIR/ps_initial.log"

# wait for collectors to finish
wait $J1 $J2 $J3 || true

echo "Collection finished, files in $OUTDIR"
