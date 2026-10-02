# HQ Linux Music Player クリーンアップ実施チェックリスト

> **原則**: 3003(new-gui) → 8002(hq_api) → MPD:6600 / CamillaDSP:1234 の正常系を**一切損傷しない**。
> - 実サービス再起動・MPD/Camilla実操作・live asset `rm -rf`・`git reset --hard` **禁止**
> - 各Phase: `git tag` → 修正 → 検証ゲート全緑 → 次へ
> - 検証ゲート: `python3 -m compileall` / `unit tests` / `check_sync.sh` / `install_systemd_units.sh --stage` / `curl 8002/3003 疎通`

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
| C1-1 | `backend/dsp/alsa.py` 新規作成 | `detect_alsa_cards()` 単一実装 | `state_manager._detect_alsa_cards` を移設・公開 | ☐ |
| C1-2 | `yaml_generator.py` 委譲化 | `_detect_alsa_cards` → `from backend.dsp.alsa import detect_alsa_cards` | 署名・TTL維持 | ☐ |
| C1-3 | `hq_api/routers/dsp.py` 委譲化 | 同上 | 同上 | ☐ |
| C1-4 | `backend/main.py` 委譲化 | 同上 (legacy shim用) | 同上 | ☐ |
| C1-5 | テストpatch先更新 | `test_bluetooth_rate_adjust.py:74` | 新関数へpatch + 旧patch両対応 | ☐ |

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
| B1-0 | `backend/dsp/models.py` 新規 | - | `AudioConfig, StoredAudioConfig, VolumeControl, DspParams, DEFAULT_DEVICE, VOLUME_DEFAULT` 定義 | ☐ |
| B1-1 | `hq_api/routers/dsp_apply.py:42` | `from backend.main import AudioConfig` | `from backend.dsp.models import AudioConfig` | ☐ |
| B1-2 | `hq_api/routers/dsp_apply.py:177` | `from backend.main import AudioConfig as BackendAudioConfig` | `from backend.dsp.models import AudioConfig as BackendAudioConfig` | ☐ |
| B1-3 | `backend/dsp/state_manager.py:124` | `from backend.main import AudioConfig` | `from backend.dsp.models import AudioConfig` | ☐ |
| B1-4 | `tests/tools/dsp_probe.py:31` | `from backend.main import AudioConfig` | `from backend.dsp.models import AudioConfig` | ☐ |
| B1-5 | `tests/unit/test_camilladsp_yaml_schema.py:28` | 同上 | 同上 | ☐ |
| B1-6 | `tests/unit/test_crossfeed_structure.py:20` | 同上 | 同上 | ☐ |
| B1-7 | `tests/unit/test_ctc_response.py:19` | 同上 | 同上 | ☐ |
| B1-8 | `tests/unit/test_dsp_applied.py:18` | 同上 | 同上 | ☐ |
| B1-9 | `tests/unit/test_dsp_gain_margin.py:18` | 同上 | 同上 | ☐ |
| B1-10 | `tests/unit/test_dsp_yaml_snapshot.py:23` | 同上 | 同上 | ☐ |
| B1-11 | `tests/unit/test_no_live_write.py:27` | 同上 | 同上 | ☐ |

### P1-1 backend/main.py shim化

| # | 作業 | 詳細 | 完了 |
|---|------|------|------|
| P1-1a | `AudioConfig` 再export | `from backend.dsp.models import AudioConfig, StoredAudioConfig, VolumeControl, DspParams` のみ残す | ☐ |
| P1-1b | デッドコード削除 | `lifespan`, `_playback_watchdog`, `_restore_last_config`, `mpd_connect`, `WSManager`, `_detect_alsa_cards` 委譲化, `_get_available_devices`, `FastAPI app/CORS *` 全削除 | ☐ |
| P1-1c | ガード追加 | ファイル先頭に `raise RuntimeError("legacy entrypoint - use hq_api")` | ☐ |

### P1-2 dmp/backend/app/main.py ガード化

| # | 作業 | 詳細 | 完了 |
|---|------|------|------|
| P1-2a | 起動ガード | 先頭に `raise RuntimeError("legacy DMP entrypoint - use hq_api")` | ☐ |
| P1-2b | CORS * 削除 | `allow_origins=["*"]` ブロック削除 | ☐ |
---

## Batch 2: 設定値統合 + 環境変数化 + CORS死文化

### A1 switch_audio.sh env化 (振る舞い不変・既定値同一)

| # | 変数 | 現行ハードコード | 変更後 (env fallback) | 完了 |
|---|------|-----------------|----------------------|------|
| A1-1 | `LOG` | `/tmp/camilladsp/switch_audio.log` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}/switch_audio.log` | ☐ |
| A1-2 | `PURE_PID_FILE` | `/tmp/camilladsp/pure_passthrough.pid` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}/pure_passthrough.pid` | ☐ |
| A1-3 | `STATE_FILE` | `/tmp/camilladsp/state.yml` | `${CAMILLA_STATE_FILE:-/var/lib/camilladsp/state.yml}` | ☐ |
| A1-4 | IR dir | `/tmp/camilladsp/ir` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}/ir` | ☐ |
| A1-5 | `mkdir -p` | `/tmp/camilladsp` | `${CAMILLA_STATE_DIR:-/var/lib/camilladsp}` | ☐ |
| A1-6 | journal併記 | `exec >> "$LOG" 2>&1` のみ | `logger -t switch_audio` 併記 (ログ二重化) | ☐ |

### A2 pathsテスト拡張

| # | 対象 | 追加内容 | 完了 |
|---|------|---------|------|
| A2-1 | `test_dsp_paths_consistency.py:117-123` | `targets` に `backend/scripts/switch_audio.sh` 追加、sh代入行検出ロジック調整 | ☐ |

### B2 既定値統合 + `or`→明示判定

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| B2-1 | `backend/dsp/models.py` | `DEFAULT_DEVICE="plughw:1,0"`, `VOLUME_DEFAULT=-25.0` を正とする | ☐ |
| B2-2 | `state_manager._default_audio_config()` | 注記追加「legacy default、実運用はmodels.pyの値が勝つ」 | ☐ |
| B2-3 | `dsp_apply.py:172,174` | `merged.get("device") or DEFAULT_DEVICE` → `merged.get("device") if merged.get("device") not in (None,"") else DEFAULT_DEVICE`<br>`merged.get("volume") or VOLUME_DEFAULT` → `merged.get("volume") if merged.get("volume") is not None else VOLUME_DEFAULT` | ☐ |

### B3 CAMILLA都度getenv化

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| B3-1 | `apply_logic.py:14-18` | `CAMILLA_HOST/PORT` をモジュール定数から削除、`_camilla_client()` 内で `os.getenv` 都度取得 | ☐ |

### A3 legacy CORS死文化 + dmp.py判定厳格化

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| A3-1 | `backend/main.py` shim化時 (P1-1b) | `allow_origins=["*"]` ブロックごと削除 | ☐ |
| A3-2 | `dmp/backend/app/main.py` (P1-2b) | 同上 | ☐ |
| A3-3 | `hq_api/routers/dmp.py:24` | `"websocket" not in str(r.prefix or "")` → `getattr(r, "tags", None) != ["websocket"]` 等の明示判定 | ☐ |

---

## Batch 3: finally disconnect + ドキュメント

### C5 CamillaClient 確実disconnect

| # | 対象 | 修正内容 | 完了 |
|---|------|---------|------|
| C5-1 | `dsp_write.py:99-103` | `try/finally` で `c.disconnect()` 保証 | ☐ |
| C5-2 | `apply_logic.py:47-56` (`init_vol`) | 同上 | ☐ |
| C5-3 | `dsp_apply.py:231-236` (`dsp_update` reload) | 既にあるが念押し確認 | ☐ |

### C6 dsp_updateロック確認 (現状確認のみ)

| # | 確認内容 | 結果 | 完了 |
|---|----------|------|------|
| C6-1 | `dsp_apply.py:142-146` | `with DSP_LOCK:` 存在確認済 → 現状維持 | ☐ |

### ドキュメント整備

| # | 項目 | 完了 |
|---|------|------|
| D-1 | 重複図・所有者表作成 | ☐ |
| D-2 | 設定パス配置表 (`~/.config/audiophile` vs `~/.config/hqmplayer` vs `~/.cache/audiophile`) | ☐ |

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