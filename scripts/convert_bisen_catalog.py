#!/usr/bin/env python3
"""Bisen ヘッドホンカタログ (TS) → config/profiles/catalog.json 変換スクリプト.

Bisen-DSP-System の計測データカタログを本リポジトリのプロファイル JSON スキーマ
に準拠した形式へ一括変換する (Phase 1 / Step 1-3b — 利用者指示による D-4 改訂)。

入力 (Bisen ローカルクローン):
  - src/dsp/headphoneCatalog.ts                 (定番 45 機種)
  - src/dsp/headphoneCatalog_oratory_crinacle.ts (oratory1990/crinacle 2,771 機種)

出力:
  - config/profiles/catalog.json (同梱カタログ。GET /api/dsp/headphones/catalog
    の検索ソース + 取込み元)

変換規約:
  - 各エントリは完全なスキーマ準拠プロファイルとして事前検証する。
  - 検証不合格 (正ゲイン合計 >20dB 等) は除外し、件数と理由を報告する。
  - 既存の同梱プロファイル (config/profiles/*.json) と ID が重複する機種は
    「重複」として除外する (既存を保護)。

実行:
  ./backend/venv/bin/python3 scripts/convert_bisen_catalog.py
"""
import json
import os
import re
import sys

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
BISEN_REPO = os.environ.get(
    "BISEN_REPO", "/home/tysbox/Bisen-DSP-System")
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from backend.dsp.profiles import validate_profile  # noqa: E402

SOURCES = [
    # (パス, 出典ラベル)
    (os.path.join(BISEN_REPO, "src/dsp/headphoneCatalog.ts"),
     "AutoEq/oratory1990 — Bisen headphoneCatalog.ts (定番カタログ)"),
    (os.path.join(BISEN_REPO, "src/dsp/headphoneCatalog_oratory_crinacle.ts"),
     "AutoEq (oratory1990/crinacle 測定) — Bisen headphoneCatalog_oratory_crinacle.ts"),
]

ID_RE = re.compile(r"^\s*id:\s*'(.+?)',?\s*$")
BRAND_RE = re.compile(r"^\s*brand:\s*'(.+?)',?\s*$")
MODEL_RE = re.compile(r"^\s*model:\s*'(.+?)',?\s*$")
TARGET_RE = re.compile(r"^\s*targetCurve:\s*'(.+?)',?\s*$")
PREAMP_RE = re.compile(r"^\s*preampGainDb:\s*(-?[\d.]+),?\s*$")
POPULARITY_RE = re.compile(r"^\s*popularity:\s*(\d+),?\s*$")
FORMFACTOR_RE = re.compile(r"^\s*formFactor:\s*'([^']+?)',?\s*$")
BAND_RE = re.compile(
    r"^\s*\{\s*freq:\s*([\d.]+),\s*gain:\s*(-?[\d.]+),"
    r"\s*q:\s*([\d.]+),\s*type:\s*'(\w+)'")


def _unescape(s: str) -> str:
    """TS 文字列の簡易エスケープ解除 (\\' → ')。"""
    return s.replace("\\'", "'")


def _slugify_id(entry_id: str) -> str:
    """カタログエントリ ID → スキーマ準拠プロファイル ID (決定的)。"""
    return re.sub(r"[^a-z0-9]+", "-", entry_id.lower()).strip("-")


def _map_target_curve(tc: str) -> str:
    """Bisen targetCurve 文字列 → スキーマ enum。元の文字列は notes に残す。"""
    t = tc.lower()
    if "harman" in t and "2013" in t:
        return "harman_2013"
    if "harman" in t:
        # AutoEq/oratory の Harman 系ターゲットは 2018 準拠が主
        return "harman_2018"
    if "diffuse" in t:
        return "diffuse_field"
    return "custom"


def parse_ts_entries(path: str) -> list:
    """TS カタログファイルから CatalogEntry を抽出する。"""
    entries = []
    current = None
    in_bands = False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")

            m = ID_RE.match(line)
            if m and not in_bands:
                current = {"id": _unescape(m.group(1)), "bands": []}
                entries.append(current)
                continue
            if current is None:
                continue

            if "bands: [" in line:
                in_bands = True
                continue
            if in_bands and "]" in line and "freq" not in line:
                in_bands = False
                continue
            if in_bands:
                mb = BAND_RE.match(line)
                if mb:
                    current["bands"].append({
                        "type": mb.group(4),
                        "freq": float(mb.group(1)),
                        "q": float(mb.group(3)),
                        "gain": float(mb.group(2)),
                    })
                continue

            m = BRAND_RE.match(line)
            if m:
                current["brand"] = _unescape(m.group(1))
                continue
            m = MODEL_RE.match(line)
            if m:
                current["model"] = _unescape(m.group(1))
                continue
            m = TARGET_RE.match(line)
            if m:
                current["targetCurve"] = _unescape(m.group(1))
                continue
            m = PREAMP_RE.match(line)
            if m:
                current["preampGainDb"] = float(m.group(1))
                continue
            m = POPULARITY_RE.match(line)
            if m:
                current["popularity"] = int(m.group(1))
                continue
            m = FORMFACTOR_RE.match(line)
            if m:
                current["formFactor"] = m.group(1)
                continue
    return entries


def _to_catalog_entry(raw: dict, source_label: str) -> dict:
    """生エントリ → カタログエントリ (実体化済みプロファイル込み)。"""
    profile_id = _slugify_id(raw["id"])
    brand = raw.get("brand", "Unknown")
    model = raw.get("model", "Unknown")
    target = raw.get("targetCurve", "custom")
    # ゼロゲインバンドは無効化されたノーオペレーション (0dB) のため除外する
    # (パイプラインに無駄な Biquad を置かない。2026-10-12: 54 バンド該当)。
    bands = [
        {
            "type": b["type"],
            "freq": round(float(b["freq"]), 1),
            "q": round(float(b["q"]), 2),
            "gain": round(float(b["gain"]), 1),
        }
        for b in raw.get("bands", [])
        if abs(float(b["gain"])) > 1e-9
    ]
    name = f"{brand} {model}"
    notes = f"ターゲットカーブ: {target}"
    if len(name) > 64:
        # スキーマ name 上限 64 文字。全文は notes に保存して切り詰める。
        notes = f"{notes} / 正式名称: {name}"
        name = name[:61] + "..."
    profile = {
        "schema_version": 1,
        "id": profile_id,
        "type": "headphone",
        "name": name,
        "source": source_label,
        "purpose": "device_correction",
        "preamp_db": round(float(raw.get("preampGainDb", 0.0)), 1),
        "target_curve": _map_target_curve(target),
        "notes": notes,
        "bands": bands,
    }
    return {
        "id": raw["id"],  # カタログ参照 ID (そのまま)
        "brand": brand,
        "model": model,
        "form_factor": raw.get("formFactor"),
        "target_curve_label": target,
        "popularity": raw.get("popularity", 0),
        "profile": profile,
    }


def main() -> int:
    # 既存の同梱プロファイル ID (重複保護)
    bundled_dir = os.path.join(_PROJ, "config", "profiles")
    bundled_ids = set()
    if os.path.isdir(bundled_dir):
        for name in os.listdir(bundled_dir):
            if name.endswith(".json") and name != "catalog.json":
                bundled_ids.add(name[:-len(".json")])

    catalog_entries = []
    seen_ids = set()
    stats = {"parsed": 0, "imported": 0, "invalid": 0,
             "duplicate_id": 0, "bundled_dup": 0, "band_anomaly": 0}
    invalid_reasons = {}

    for path, label in SOURCES:
        if not os.path.exists(path):
            print(f"ERROR: source not found: {path}")
            return 1
        raw_entries = parse_ts_entries(path)
        stats["parsed"] += len(raw_entries)
        for raw in raw_entries:
            if raw["id"] in seen_ids:
                stats["duplicate_id"] += 1
                continue
            seen_ids.add(raw["id"])

            entry = _to_catalog_entry(raw, label)
            profile = entry["profile"]

            if profile["id"] in bundled_ids:
                stats["bundled_dup"] += 1
                continue

            valid, errors = validate_profile(profile)
            if not valid:
                stats["invalid"] += 1
                reason = errors[0] if errors else "unknown"
                invalid_reasons[reason] = invalid_reasons.get(reason, 0) + 1
                continue
            if len(profile["bands"]) == 0:
                stats["band_anomaly"] += 1
                continue

            catalog_entries.append(entry)
            stats["imported"] += 1

    catalog = {
        "schema_version": 1,
        "generated_at": "2026-10-12",
        "source": ("Bisen-DSP-System headphoneCatalog.ts (45) + "
                    "headphoneCatalog_oratory_crinacle.ts (2771) — "
                    "AutoEq (jaakkopasanen), oratory1990/crinacle 測定"),
        "total": len(catalog_entries),
        "entries": catalog_entries,
    }

    out_path = os.path.join(_PROJ, "config", "profiles", "catalog.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"parsed={stats['parsed']} imported={stats['imported']} "
          f"invalid={stats['invalid']} bundled_dup={stats['bundled_dup']} "
          f"duplicate_id={stats['duplicate_id']} band_anomaly={stats['band_anomaly']}")
    if invalid_reasons:
        print("invalid reasons:")
        for reason, count in sorted(invalid_reasons.items(),
                                    key=lambda kv: -kv[1]):
            print(f"  [{count:4d}] {reason[:120]}")
    print(f"catalog: {out_path} ({size_mb:.2f} MB, {len(catalog_entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

