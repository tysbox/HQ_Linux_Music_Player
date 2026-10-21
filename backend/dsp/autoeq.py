#!/usr/bin/env python3
"""AutoEq ParametricEQ.txt パーサ（Bisen移植 Phase 1 / Step 1-4）.

Bisen-DSP-System src/dsp/customProfileStorage.ts parseAutoEqText() の Python 移植。
AutoEq テキスト形式 (jaakkopasanen/AutoEq、oratory1990 互換) を本リポジトリの
DSP プロファイル JSON スキーマ (docs/schemas/dsp_profile.schema.json) に変換する。

移植時の改善 (Bisen 仕様を超える部分):
- Bisen はフィルタ種別トークン (PK/LSC/HSC) を読み捨て、全バンドを peaking 扱い
  にしていた。本実装は種別を解析し peaking/lowshelf/highshelf に正しくマッピング
  する (= 補正精度が上がる)。
- ID はタイムスタンプ乱数ではなく名前から決定的に生成 (再インポート冪等)。

形式例:
    Preamp: -5.4 dB
    Filter 1: ON PK Fc 32 Hz Gain 4.8 dB Q 1.41
    Filter 2: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.71
    Filter 3: ON HSC Fc 10000 Hz Gain -1.0 dB Q 0.71

実行 (単体テスト):
  ./backend/venv/bin/python3 -m unittest tests.unit.test_autoeq -v
"""
import hashlib
import json
import os
import re
import tempfile
from typing import Optional

# Bisen customProfileStorage.ts と同一規約の正規表現 (Preamp / Filter 行)
_PREAMP_RE = re.compile(r"Preamp:\s*(-?\d+(?:\.\d+)?)\s*dB", re.IGNORECASE)
_FILTER_RE = re.compile(
    r"Fc\s+(\d+(?:\.\d+)?)\s*Hz\s+Gain\s+(-?\d+(?:\.\d+)?)\s*dB\s+Q\s+(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
# 種別トークン (移植改善): "Filter N: ON <TYPE> Fc ..."
_TYPE_RE = re.compile(r"Filter\s+\d+:\s+ON\s+(PK|LSC|HSC)\b", re.IGNORECASE)

_TYPE_MAP = {
    "PK": "peaking",
    "LSC": "lowshelf",
    "HSC": "highshelf",
}


def _slugify(name: str) -> str:
    """プロファイル名 → スキーマ準拠 ID (小英数・ハイフン・アンダースコア)。"""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if slug:
        return slug
    # スラグ化不能 (日本語名等) は名前のハッシュで一意化
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"autoeq-{digest}"


def parse_autoeq_text(text: str, name: str = "Custom AutoEq Profile") -> Optional[dict]:
    """AutoEq ParametricEQ.txt 形式のテキストをプロファイル JSON 辞書へ変換。

    Bisen parseAutoEqText() と同じ規約:
    - Preamp 行 → preamp_db (無ければ 0.0)
    - Filter 行 → bands (freq 整数丸め / gain 小数 1 位 / q 小数 2 位)
    - band は最大 10 個
    - 1 バンドも解析できなければ None

    Args:
        text: AutoEq テキスト
        name: プロファイル表示名

    Returns:
        スキーマ準拠プロファイル辞書、解析失敗時は None
    """
    if not text or not text.strip():
        return None

    preamp_db = 0.0
    bands: list[dict] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        m = _PREAMP_RE.search(line)
        if m:
            preamp_db = float(m.group(1))
            continue

        m = _FILTER_RE.search(line)
        if m:
            freq = float(m.group(1))
            gain = float(m.group(2))
            q = float(m.group(3))

            t = _TYPE_RE.search(line)
            band_type = _TYPE_MAP.get(t.group(1).upper()) if t else None
            if band_type is None:
                band_type = "peaking"  # Bisen 互換フォールバック

            bands.append({
                "type": band_type,
                "freq": int(round(freq)),
                "q": round(q, 2),
                "gain": round(gain, 1),
            })

    if not bands:
        return None

    return {
        "schema_version": 1,
        "id": _slugify(name),
        "type": "headphone",
        "name": name or "Custom Headphone",
        "source": "AutoEq ParametricEQ.txt",
        "purpose": "device_correction",
        "preamp_db": round(preamp_db, 1),
        "bands": bands[:10],
    }


def validate_autoeq_profile(profile: dict) -> tuple[bool, list[str]]:
    """解析結果をプロファイルスキーマで検証 (profiles.validate_profile に委譲)。"""
    from backend.dsp.profiles import validate_profile
    return validate_profile(profile)


def save_autoeq_profile(profile: dict) -> Optional[str]:
    """検証済みプロファイルを PROFILES_DIR へ永続化 (アトミック置換)。

    同名 ID の再インポートは上書き (= 再インポート冪等)。
    本関数は検証も行い、不正プロファイルは書き込まない。

    Returns:
        保存したプロファイル ID。検証失敗時は None。
    """
    from backend.dsp.profiles import PROFILES_DIR, ensure_profiles_dir

    valid, _errors = validate_autoeq_profile(profile)
    if not valid:
        return None

    ensure_profiles_dir()
    profile_id = profile["id"]
    path = PROFILES_DIR / f"{profile_id}.json"
    fd, tmp = tempfile.mkstemp(dir=str(PROFILES_DIR), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return profile_id
