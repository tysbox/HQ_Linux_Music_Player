#!/usr/bin/env python3
"""DSP プロファイル管理モジュール（Stage 3-2: ローダと検証）

JSON Schema に基づくプロファイルの読み込み・検証・一覧取得。
FastAPI 等の Web フレームワーク非依存（純粋ロジック）。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_profiles -v
"""
import json
import os
from pathlib import Path
from typing import Any

import jsonschema

# プロジェクトルートをパスに追加
import sys
_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)


# ─────────────────────────────────────────────────────────────────────────────
# 定数・パス
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_PATH = Path(_PROJ) / "docs" / "schemas" / "dsp_profile.schema.json"
PROFILES_DIR = Path(os.path.expanduser("~/.config/audiophile/profiles"))


# ─────────────────────────────────────────────────────────────────────────────
# スキーマ読み込み（モジュール初期化時1回）
# ─────────────────────────────────────────────────────────────────────────────
_SCHEMA = None


def _load_schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        with open(SCHEMA_PATH) as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


# ─────────────────────────────────────────────────────────────────────────────
# 検証関数
# ─────────────────────────────────────────────────────────────────────────────
def validate_profile(profile: dict) -> tuple[bool, list[str]]:
    """
    プロファイル辞書をスキーマで検証。

    Args:
        profile: プロファイル辞書

    Returns:
        (is_valid, errors): 検証結果とエラーメッセージのリスト
    """
    schema = _load_schema()
    try:
        jsonschema.validate(instance=profile, schema=schema)
    except jsonschema.ValidationError as e:
        return False, [str(e)]
    except jsonschema.SchemaError as e:
        return False, [f"Schema error: {e}"]

    # 追加のセマンティック検証
    errors = []
    
    # q=0 は無効（ゼロ除算）
    for i, band in enumerate(profile.get("bands", [])):
        if band.get("type") in ("peaking", "notch", "lowpass", "highpass") and band.get("q", 0) <= 0:
            errors.append(f"Band {i}: {band['type']} requires q > 0")
        if band.get("type") in ("peaking", "lowshelf", "highshelf") and band.get("gain", 0) == 0:
            errors.append(f"Band {i}: {band['type']} requires non-zero gain")
        if band.get("freq", 0) <= 0 or band.get("freq", 0) > 96000:
            errors.append(f"Band {i}: freq must be in (0, 96000] Hz")
        if band.get("gain", 0) < -20 or band.get("gain", 0) > 20:
            errors.append(f"Band {i}: gain must be in [-20, 20] dB")
    
    # 過大ブースト検出（全帯域のゲイン合計が大きすぎる）
    total_boost = sum(max(0, b.get("gain", 0)) for b in profile.get("bands", []))
    if total_boost > 20:
        errors.append(f"Total positive gain {total_boost:.1f}dB exceeds 20dB limit")
    
    preamp = profile.get("preamp_db", 0)
    if preamp < -20 or preamp > 20:
        errors.append(f"preamp_db {preamp} out of range [-20, 20]")

    return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
# プロファイル読み込み
# ─────────────────────────────────────────────────────────────────────────────
def load_profile(profile_id: str) -> dict | None:
    """
    指定 ID のプロファイルを読み込み・検証。

    Args:
        profile_id: プロファイル ID（拡張子 .json なし）

    Returns:
        プロファイル辞書、存在しない/検証失敗なら None
    """
    path = PROFILES_DIR / f"{profile_id}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            profile = json.load(f)
    except json.JSONDecodeError:
        return None
    
    valid, errors = validate_profile(profile)
    if not valid:
        return None
    return profile


def list_profiles() -> list[dict]:
    """
    利用可能なプロファイル一覧を取得（軽量版: id, name, type, source, purpose のみ）。

    Returns:
        プロファイル概要のリスト
    """
    if not PROFILES_DIR.exists():
        return []
    
    result = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            with open(path) as f:
                profile = json.load(f)
            valid, _ = validate_profile(profile)
            if valid:
                result.append({
                    "id": profile.get("id"),
                    "name": profile.get("name"),
                    "type": profile.get("type"),
                    "source": profile.get("source"),
                    "purpose": profile.get("purpose"),
                })
        except Exception:
            continue
    return result


def load_all_profiles() -> dict[str, dict]:
    """
    すべての有効プロファイルを {id: profile} 形式で読み込み。
    """
    result = {}
    for path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            with open(path) as f:
                profile = json.load(f)
            valid, _ = validate_profile(profile)
            if valid:
                result[profile.get("id", path.stem)] = profile
        except Exception:
            continue
    return result


def profile_to_biquads(profile: dict, fs: float = 192000) -> list[dict]:
    """
    プロファイルの bands を yaml_generator 互換の Biquad フィルタ辞書リストに変換。

    Args:
        profile: 検証済みプロファイル辞書
        fs: サンプリングレート

    Returns:
        [{"type": "Biquad", "parameters": {...}}, ...] 形式のリスト
    """
    from backend.dsp.analysis import rbj_coefficients

    type_map = {
        "peaking": "Peaking",
        "lowshelf": "LowShelf",
        "highshelf": "HighShelf",
        "lowpass": "Lowpass",
        "highpass": "Highpass",
        "notch": "Notch",
    }

    biquads = []
    for band in profile.get("bands", []):
        bq_type = band.get("type")
        if bq_type not in type_map:
            continue
        freq = band.get("freq", 1000.0)
        q = band.get("q", 0.707)
        gain = band.get("gain", 0.0)
        
        # 係数計算（内部検証用）
        rbj_type = bq_type
        try:
            rbj_coefficients(rbj_type, freq, q, gain, fs)
        except Exception:
            continue
        
        biquads.append({
            "type": "Biquad",
            "parameters": {
                "type": type_map[bq_type],
                "freq": freq,
                "q": q,
                "gain": gain,
            }
        })
    return biquads


# ─────────────────────────────────────────────────────────────────────────────
# 初期化ヘルパー
# ─────────────────────────────────────────────────────────────────────────────
def ensure_profiles_dir() -> None:
    """プロファイルディレクトリの存在確認・作成。"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    # 簡易動作確認
    ensure_profiles_dir()
    print(f"Profiles dir: {PROFILES_DIR}")
    print(f"Schema: {SCHEMA_PATH}")
    print(f"Profiles found: {len(list_profiles())}")
    for p in list_profiles():
        print(f"  - {p['id']}: {p['name']} ({p['type']}, {p['purpose']})")
