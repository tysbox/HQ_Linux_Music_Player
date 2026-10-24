#!/usr/bin/env bash
# patch_mpd_autoenable.sh — /etc/mpd.conf の audio_output に autoenable を設定する
#
# 背景 (2026-10-21 実測):
#   DSP 構成では MPD は常に ALSA Loopback のみへ出力し、USB DAC / PC Speaker /
#   Bluetooth への切替は CamillaDSP の YAML (devices.playback.device) が担う。
#   ところが /etc/mpd.conf の audio_output に autoenable が無いと、
#   MPD 再起動時に全出力が enabled になる。すると:
#     1. MPD が PCH (PC Speaker) を掴む
#     2. CamillaDSP が PCH を開こうとして "Device or resource busy" で停止
#     3. DSP 経路が完全に死に、VU メーター / ボリューム / OUTPUT 選択が
#        まとめて機能停止する
#   USB DAC を抜いた直後 (CamillaDSP が DISCONNECTED で停止した後) に
#   MPD が PCH を掴う形で実際に発生を確認した。
#
# 対応:
#   ALSA Loopback のみ autoenable yes、他 (USB DAC / PC Speaker / Bluetooth) は
#   autoenable no。MPD 再起動後も Loopback だけが有効な状態を保つ。
#
# 使い方:
#   sudo scripts/patch_mpd_autoenable.sh          # 適用 + mpd 再起動
#   sudo scripts/patch_mpd_autoenable.sh --dry-run # 差分表示のみ
#
# 副作用:
#   /etc/mpd.conf を /etc/mpd.conf.bak.<timestamp> へ退避してから書き換える。
#   mpd.service を再起動する (再生が 1〜2 秒途切れる)。
set -euo pipefail

CONF="${MPD_CONF:-/etc/mpd.conf}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

if [ ! -f "$CONF" ]; then
    echo "ERROR: $CONF not found" >&2
    exit 1
fi

echo "=== 現在の設定 ==="
grep -n -E 'name\s+"|autoenable' "$CONF" || true

if [ "$DRY_RUN" -eq 1 ]; then
    echo
    echo "=== 適用後の差分 (dry-run) ==="
    python3 - "$CONF" <<'PY'
import re, sys, difflib
path = sys.argv[1]
text = open(path, encoding="utf-8").read()

def fix_block(m):
    body = m.group(0)
    if "autoenable" in body:
        return body
    def repl(mm):
        val = "yes" if mm.group(3) == "ALSA Loopback" else "no"
        # MPD の設定値は引用符が必須。引用符なしだと
        #   Error in "/etc/mpd.conf" line N; '"' expected
        # で mpd が起動に失敗する (2026-10-24 修正)。
        return mm.group(1) + f'\n{mm.group(2)}autoenable    "{val}"'
    return re.sub(r'(\n(\s*)name\s+"([^"]+)")', repl, body, count=1)

new = re.sub(r'audio_output\s*\{.*?\n\}', fix_block, text, flags=re.S)
print("".join(difflib.unified_diff(text.splitlines(True), new.splitlines(True), path, "patched")))
PY
    exit 0
fi

BAK="$CONF.bak.$(date +%Y%m%dT%H%M%SZ)"
cp -a "$CONF" "$BAK"
echo "backup: $BAK"

python3 - "$CONF" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()

def fix_block(m):
    body = m.group(0)
    if "autoenable" in body:
        return body
    def repl(mm):
        val = "yes" if mm.group(3) == "ALSA Loopback" else "no"
        # MPD の設定値は引用符が必須 (上記 dry-run 側と同じ理由)。
        return mm.group(1) + f'\n{mm.group(2)}autoenable    "{val}"'
    return re.sub(r'(\n(\s*)name\s+"([^"]+)")', repl, body, count=1)

new = re.sub(r'audio_output\s*\{.*?\n\}', fix_block, text, flags=re.S)
open(path, "w", encoding="utf-8").write(new)
print("patched")
PY

echo "=== 適用後 ==="
grep -n -E 'name\s+"|autoenable' "$CONF"

systemctl restart mpd.service
sleep 2
echo "=== mpc outputs ==="
mpc outputs 2>&1 | grep -E "^Output|enabled|disabled" || true
