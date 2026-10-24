#!/usr/bin/env python3
"""DSP プロファイル管理モジュール（Stage 3-2: ローダと検証）

JSON Schema に基づくプロファイルの読み込み・検証・一覧取得。
FastAPI 等の Web フレームワーク非依存（純粋ロジック）。

実行:
  ./backend/venv/bin/python3 -m unittest tests.unit.test_profiles -v
"""
import json
import os
import shutil
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
    
    # 過大ブースト検出（目的別・2026-10-12 改定）
    # device_correction (AutoEq 測定ベース): 大きなブーストと負の preamp が正常形式。
    #   クリップ防止は Stage 2-5 の自動ヘッドルームが合成応答 (preamp 含む) から
    #   常時担保するため上限を 60dB に緩和 (旧 20dB では Bisen カタログ 2,815 機種中
    #   725 機種 = 26% が失われていた)。
    # sound_color (手作り音色): 従来どおり 20dB を維持 (誤設定の大音量ブースト防止)。
    total_boost = sum(max(0, b.get("gain", 0)) for b in profile.get("bands", []))
    boost_limit = 60.0 if profile.get("purpose") == "device_correction" else 20.0
    if total_boost > boost_limit:
        errors.append(f"Total positive gain {total_boost:.1f}dB exceeds {boost_limit:.0f}dB limit")
    
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


def profile_to_biquads(profile: dict, fs: float = 192000, gain_scale: float = 1.0) -> list[dict]:
    """
    プロファイルの bands を yaml_generator 互換の Biquad フィルタ辞書リストに変換。

    Args:
        profile: 検証済みプロファイル辞書
        fs: サンプリングレート
        gain_scale: band ゲインのスケール係数 (0.0-1.0)。Bisen calibrationIntensity
            相当。preamp_db はスケールしない (Bisen 仕様と同一)。
            既定 1.0 = 従来動作 (ゲインそのまま)。

    Returns:
        [{"type": "Biquad", "parameters": {...}}, ...] 形式のリスト
    """
    from backend.dsp.analysis import rbj_coefficients

    type_map = {
        "peaking": "Peaking",
        # CamillaDSP 4.1.3 の有効型名は Lowshelf/Highshelf (L大文字・s小文字)。
        # 旧実装の "LowShelf"/"HighShelf" は camilladsp --check で拒否される無効型名
        # だったため 2026-10-12 に修正 (Stage 8 で初めて実生成に使用され顕在化)。
        "lowshelf": "Lowshelf",
        "highshelf": "Highshelf",
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
        gain = round(band.get("gain", 0.0) * gain_scale, 2)
        
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


# ─────────────────────────────────────────────────────────────────────────────
# 同梱プロファイル (Bisen移植 Phase 1 / Step 1-3)
# ─────────────────────────────────────────────────────────────────────────────
def bundled_profiles_dir() -> Path:
    """リポジトリ同梱プロファイルのディレクトリ (config/profiles/)。"""
    return Path(_PROJ) / "config" / "profiles"


def install_bundled_profiles(force: bool = False) -> list[str]:
    """同梱プロファイルを PROFILES_DIR へインストール (既定: 既存は上書きしない)。

    Bisen-DSP-System の内蔵プロファイル (headphoneProfiles.ts) を JSON スキーマ
    準拠に変換したもの。手元の既存プロファイルを保護するため、同名ファイルが
    存在する場合は force=True でなければ上書きしない。

    Args:
        force: True なら同名ファイルも上書きする

    Returns:
        新たにコピーしたプロファイル ID のリスト
    """
    src_dir = bundled_profiles_dir()
    if not src_dir.exists():
        return []
    ensure_profiles_dir()
    installed: list[str] = []
    for path in sorted(src_dir.glob("*.json")):
        dst = PROFILES_DIR / path.name
        if dst.exists() and not force:
            continue
        shutil.copy2(path, dst)
        installed.append(path.stem)
    return installed


# ─────────────────────────────────────────────────────────────────────────────
# 同梱カタログ (Bisen 測定データ 2,810 機種 — Phase 1 Step 1-3b)
# ─────────────────────────────────────────────────────────────────────────────
def bundled_catalog_path() -> Path:
    """同梱カタログ (config/profiles/catalog.json) のパス。"""
    return bundled_profiles_dir() / "catalog.json"


_CATALOG_CACHE: dict = {"mtime": None, "data": None}


def load_catalog() -> dict:
    """同梱カタログを読み込む (mtime キャッシュ付き)。

    Returns:
        {"total": int, "entries": [...]} カタログ辞書。未生成時は空カタログ。
    """
    path = bundled_catalog_path()
    if not path.exists():
        return {"schema_version": 1, "total": 0, "entries": []}
    mtime = path.stat().st_mtime
    if _CATALOG_CACHE["mtime"] == mtime and _CATALOG_CACHE["data"] is not None:
        return _CATALOG_CACHE["data"]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _CATALOG_CACHE["mtime"] = mtime
    _CATALOG_CACHE["data"] = data
    return data


def search_catalog(query: str = "", limit: int = 50) -> dict:
    """同梱カタログを検索する (オフライン・即応)。

    Args:
        query: ブランド/モデル名 (スペース区切り AND 検索。空 = 人気順)
        limit: 最大返却件数 (1-200)

    Returns:
        {"total": ヒット総数, "entries": [...]}
    """
    catalog = load_catalog()
    entries = catalog.get("entries", [])
    q = (query or "").strip().lower()
    if q:
        terms = q.split()

        def _match(e: dict) -> bool:
            hay = f"{e.get('brand', '')} {e.get('model', '')} {e.get('id', '')}".lower()
            return all(t in hay for t in terms)

        hits = [e for e in entries if _match(e)]
        # 完全一致を優先し、次に popularity 順
        hits.sort(key=lambda e: (
            0 if q in f"{e.get('brand', '')} {e.get('model', '')}".lower() else 1,
            -int(e.get("popularity", 0)),
        ))
    else:
        hits = sorted(entries, key=lambda e: -int(e.get("popularity", 0)))
    safe_limit = max(1, min(int(limit), 200))
    return {"total": len(hits), "entries": hits[:safe_limit]}


def import_catalog_entry(entry_id: str, force: bool = False) -> dict | None:
    """カタログエントリをプロファイルとして PROFILES_DIR に実体化する。

    既に取り込み済み (同名プロファイル存在) の場合は既存を返す (冪等)。
    force=True でカタログ側の内容で上書きする。

    Args:
        entry_id: カタログエントリ ID (例: 'oratory1990__in_ear__Bose_Q25_ANC_off')
        force: 既存プロファイルを上書きするか

    Returns:
        取り込んだ (または既存の) プロファイル辞書。未検出/検証失敗は None。
    """
    catalog = load_catalog()
    entry = next(
        (e for e in catalog.get("entries", []) if e.get("id") == entry_id), None)
    if entry is None:
        return None
    profile = entry.get("profile")
    if not profile:
        return None

    dst_id = profile["id"]
    if not force:
        existing = load_profile(dst_id)
        if existing is not None:
            return existing  # 取り込み済み → 冪等

    from backend.dsp.autoeq import save_autoeq_profile
    if save_autoeq_profile(profile) is None:
        return None
    return load_profile(dst_id)


if __name__ == "__main__":
    # 簡易動作確認
    ensure_profiles_dir()
    print(f"Profiles dir: {PROFILES_DIR}")
    print(f"Schema: {SCHEMA_PATH}")
    print(f"Bundled dir: {bundled_profiles_dir()}")
    newly = install_bundled_profiles()
    if newly:
        print(f"Installed bundled: {newly}")
    print(f"Profiles found: {len(list_profiles())}")
    for p in list_profiles():
        print(f"  - {p['id']}: {p['name']} ({p['type']}, {p['purpose']})")
