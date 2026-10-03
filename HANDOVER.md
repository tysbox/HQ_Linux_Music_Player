# HANDOVER — Root Fix B 完了報告

## 実施内容サマリー

**Root Fix B (CamillaDSP systemd native化 + BTアンダーラン対策) 完了**

### 実施内容

| 項目 | 修正前 | 修正後 | 結果 |
|------|--------|--------|------|
| **camilladsp.service** | Type=notify, --notify | Type=simple, --wait | ✅ 起動安定化 |
| **switch_audio.sh** | nohup camilladsp & | systemctl reload/restart/start | ✅ systemd委譲完了 |
| **BT出力デバイス** | plug:bluealsa | bluealsa | ✅ BT出力動作確認済み |
| **アンダーラン対策** | chunksize=4096(21ms) | chunksize=16384 (85ms) | ✅ アンダーラン解消 |
| **last_config.json** | plug:bluealsa | bluealsa | ✅ 同期済み |
| **RT優先度** | 未適用 | SCHED_FIFO 50 | ✅ 適用済み |

### 作成・更新したファイル

| ファイル | 内容 |
|----------|------|
| /etc/systemd/system/camilladsp.service | Type=simple, --wait, Restart=always, RT SCHED_FIFO 50 |
| backend/scripts/switch_audio.sh | systemd委譲版 (nohup廃止、systemctl reload/restart/start使用) |
| /var/lib/camilladsp/active_dsp.yml | chunksize=16384, device=bluealsa, format=S16_LE |
| ~/.config/audiophile/last_config.json | device: bluealsa に修正 |
| staging/camilladsp.service | 本番適用用テンプレート |
| staging/switch_audio.sh | 本番適用用スクリプト |
| staging/verify_root_fix.sh | 6項目検証スクリプト |
| staging/rollback.sh | ロールバックスクリプト |
| docs/ARCHITECTURE_DUPLICATION_MAP.md | 二重実装マップ・所有者表・残存優先度 |
| docs/CONFIG_PATHS_MAP.md | 設定パス配置一覧・環境変数・移行手順 |

### 検証結果 ✅

| 項目 | 結果 |
|------|------|
| Service Active | ✅ Active |
| Port 1234 Listening | ✅ OK |
| DSP Connected (health) | ✅ connected |
| BT sink detected | ✅ true |
| RT Priority SCHED_FIFO 50 | ✅ Applied |
| Config Device | ✅ bluealsa |
| アンダーラン (過去5分間) | ✅ **ゼロ** |
| Config Device | ✅ bluealsa |

### 未完了課題 (CLEANUP_CHECKLIST.md 残存項目)

| 優先度 | 項目 | 見込み |
|--------|------|--------|
| 高 | detect_alsa_cards 完全委譲 (backend/dsp/alsa.py 新設) | 0.5日 |
| 高 | 設定パス統合 (audiophile vs hqmplayer vs cache) | 1日 |
| 高 | switch_audio.sh → systemctl restart camilladsp 委譲 | **実機適用済み** |
| 中 | WebSocket 一本化 (now_playing/status/all) | 1日 |
| 中 | Version 統一 (semver) | 0.5日 |
| 低 | CTC/CTC_response 等テスト分離 | 継続 |

### 次のアクション

1. **即時**: detect_alsa_cards 委譲 (backend/dsp/alsa.py 新設 → 3箇所委譲)
2. **次リリース**: 設定パス統合 (移行スクリプト・dry-run・ロールバック手順込み)
3. **別runbook**: switch_audio.sh → systemctl restart camilladsp 委譲 (実機適用済み)

---

**結論**: Root Fix B 完了。BT出力安定・アンダーラン解消・systemd管理下での安定動作を確認。

次のフェーズ: detect_alsa_cards 委譲・設定パス統合着手
