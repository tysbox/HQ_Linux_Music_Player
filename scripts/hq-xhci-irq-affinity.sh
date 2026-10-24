#!/bin/sh
# HQ Linux Music Player — xhci_hcd IRQ の CPU 再配置
#
# 目的: USB DAC 出力と USB コントローラの割り込みを同一 CPU 上に置かない。
#   IRQ (xhci_hcd) が CPU1 に 100% 固定され、CamillaDSP の AlsaPlayback
#   スレッドと MPD の output:ALSA Loopback スレッドも CPU1 で動作していたため、
#   割り込み処理の遅延で再生スレッドが preempt され音切れが発生していた。
#
# 構成:
#   IRQ (xhci_hcd)      → CPU0
#   オーディオスレッド   → CPU1,3
#
# IRQ 番号は起動ごとに変わるため、/proc/irq を走査して動的に解決する。
#   udev ルール /etc/udev/rules.d/99-xhci-irq-affinity.rules から呼ばれる。
#
# root 権限が無い場合は /proc への書き込みが失敗する（何も起きない）。
#   冪等であり、失敗しても Safe である。
#
# README §12-6 (IRQ 固定と CPU アフィニティ分離) 参照。

set -e

for irqdir in /proc/irq/*/; do
    [ -e "${irqdir}xhci_hcd" ] || continue
    irq=$(basename "$irqdir")
    echo 0 > "/proc/irq/${irq}/smp_affinity_list" 2>/dev/null || true
done

exit 0
