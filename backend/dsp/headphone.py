#!/usr/bin/env python3
"""ホンキャリブレーション リキャリブレーション合成ロジック (Bisen移植 Phase 1 / Step 1-6c).

Bisen-DSP-System src/App.tsx の computeCorrectionBands() / resolveProfileById() 相当。

合成方式について (2026-10-12 設計判断):
  Bisen の簡易式「target.gain − listening.gain (周波数±5%マッチ)」は、リスニング
  補正を打ち消す向きに働くため「デフォルトで Harman 近似」が数学的に達成されない
  (コード内に "Simplified" と自認がある)。本実装は Android UI の操作体系
  (リスニング選択 + ターゲット選択[Harman既定/Flat/機種]) を維持しつつ、
  意図された機能を正確に実現するバンド連結方式を採る:

    実効補正 = C_L + (−C_T)

    C_L : リスニング機種の AutoEq 補正 (リスニング機種 → ターゲット[主にHarman])
    −C_T: ターゲット機種補正の逆 (ターゲット位置 → 機種の素の特性)
    結果: リスニング機種 → Harman 近似 → ターゲット機種の特性
          = 「選択したヘッドフォンの特性に近づける」(リキャリブレーション)

ターゲット種別 (headphone_target):
  - "harman" (既定): リスニング補正のみ (AutoEq ターゲット = 主に Harman へ近似)
  - "flat"       : リスニング補正のみ (同上。UI 表示上の区別。FIR 全帯域モード
                   導入時に厳密フラット化へ拡張予定)
  - "bypass"     : 補正なし (素の音)
  - "<機種ID>"   : リキャリブレーション (当該機種の特性へ近づける)
                   - インストール済みプロファイル → 同梱カタログ の順に解決
                   - リスニング機種と同一の場合は補正なし (Bisen 仕様:
                     listening.id === target.id → no correction)

実行 (単体テスト):
  ./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_headphone -v
"""

# 仮想ターゲット (Bisen HARMAN_REFERENCE / FLAT_REFERENCE / flat_bypass 相当。
# 実バンドを持たず、実効補正はリスニング補正のみ = AutoEq ターゲット近似)
VIRTUAL_TARGETS = {"harman", "flat", "bypass"}


def resolve_target_profile(target_id: str) -> dict | None:
    """ターゲット ID → 機種プロファイル辞書。

    仮想 ID ("harman"/"flat"/"bypass"/空) は None。
    機種 ID はインストール済みプロファイル (PROFILES_DIR) → 同梱カタログ の順に解決。
    Bisen resolveProfileById の「カタログも検索する」修正版に相当。
    """
    if not target_id or target_id in VIRTUAL_TARGETS:
        return None
    from backend.dsp.profiles import load_profile, load_catalog

    prof = load_profile(target_id)
    if prof is not None:
        return prof
    catalog = load_catalog()
    for entry in catalog.get("entries", []):
        p = entry.get("profile") or {}
        if entry.get("id") == target_id or p.get("id") == target_id:
            return p
    return None


def compute_effective_profile(listening_profile: dict, target_id: str) -> dict:
    """リスニングプロファイル × ターゲット → 実効プロファイル。

    Bisen App.tsx computeCorrectionBands() 相当 (合成方式は上記 docstring のとおり
    バンド連結)。戻り値は YAML 生成に渡す一時辞書であり、ディスク保存しないため
    スキーマ検証対象外 (妥当性は profile_to_biquads 内部検証が担保)。

    Args:
        listening_profile: 検証済みリスニングプロファイル辞書
        target_id: headphone_target 値 ("harman"/"flat"/"bypass"/機種ID)

    Returns:
        実効プロファイル辞書
    """
    if target_id == "bypass":
        # 素の音 (補正なし)
        return {**listening_profile, "preamp_db": 0.0, "bands": []}

    target = resolve_target_profile(target_id)
    if target is None:
        # 仮想 (harman/flat) または未解決 ID → リスニング補正のみ (既存動作保護)
        return listening_profile

    if target.get("id") == listening_profile.get("id"):
        # 同一機種: 補正なし (Bisen 仕様: listening.id === target.id)
        return {**listening_profile, "preamp_db": 0.0, "bands": []}

    # リキャリブレーション: リスニング補正 + ターゲット補正の逆
    bands = [
        {
            "type": b.get("type", "peaking"),
            "freq": b.get("freq", 1000.0),
            "q": b.get("q", 0.707),
            "gain": b.get("gain", 0.0),
        }
        for b in listening_profile.get("bands", [])
    ]
    for b in target.get("bands", []):
        bands.append({
            "type": b.get("type", "peaking"),
            "freq": b.get("freq", 1000.0),
            "q": b.get("q", 0.707),
            "gain": -float(b.get("gain", 0.0)),
        })
    # preamp はリスニング側のみ維持 (Bisen 仕様。ターゲット逆補正の preamp は
    # 音量上昇方向になり得るため不採用 — クリップ防止は Stage 2-5 自動ヘッドルームが担保)
    return {**listening_profile, "bands": bands}
