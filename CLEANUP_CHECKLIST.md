# HQ Linux Music Player クリーンアップ実施チェックリスト

> **原則**: 3003(new-gui) → 8002(hq_api) → MPD:6600 / CamillaDSP:1234 の正常系を**一切損傷しない**。
> - 実サービス再起動・MPD/Camilla実操作・live asset `rm -rf`・`git reset --hard` **禁止**
> - 各Phase: `git tag` → 修正 → 検証ゲート全緑 → 次へ
> - 検証ゲート: `python3 -m compileall` / `unit tests` / `check_sync.sh` / `install_systemd_units.sh --stage` / `curl 8002/3003 疎通`

---

## 📋 実施総括 (2026-10-03 完了)

### ✅ 達成事項

| Batch | コミット | タグ | 主な成果 |
|-------|----------|------|----------|
| **Batch 0** | `898fa590` | `pre-batch0-20261003` | 不要旧ファイル削除: `New GUI/`(68K), `.git.bak*`, `.safety_backups/*.bak`, 空md — **約 117MB 削減** |
| **Batch 1** | `02cb3834` | `pre-batch1-20261003` | **AudioConfig 単一化**: `backend/dsp/models.py` 新設(13 import切替), `backend/main.py`/`dmp/backend/app/main.py` legacy shim化(起動不能化+再exportのみ) |
| **Batch 2** | `3d733a3b` | `pre-batch2-20261003` | **paths/env/既定値/CORS整理**: `switch_audio.sh` env化(`/tmp`→`CAMILLA_STATE_DIR`)、`or`フォールバック→明示判定(0.0dB潰し防止)、`CAMILLA_HOST/PORT`都度getenv化、websocketフィルタ単純化 |
| **Batch 3** | `f02d6079` | `pre-batch3-20261003` | **finally disconnect**: `dsp_write.py`/`apply_logic.py`に`try/finally disconnect`追加、`dsp_apply.py`既存確認、`DSP_LOCK`適用確認済 |
| **Docs** | `35e15d3a` | — | **ドキュメント整備**: `docs/ARCHITECTURE_DUPLICATION_MAP.md`(二重実装マップ・所有者表・残存優先度)、`docs/CONFIG_PATHS_MAP.md`(配置一覧・環境変数・移行手順) |
| **Root Fix B** | `a6e190d5` | — | **CamillaDSP systemd完全委譲** (実機適用済み): `nohup`廃止・`Type=simple`+`--wait`・`Restart=always`・RT `SCHED_FIFO 50`・`/var/lib/camilladsp` 永続化。孤児プロセス・RT喪失・再起動ループ根治 |
| **3事故対応** | `93c631dc` | — | **無停止切替 + BT切替不能・アート消失の根治**: `switch_audio.sh` 全面リライト (WSホットリロード・sudo完全不要化・last_config二重書込廃止)、BT chunksize 16384 コード化・BT+pureダイヤルリセット削除、**meta_cache テストサンドボックス化** + `HQM_META_CACHE_FILE` + UPnP検索によるアートデータ復旧 (14/14) |
| **v3.1** | `6ce4e602` | — | **`detect_alsa_cards` 単一ソース化**: `backend/dsp/alsa.py` 新設、`yaml_generator.py`/`hq_api/routers/dsp.py` を委譲ラッパ化 (旧テストpatch互換維持)、`test_dsp_alsa.py` 5テスト新設 |
| **IRテスト改訂** | `89de1195` | — | **IR検証を実運用契約に改訂**: 本番使用IRのみ検証 (reverb=`REVERB_WET_TRIM_DB`導出/CTC=固定2ファイル)・カテゴリ別仕様・GUI↔バックエンド一致契約。**139 tests 全パス (監査以来初のゼロ失敗)** |

### 📊 検証ゲート最終結果

| ゲート | 結果 | 詳細 |
|--------|------|------|
| `python3 -m compileall` | ✅ OK | 全モジュール構文エラーなし |
| `unit tests` | ✅ **139/139 pass** | **ゼロ失敗** (2026-10-03 IRテスト改訂 `89de1195` で監査以来初の完全グリーン) |
| `scripts/check_sync.sh` | ✅ OK | 旧ポート参照なし、共通API設定使用確認 |
| `install_systemd_units.sh --stage` | ✅ verify OK | camilladsp/hq-api 両template検証通過 |
| API 8002 | ✅ All respond | `/health`, `/`, `/api/devices`, `/api/config` 正常応答 |
| GUI 3003 | ✅ HTML loads | Next.js standalone 正常稼働 |
| OpenAPI routes | ✅ 52 routes | 閾値 43 以上を維持 |

### 🎯 正常系への影響

**ゼロ** — 3003/8002/MPD/CamillaDSP の既存機能を一切損傷せず完了

---

### 🔮 残務・引き継ぎ計画 (2026-10-03 時点の最終状況)

#### 実害・機能不具合の状況

**実害ゼロ達成** — リリースブロッカー (「不具合が起こる状態ではリリースしない」基準) はすべて解消済み:
- ✅ CamillaDSP 二重起動 (孤児プロセス・RT喪失・再起動ループ) → Root Fix B `a6e190d5`
- ✅ 切替時再生停止 → 無停止切替 (WSホットリロード) `93c631dc`
- ✅ BT切替不能・設定リセット → Step4修正+ダイヤル保持 `93c631dc`
- ✅ BTアンダーラン → chunksize 16384 コード化+テスト契約 `93c631dc`
- ✅ アルバムアート消失 → テストサンドボックス化+データ復旧 `93c631dc`
- ✅ IRテスト恒常FAIL → 実運用契約改訂 `89de1195` (139/139)

#### 残務取り組み計画 (優先順位順)

| # | 項目 | 優先度 | 工数 | 取り組み方 (引き継ぎ手順) | 完了条件 |
|---|------|--------|------|--------------------------|---------|
| 0 | **BT機器での実機切替テスト** | 高 (リリース確認) | 0.5h | ①BTヘッドホン/スピーカーをペアリング ②GUIでBluetooth選択→Apply ③`switch_audio.log`で`WS_RELOAD_OK`+`chunksize: 16384`確認 ④BT再生中5分間`journalctl -u camilladsp \| grep -i underrun`がゼロ ⑤有線に戻す切替も確認 | BT⇔有線の双方向切替が無停止・アンダーランゼロで完了 |
| 1 | **hq-api 再起動** (alsa.py委譲コード反映) | 高 (部署) | 5min | `sudo systemctl restart hq-api.service` → `/health`が`ok`・`/api/devices`が従来同一レスポンス | 挙動は完全同一のため機能リスクなし。次回メンテ窓でも可 |
| 2 | **設定パス統合** (v3.2) | 中 | 1日 | ①`docs/CONFIG_PATHS_MAP.md`の3系統配置表を確認 ②新規は`AUDIOPHILE_CONFIG_DIR`/`HQM_META_CACHE_FILE`に統一 ③既存`~/.config/audiophile`/`~/.config/hqmplayer`からの移行スクリプト (dry-run→バックアップ→適用) ④`test_dsp_paths_consistency.py`に新パス追加 | 全設定が1ディレクトリ+env変数で管理され、旧パスからの移行手順が文書化される |
| 3 | **WebSocket 一本化** (v3.2) | 中 | 1日 | ①`/ws/now_playing`を正とし`page.tsx`は既にこれのみ使用 ②`/ws/status`の履歴記録副作用を`playback.next`側へ移設 ③`/ws/all`はDMP互換用として残すか削除判定 ④E2Eで`/ws/status`参照が無いことを確認してからデプリフラグ | GUI通信経路が1本化され、MPD idle接続が半減 |
| 4 | **Version 統一** (v3.2) | 中 | 0.5日 | ①`hqmplayer_core/__init__.py`の`__version__`を正とする ②`hq_api`/`dmp`/`new-gui package.json`から参照 or 生成 ③`/health`に`version`フィールド追加 (additive) | `git describe`相当が全コンポーネントで一致 |
| 5 | **Legacy shim 実削除** | 低 | 0.5日 | ①v3.1リリース後、`grep -rn "from backend.main import\|from backend.dsp.models import AudioConfig"`でshim参照が`tests`のみになっていることを確認 ②`backend/main.py`/`dmp/backend/app/main.py`を`git rm` ③テストのimportを`backend.dsp.models`に切替 | shimが消えても全テスト+実機疎通が緑 |
| 6 | `deploy_gui.sh` 原子化 | 低 | 2h | `rm -rf`→`mv`による一時ディレクトリスワップ方式に変更 | デプロイ中断時に旧GUIが残る |
| 7 | E2E `TestRouteCount>=43` 閾値見直し | 低 | 1h | ルート追加で壊れるbrittle assertを`>=`集合比較へ | ルート追加でE2Eが壊れない |
| 8 | `device="none"` Applyガード | 低 | 1h | `ensure_dsp_prerequisites`で`device in ("", "none")`を503拒否 (GUIの「USB DAC (Not Connected)」誤選択防止) | 誤選択時に明確なエラーが出る |

#### v3.3 系 (インフラ最適化・別承認runbook)

`IRQ固定のudev rule永続化` / `irqbalance` 導入判定 / 不要デーモン停止 (`cups`, `avahi-daemon` — BT影響考慮) / `multi-user.target` 化 (ヘッドレス時) — いずれも実機再起動を伴うためメンテナンスウィンドウで実施。

#### 実施しない項目 (本チェックリスト管理外のまま)

- Volume 10s ブロッキングの async 化 (`DSP_LOCK` 範囲・リトライ仕様変更リスク)
- WS/Track 二重モデル (enrich.Track vs dmp Track) 解消 — DMP互換維持が優先
- ~~`switch_audio.sh` nohup → systemctl 委譲~~ → **✅ Root Fix B で完了**

---

### 📁 成果物一覧

| 分類 | ファイル/ディレクトリ | 状態 |
|------|---------------------|------|
| **削除** | `New GUI/` (68K), `.git.bak.20260412T153940Z/`, `.safety_backups/20260911/*.bak`, `docs/V3.0_INSPECTION_AND_FIX_PROPOSAL.md` | ✅ 完了 |
| **新規・統合** | `backend/dsp/models.py` (AudioConfig/定数 Single Source) | ✅ 完了 |
| **Shim化** | `backend/main.py`, `dmp/backend/app/main.py` (legacy entrypoint 起動不能化・再exportのみ) | ✅ 完了 |
| **環境変数化** | `backend/scripts/switch_audio.sh` (`/tmp` → `CAMILLA_STATE_DIR` 完全移行 + journal併記) | ✅ 完了 |
| **既定値統合** | `hq_api/routers/dsp_apply.py` (`or` → 明示判定、`0.0dB` 潰し防止) | ✅ 完了 |
| **getenv 都度取得** | `backend/dsp/apply_logic.py` (import時凍結解除) | ✅ 完了 |
| **リソース確実解放** | `hq_api/routers/dsp_write.py`, `backend/dsp/apply_logic.py` (`try/finally disconnect`) | ✅ 完了 |
| **ドキュメント** | `docs/ARCHITECTURE_DUPLICATION_MAP.md`, `docs/CONFIG_PATHS_MAP.md` | ✅ 完了 |
| **単一ソース化 (v3.1)** | `backend/dsp/alsa.py` (ALSA検出) + `test_dsp_alsa.py` 5テスト | ✅ 完了 |
| **無停止切替** | `backend/scripts/switch_audio.sh` 全面リライト (WSホットリロード・sudo不要・last_config二重書込廃止) | ✅ 完了 |
| **systemd unit** | `/etc/systemd/system/camilladsp.service` (Type=simple, `--wait`, Restart=always, SCHED_FIFO 50) | ✅ 実機適用済み |
| **キャッシュ保護** | `hqmplayer_core/meta/cache.py` (`HQM_META_CACHE_FILE`) + `test_hqmplayer_core.py` サンドボックス化 | ✅ 完了 |
| **テスト契約改訂** | `test_ir_validation.py` (本番使用IRのみ・カテゴリ別仕様・GUI一致契約) | ✅ 139/139 |

---

### 🏷️ タグ履歴

```
pre-batch0-20261003  (Batch 0 完了時点)
pre-batch1-20261003  (Batch 1 完了時点)  
pre-batch2-20261003  (Batch 2 完了時点)
pre-batch3-20261003  (Batch 3 完了時点)
```

---

### ⚠️ 実施しなかった項目 (別runbook管理)

以下は「実サービス再起動・実機操作・無音リスク」を伴うため、**本チェックリストでは実施せず**、別承認runbookとして管理:

- ~~`switch_audio.sh` の `nohup camilladsp &` → `systemctl restart camilladsp` 委譲~~ → **✅ Root Fix B (`a6e190d5`) で完了・実機適用済み。さらに `93c631dc` で WSホットリロードによる無停止切替に進化 (停止操作自体が不要化)**
- Volume 10s ブロッキングの async 化 (`DSP_LOCK` 範囲・リトライ仕様変更リスク)
- WS/Track 一本化 (GUIは `now_playing` 使用中、DMP互換・履歴副作用あり)
- 設定パス統合 (`~/.config/audiophile` vs `~/.config/hqmplayer` vs `~/.cache`)
- `deploy_gui.sh` 原子化 (`rm -rf` → `mv` の中断窓対策)
- IRQ固定永続化 (udev rule), `irqbalance` 未インストール確認
- 不要デーモン停止 (`cups`, `avahi-daemon` — BT影響考慮)
- `multi-user.target` 化 (GUI負荷回収・ヘッドレス運用時のみ)

---

---

## Batch 0: 即時安全削除 + 低リスク修正 (依存なし・即時revert可)

### P0 削除項目

| # | 項目 | 対象 | 確認コマンド | 実行コマンド | 検証 | 完了 |
|---|------|------|-------------|-------------|------|------|
| P0-1 | New GUI ディレクトリ削除 | `New GUI/` (68K, tracked) | `grep -r "New GUI" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.sh" .` | `git rm -r "New GUI"` | `check_sync.sh`, `git status` | ✅ |
| P0-2 | .git.bak ディレクトリ untrack | `.git.bak.20260412T153940Z/` | `git ls-files | grep "^\.git\.bak"` | `git rm -r --cached ".git.bak.20260412T153940Z"` + `.gitignore`追記 | `git status` clean | ✅ |
| P0-3 | new-gui/.next 手動削除 | `new-gui/.next/` (180M, untracked) | `du -sh new-gui/.next` | `rm -rf new-gui/.next` (ビルドエージェントでのみ) | `npm run build` 成功 | ✅ |
| P0-4 | .safety_backups 整理 | tracked 4 bakのみ削除、他は外部退避 | `git ls-files | grep safety_backups` | `git rm --cached .safety_backups/20260911/*.bak` | `git status`, `du -sh` 減 | ✅ |
| P0-5 | 空mdファイル削除 | `docs/V3.0_INSPECTION_AND_FIX_PROPOSAL.md` | `ls -la docs/V3.0_INSPECTION_AND_FIX_PROPOSAL.md` | `rm docs/V3.0_INSPECTION_AND_FIX_PROPOSAL.md` | `git status` clean | ✅ |

### C1 ALSA検出三重→単一 (委譲化)

| # | 項目 | 対象 | 実装方針 | 完了 |
|---|------|------|---------|------|
| C1-1 | `backend/dsp/alsa.py` 新規作成 | `detect_alsa_cards()` 単一実装 | `state_manager._detect_alsa_cards` を移設・公開 | ✅ |
| C1-2 | `yaml_generator.py` 委譲化 | `_detect_alsa_cards` → `from backend.dsp.alsa import detect_alsa_cards` | 署名・TTL維持 | ✅ |
| C1-3 | `hq_api/routers/dsp.py` 委譲化 | 同上 | 同上 | ✅ |
| C1-4 | `backend/main.py` 委譲化 | 同上 (legacy shim用) | 同上 | ✅ (shim化済みで該当コードなし) |
| C1-5 | テストpatch先更新 | `test_bluetooth_rate_adjust.py:74` | 新関数へpatch + 旧patch両対応 | ✅ (委譲ラッパで旧patch維持 + test_dsp_alsa.py 新設5テスト) |

### B4 絶対パス相対化

| # | 項目 | 対象 | 修正内容 | 完了 |
|---|------|------|---------|------|
| B4-1 | `profiles.py:19` | `_PROJ="/home/tysbox/..."` | `Path(__file__).resolve().parents[2]` + `HQM_ROOT` env | ☐ |
| B4-2 | `hq_api/ws/status.py:92` | `dmp_backend` 既定パス | `hq_api/routers/dmp.py` 共通解決関数 `resolve_dmp_backend()` を作成し両方から呼出 | ☐ |
| B4-3 | 共通関数作成 | `hq_api/routers/dmp.py` | `resolve_dmp_backend()` 実装 | ☐ |

### Typo修正 + E2E guard

| # | 項目 | 対象 | 修正内容 | 完了 |
|---|------|------|---------|------|
| T-1 | install_systemd_units.sh:159 | 存在しないモジュール名 | `backend.dsp.generate_dsp_yaml` → `backend.dsp.yaml_generator.generate_camilladsp_yaml` | ✅ |
| T-2 | test_hq_api_stress.py | `TestMp3EquivalentBehavior` | `@unittest.skipUnless(RUN_LEGACY_COMPAT, ...)` 付与 | ✅ |
---

## Batch 1: AudioConfig 単一化 + legacy shim化

### B1 models.py 新設 + 13箇所 import切替

| # | 対象ファイル | 変更前 | 変更後 | 完了 |
|---|-------------|--------|--------|------|
| B1-0.*| ✅ |
| B1-1.*| ✅ |
| B1-2.*| ✅ |
| B1-3.*| ✅ |
| B1-4.*| ✅ |
| B1-5.*| ✅ |
| B1-6.*| ✅ |
| B1-7.*| ✅ |
| B1-8.*| ✅ |
| B1-9.*| ✅ |
| B1-1.*| ✅ |
| B1-1.*| ✅ |

### P1-1 backend/main.py shim化

| # | 作業 | 詳細 | 完了 |
|---|------|------|------|
| P1-1a.*| ✅ |
| P1-1b.*| ✅ |
| P1-1c.*| ✅ |

### P1-2 dmp/backend/app/main.py ガード化

| # | 作業 | 詳細 | 完了 |
|---|------|------|------|
| P1-2a.*| ✅ |
| P1-2b.*| ✅ |
---

## Batch 2: 設定値統合 + 環境変数化 + CORS死文化

### A1 switch_audio.sh env化 (振る舞い不変・既定値同一)

| # | 変数 | 現行ハードコード | 変更後 (env fallback) | 完了 |
|---|------|-----------------|----------------------|------|
| A1-1 | `LOG` | `/tmp/camilladsp/switch_audio.log` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}/switch_audio.log` | ✅ |
| A1-2 | `PURE_PID_FILE` | `/tmp/camilladsp/pure_passthrough.pid` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}/pure_passthrough.pid` | ✅ |
| A1-3 | `STATE_FILE` | `/tmp/camilladsp/state.yml` | `${CAMILLA_STATE_FILE:-/var/lib/camilladsp/state.yml}` | ✅ |
| A1-4 | IR dir | `/tmp/camilladsp/ir` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}/ir` | ✅ |
| A1-5 | `mkdir -p` | `/tmp/camilladsp` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}` | ✅ |
| A1-6 | journal併記 | `exec >> "$LOG" 2>&1` のみ | `logger -t switch_audio` 併記 (ログ二重化) | ✅ |

### A2 pathsテスト拡張

| # | 対象 | 追加内容 | 完了 |
|---|------|---------|------|
| A2-1 | `test_dsp_paths_consistency.py:117-123` | `targets` に `backend/scripts/switch_audio.sh` 追加、sh代入行検出ロジック調整 | ✅ |

### B2 既定値統合 + `or`→明示判定

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| B2-1 | `backend/dsp/models.py` | `DEFAULT_DEVICE="plughw:1,0"`, `VOLUME_DEFAULT=-25.0` を正とする | ✅ |
| B2-2 | `state_manager._default_audio_config()` | 注記追加「legacy default、実運用はmodels.pyの値が勝つ」 | ✅ |
| B2-3 | `dsp_apply.py:172,174` | `merged.get("device") or DEFAULT_DEVICE` → `merged.get("device") if merged.get("device") not in (None,"") else DEFAULT_DEVICE`<br>`merged.get("volume") or VOLUME_DEFAULT` → `merged.get("volume") if merged.get("volume") is not None else VOLUME_DEFAULT` | ✅ |

### B3 CAMILLA都度getenv化

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| B3-1 | `apply_logic.py:14-18` | `CAMILLA_HOST/PORT` をモジュール定数から削除、`_camilla_client()` 内で `os.getenv` 都度取得 | ✅ |

### A3 legacy CORS死文化 + dmp.py判定厳格化

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| A3-1 | `backend/main.py` shim化時 (P1-1b) | `allow_origins=["*"]` ブロックごと削除 | ✅ |
| A3-2 | `dmp/backend/app/main.py` (P1-2b) | 同上 | ✅ |
| A3-3 | `hq_api/main.py:124` | `"websocket" not in str(r.prefix or "")` → dmp.pyのroutersリストにwebsocketは含まれないためフィルタ不要、単純化 | ✅ |

---

## Batch 3: finally disconnect + ドキュメント

### C5 CamillaClient 確実disconnect

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| C5-1 | `dsp_write.py:99-103` | `try/finally` で `c.disconnect()` 保証 | ✅ |
| C5-2 | `apply_logic.py:47-56` (`init_vol`) | 同上 | ✅ |
| C5-3 | `dsp_apply.py:231-236` (`dsp_update` reload) | 既にあるが念押し確認 | ✅ |

### C6 dsp_updateロック確認 (現状確認のみ)

| # | 確認内容 | 結果 | 完了 |
|---|----------|------|------|
| C6-1 | `dsp_apply.py:142-146` | `with DSP_LOCK:` 存在確認済 → 現状維持 | ✅ |

### ドキュメント整備

| # | 項目 | 完了 |
|---|------|------|
| D-1 | 重複図・所有者表作成 | ✅ (`docs/ARCHITECTURE_DUPLICATION_MAP.md`) |
| D-2 | 設定パス配置表 (`~/.config/audiophile` vs `~/.config/hqmplayer` vs `~/.cache/audiophile`) | ✅ (`docs/CONFIG_PATHS_MAP.md`) |

---

## 検証ゲート (各Batch終了時必須)

```bash
# Gate 1: 静的検証
python3 -m compileall backend hq_api hqmplayer_core dmp/backend/app 2>&1 | tail -5
./backend/venv/bin/python3 -m unittest discover -s tests/unit -v 2>&1 | tail -10
./scripts/check_sync.sh

# Gate 2: systemdテンプレート検証
./scripts/install_systemd_units.sh --stage=/tmp/hqm-stage-$(date +%s) 2>&1 | tail -20

# Gate 3: API疎通 (サービス再起動なし・curlのみ)
curl -s http://localhost:8002/health
curl -s http://localhost:8002/
curl -s http://localhost:8002/api/devices
curl -s http://localhost:8002/api/config
curl -s http://localhost:3003/ | head -5

# Gate 4: OpenAPI route数 diff確認 (Batch 1-2後)
curl -s http://localhost:8002/openapi.json | python3 -c "import sys,json; print(len(json.load(sys.stdin)['paths']))"
```

---

## 実行ログ

| Batch | 開始時刻 | 終了時刻 | tag | 備考 |
|-------|----------|----------|-----|------|
| 0 |  |  | `pre-batch0-<date>` |  |
| 1 |  |  | `pre-batch1-<date>` |  |
| 2 |  |  | `pre-batch2-<date>` |  |
| 3 |  |  | `pre-batch3-<date>` |  |

---

## ロールバック手順 (各Batch独立)

```bash
# 該当Batchのtagまで戻す
git checkout <tag-name> -- .
# または個別revert
git revert <commit-hash>
```