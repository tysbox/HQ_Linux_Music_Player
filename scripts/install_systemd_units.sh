#!/usr/bin/env bash
# install_systemd_units.sh — systemd unit テンプレートを実機値に置換して適用する。
#
# 設計方針 (リスク最小・即ロールバック可能):
#   - 既定は dry-run (何も書き込まない)。適用には --apply が必要
#   - --apply 時は既存 unit を /etc/systemd/system/<name>.bak.<timestamp> へ退避
#   - 置換結果は /tmp に書き、systemd-analyze verify で検証してから cp する
#   - daemon-reload / restart は --reload を明示したときのみ実行
#
# 使用法:
#   scripts/install_systemd_units.sh                 # 置換結果を表示 (dry-run)
#   sudo scripts/install_systemd_units.sh --apply    # 退避 + 配置 + verify
#   sudo scripts/install_systemd_units.sh --apply --reload   # 配置後 daemon-reload
#
# 環境変数で上書き可能:
#   HQM_ROOT, HQM_USER, HQM_GROUP, HQ_API_PORT, CAMILLA_PORT,
#   CAMILLA_BIN, CAMILLA_YAML, CAMILLA_STATE
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HQM_ROOT="${HQM_ROOT:-$DEFAULT_ROOT}"
HQM_USER="${HQM_USER:-${SUDO_USER:-$USER}}"
if [[ "$HQM_USER" == "root" ]]; then
  echo "WARN: 実行ユーザーが root です。HQM_USER=<実ユーザー> を指定してください。" >&2
fi
HQM_GROUP="${HQM_GROUP:-$(id -gn "$HQM_USER" 2>/dev/null || echo "$HQM_USER")}"
HQM_HOME="$(getent passwd "$HQM_USER" | cut -d: -f6 || true)"
HQM_HOME="${HQM_HOME:-$HOME}"
HQ_API_PORT="${HQ_API_PORT:-8002}"
CAMILLA_PORT="${CAMILLA_PORT:-1234}"
CAMILLA_YAML="${CAMILLA_YAML:-/tmp/camilladsp/active_dsp.yml}"
CAMILLA_STATE="${CAMILLA_STATE:-/tmp/camilladsp/state.yml}"
CAMILLA_DIR="$(dirname "$CAMILLA_YAML")"
CAMILLA_BIN="${CAMILLA_BIN:-$(command -v camilladsp || echo /usr/local/bin/camilladsp)}"
HQM_VENV="${HQM_VENV:-$HQM_ROOT/backend/venv/bin/python3}"

TEMPLATE_DIR="$HQM_ROOT/config/systemd"
WORK_DIR="$(mktemp -d /tmp/hqm-systemd.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

APPLY=0
RELOAD=0
STAGE_DIR=""
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --reload) RELOAD=1 ;;
    --stage=*) STAGE_DIR="${arg#--stage=}" ;;
    -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "不明な引数: $arg" >&2; exit 2 ;;
  esac
done

render() {
  local tpl="$1" out="$2"
  sed \
    -e "s|@@HQM_ROOT@@|${HQM_ROOT}|g" \
    -e "s|@@HQM_USER@@|${HQM_USER}|g" \
    -e "s|@@HQM_GROUP@@|${HQM_GROUP}|g" \
    -e "s|@@HQM_HOME@@|${HQM_HOME}|g" \
    -e "s|@@HQM_VENV@@|${HQM_VENV}|g" \
    -e "s|@@HQ_API_PORT@@|${HQ_API_PORT}|g" \
    -e "s|@@CAMILLA_BIN@@|${CAMILLA_BIN}|g" \
    -e "s|@@CAMILLA_PORT@@|${CAMILLA_PORT}|g" \
    -e "s|@@CAMILLA_YAML@@|${CAMILLA_YAML}|g" \
    -e "s|@@CAMILLA_STATE@@|${CAMILLA_STATE}|g" \
    -e "s|@@CAMILLA_DIR@@|${CAMILLA_DIR}|g" \
    "$tpl" > "$out"
}

echo "== 解決した値 =="
echo "  HQM_ROOT      = $HQM_ROOT"
echo "  HQM_USER      = $HQM_USER (group=$HQM_GROUP home=$HQM_HOME)"
echo "  HQM_VENV      = $HQM_VENV"
echo "  HQ_API_PORT   = $HQ_API_PORT"
echo "  CAMILLA_BIN   = $CAMILLA_BIN"
echo "  CAMILLA_PORT  = $CAMILLA_PORT"
echo "  CAMILLA_YAML  = $CAMILLA_YAML"
echo "  CAMILLA_STATE = $CAMILLA_STATE"
echo

if [[ "$APPLY" -eq 0 ]]; then
  if [[ -n "$STAGE_DIR" ]]; then
    mkdir -p "$STAGE_DIR"
    for tpl in camilladsp hq-api; do
      name="${tpl}.service"
      render "$TEMPLATE_DIR/${tpl}.service.template" "$STAGE_DIR/$name"
      if command -v systemd-analyze >/dev/null 2>&1; then
        if systemd-analyze verify "$STAGE_DIR/$name" 2>"$STAGE_DIR/$name.verify"; then
          echo "verify OK: $STAGE_DIR/$name"
        else
          echo "verify NG: $STAGE_DIR/$name" >&2
          cat "$STAGE_DIR/$name.verify" >&2
        fi
      fi
    done
    echo
    echo "ステージ済み成果物: $STAGE_DIR"
    echo "適用するには (要 sudo):"
    echo "  sudo cp $STAGE_DIR/camilladsp.service /etc/systemd/system/camilladsp.service"
    echo "  sudo cp $STAGE_DIR/hq-api.service /etc/systemd/system/hq-api.service"
    echo "  sudo systemctl daemon-reload && sudo systemctl restart camilladsp.service hq-api.service"
    exit 0
  fi
  for tpl in camilladsp hq-api; do
    echo "----- (dry-run) $tpl.service -----"
    render "$TEMPLATE_DIR/${tpl}.service.template" "$WORK_DIR/${tpl}.service"
    cat "$WORK_DIR/${tpl}.service"
    echo
  done
  echo "dry-run のため書き込みは行っていません。適用するには --apply を付けて再実行してください。"
  exit 0
fi

if [[ ! -x "$HQM_VENV" ]]; then
  echo "ERROR: venv python が見つかりません: $HQM_VENV" >&2
  exit 1
fi
if [[ ! -x "$CAMILLA_BIN" ]]; then
  echo "ERROR: camilladsp 実行ファイルが見つかりません: $CAMILLA_BIN" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
for tpl in camilladsp hq-api; do
  name="${tpl}.service"
  render "$TEMPLATE_DIR/${tpl}.service.template" "$WORK_DIR/$name"
  if command -v systemd-analyze >/dev/null 2>&1; then
    if ! systemd-analyze verify "$WORK_DIR/$name" 2>"$WORK_DIR/$name.verify"; then
      echo "ERROR: systemd-analyze verify 失敗: $name" >&2
      cat "$WORK_DIR/$name.verify" >&2
      echo "適用を中止しました (既存 unit は未変更)。" >&2
      exit 1
    fi
    # 未知キー警告のみの場合は成功扱い
    if grep -qE "Unknown key|unknown lvalue" "$WORK_DIR/$name.verify" 2>/dev/null; then
      echo "NOTE: $name verify 警告:"; cat "$WORK_DIR/$name.verify"
    fi
  fi
done

TARGET_DIR="/etc/systemd/system"
for tpl in camilladsp hq-api; do
  name="${tpl}.service"
  if [[ -f "$TARGET_DIR/$name" ]]; then
    sudo cp -a "$TARGET_DIR/$name" "$TARGET_DIR/$name.bak.$TS"
    echo "退避: $TARGET_DIR/$name -> $TARGET_DIR/$name.bak.$TS"
  fi
  sudo cp "$WORK_DIR/$name" "$TARGET_DIR/$name"
  echo "配置: $TARGET_DIR/$name"
done

if [[ "$RELOAD" -eq 1 ]]; then
  sudo systemctl daemon-reload
  echo "daemon-reload 実行済み。ロールバック:"
else
  echo "daemon-reload 未実行。次を実行してください:"
fi
echo "  sudo cp $TARGET_DIR/camilladsp.service.bak.$TS $TARGET_DIR/camilladsp.service"
echo "  sudo cp $TARGET_DIR/hq-api.service.bak.$TS $TARGET_DIR/hq-api.service"
echo "  sudo systemctl daemon-reload && sudo systemctl restart hq-api.service camilladsp.service"
