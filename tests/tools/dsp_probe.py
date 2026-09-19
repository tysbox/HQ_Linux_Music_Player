#!/usr/bin/env python3
"""DSP 検査ツール（Stage 0: 非破壊テスト基盤）

用途:
- guard --snapshot: 保護対象の md5 を記録
- guard --verify:   保護対象が変更されていないか検証
- yaml <json>:      任意設定で YAML 生成（標準出力）
- gain-margin:      全構成の最大ゲインを計算

保護対象（書き換えてはいけないもの）:
1. /tmp/camilladsp/active_dsp.yml
2. ~/.config/audiophile/last_config.json
3. ~/.config/audiophile/presets.json
4. ~/.cache/audiophile/ir/*.wav
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile

# プロジェクトルートをパスに追加
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.yaml_generator import generate_camilladsp_yaml  # noqa: E402
from backend.main import AudioConfig  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 保護対象の定義
# ─────────────────────────────────────────────────────────────────────────────
PROTECTED_FILES = [
    "/tmp/camilladsp/active_dsp.yml",
    os.path.expanduser("~/.config/audiophile/last_config.json"),
    os.path.expanduser("~/.config/audiophile/presets.json"),
]

PROTECTED_IR_DIR = os.path.expanduser("~/.cache/audiophile/ir/")


def _md5_file(path: str) -> str | None:
    """ファイルの md5 を返す。存在しない場合は None."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def _md5_dir(dir_path: str) -> dict[str, str]:
    """ディレクトリ内の .wav ファイルの md5 を辞書で返す."""
    result = {}
    if os.path.isdir(dir_path):
        for fname in sorted(os.listdir(dir_path)):
            if fname.endswith(".wav"):
                fpath = os.path.join(dir_path, fname)
                md5 = _md5_file(fpath)
                if md5:
                    result[fname] = md5
    return result


def _snapshot_all() -> dict:
    """保護対象すべてのスナップショットを取得."""
    snapshot = {"files": {}, "ir_files": {}}
    for f in PROTECTED_FILES:
        md5 = _md5_file(f)
        if md5:
            snapshot["files"][f] = md5
    snapshot["ir_files"] = _md5_dir(PROTECTED_IR_DIR)
    return snapshot


def cmd_guard_snapshot(args):
    """guard snapshot: 保護対象の md5 を標準出力に JSON で出力し、キャッシュに保存."""
    snap = _snapshot_all()
    # キャッシュディレクトリに保存
    cache_dir = os.path.expanduser("~/.cache/audiophile")
    os.makedirs(cache_dir, exist_ok=True)
    snapshot_path = os.path.join(cache_dir, "dsp_probe_snapshot.json")
    with open(snapshot_path, "w") as f:
        json.dump(snap, f, indent=2, sort_keys=True)
    print(json.dumps(snap, indent=2, sort_keys=True))
    print(f"\nSnapshot saved to {snapshot_path}", file=sys.stderr)
    return 0


def cmd_guard_verify(args):
    """guard --verify: 保護対象がスナップショットと一致するか検証."""
    # スナップショットファイルを読み込み
    snapshot_path = os.path.expanduser("~/.cache/audiophile/dsp_probe_snapshot.json")
    if not os.path.exists(snapshot_path):
        print("ERROR: Snapshot file not found. Run 'guard --snapshot' first.", file=sys.stderr)
        return 1

    with open(snapshot_path) as f:
        expected = json.load(f)

    current = _snapshot_all()

    # 比較
    mismatches = []
    for f, expected_md5 in expected.get("files", {}).items():
        current_md5 = current["files"].get(f)
        if current_md5 != expected_md5:
            mismatches.append(f"{f}: expected {expected_md5}, got {current_md5}")

    for fname, expected_md5 in expected.get("ir_files", {}).items():
        current_md5 = current["ir_files"].get(fname)
        if current_md5 != expected_md5:
            mismatches.append(f"IR {fname}: expected {expected_md5}, got {current_md5}")

    # IR ファイルの増減もチェック
    expected_ir_set = set(expected.get("ir_files", {}).keys())
    current_ir_set = set(current["ir_files"].keys())
    if expected_ir_set != current_ir_set:
        added = current_ir_set - expected_ir_set
        removed = expected_ir_set - current_ir_set
        if added:
            mismatches.append(f"IR files added: {added}")
        if removed:
            mismatches.append(f"IR files removed: {removed}")

    if mismatches:
        print("FAIL: Protected files changed:", file=sys.stderr)
        for m in mismatches:
            print(f"  {m}", file=sys.stderr)
        return 1

    print("OK: All protected files unchanged")
    return 0


def cmd_yaml(args):
    """yaml <json>: 任意設定で YAML 生成（標準出力）。"""
    try:
        config_dict = json.loads(args.config_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        return 1

    # 一時ファイルに生成
    with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
        tmp_path = f.name

    try:
        cfg = AudioConfig(**config_dict)
        generate_camilladsp_yaml(cfg, out_path=tmp_path)
        with open(tmp_path) as f:
            print(f.read())
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    return 0


def cmd_gain_margin(args):
    """gain-margin: 全構成の最大ゲインを計算（Stage 2 以降で実装）。"""
    from backend.dsp.analysis import max_gain_of_config
    import yaml

    configs = {
        "none": {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "none", "crossfeed_intensity": 5,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
        },
        "eq_only": {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "classical", "eq_output": "studio-monitors",
            "crossfeed": "none", "crossfeed_intensity": 5,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
        },
        "reverb_only": {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "none", "crossfeed_intensity": 5,
            "hum_noise": "none", "reverb": "hall", "reverb_intensity": 35,
        },
        "crossfeed_only": {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "none", "eq_output": "none",
            "crossfeed": "standard", "crossfeed_intensity": 50,
            "hum_noise": "none", "reverb": "none", "reverb_intensity": 5,
        },
        "all_enabled": {
            "mode": "dsp", "device": "plughw:1,0", "volume": -12.0,
            "music_type": "classical", "eq_output": "studio-monitors",
            "crossfeed": "standard", "crossfeed_intensity": 50,
            "hum_noise": "60hz", "reverb": "hall", "reverb_intensity": 35,
        },
    }

    results = {}
    for name, config_dict in configs.items():
        cfg = AudioConfig(**config_dict)
        with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
            tmp_path = f.name
        try:
            generate_camilladsp_yaml(cfg, out_path=tmp_path)
            with open(tmp_path) as f:
                y = yaml.safe_load(f)
            max_gain = max_gain_of_config(y["filters"])
            results[name] = max_gain
            print(f"{name}: max_gain = {max_gain:.2f} dB")
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    # 2回実行して同一値か確認（決定性テスト）
    print("\n--- 再実行で同一性確認 ---")
    for name, config_dict in configs.items():
        cfg = AudioConfig(**config_dict)
        with tempfile.NamedTemporaryFile(mode="w", suffix="_dsp.yml", delete=False) as f:
            tmp_path = f.name
        try:
            generate_camilladsp_yaml(cfg, out_path=tmp_path)
            with open(tmp_path) as f:
                y = yaml.safe_load(f)
            max_gain = max_gain_of_config(y["filters"])
            if abs(max_gain - results[name]) > 1e-10:
                print(f"FAIL: {name} 不一致: {max_gain:.10f} != {results[name]:.10f}", file=sys.stderr)
                return 1
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    print("OK: 2回実行で同一値")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="dsp_probe", description="DSP 検査ツール")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # guard
    p_guard = sub.add_parser("guard", help="保護対象のスナップショット/検証")
    p_guard.add_argument("action", choices=["snapshot", "verify"], help="snapshot または verify")
    p_guard.set_defaults(func=lambda a: cmd_guard_snapshot(a) if a.action == "snapshot" else cmd_guard_verify(a))

    # yaml
    p_yaml = sub.add_parser("yaml", help="設定 JSON から YAML 生成（標準出力）")
    p_yaml.add_argument("config_json", help="AudioConfig 相当の JSON 文字列")
    p_yaml.set_defaults(func=cmd_yaml)

    # gain-margin
    p_gm = sub.add_parser("gain-margin", help="全構成の最大ゲインを計算")
    p_gm.set_defaults(func=cmd_gain_margin)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())