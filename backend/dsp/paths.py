"""CamillaDSP 設定/状態パスの単一ソース (Single Source of Truth).

背景 (2026-10-02 点検):
    従来 `HQ_DSP_YAML` / `CAMILLA_STATE_FILE` は `/tmp/camilladsp/` を指していた。
    `/tmp` は tmpfs のため OS リブートで必ず消え、CamillaDSP は
    "Could not open config file" で起動失敗しoru。结果 8002 `/health` が
    `dsp: disconnected` になり、GUI の DSP 機能が毎回リブート後に失われていた。

    本モジュールは既定値を永続領域 (`/var/lib/camilladsp/`) に置き、
    環境変数による上書きを許す。shell / systemd / テストの双方が
    `tests/unit/test_dsp_paths_consistency.py` で一致することを検証する。

優先順位:
    1. 環境変数 (HQ_DSP_YAML / CAMILLA_STATE_FILE) — 実機のoverride
    2. 本モジュールの永続パス既定値

注意:
    CamillaDSP の「設定」(active_dsp.yml) は API 適用ごとに再生成される
    派生物であり、原本は Git 管理下に置かれない。/var/lib は全ユーザ共有の
    状態領域として妥当なため、CamillaDSP 公式パッケージの慣習に合わせる。
"""
from __future__ import annotations

import os

# ─────────────────────────────────────────────────────────────────────────────
# 永続領域の既定値
# ─────────────────────────────────────────────────────────────────────────────
#: 状態ディレクトリ (unit 側 CAMILLA_DIR / mkdir -p の対象)
DSP_STATE_DIR = "/var/lib/camilladsp"

#: 生成される CamillaDSP 設定 YAML
DEFAULT_DSP_YAML = f"{DSP_STATE_DIR}/active_dsp.yml"

#: 音量永続化 statefile (リブート後に音量が初期値に戻るのを防ぐ)
DEFAULT_DSP_STATE = f"{DSP_STATE_DIR}/state.yml"


def dsp_state_dir() -> str:
    """YAML / statefile を置くディレクトリ (環境変数で上書き可)."""
    return os.getenv("CAMILLA_STATE_DIR", DSP_STATE_DIR)


def dsp_yaml_path() -> str:
    """生成 YAML の実効パス."""
    return os.getenv("HQ_DSP_YAML") or DEFAULT_DSP_YAML


def dsp_state_path() -> str:
    """音量 statefile の実効パス."""
    return os.getenv("CAMILLA_STATE_FILE") or DEFAULT_DSP_STATE
