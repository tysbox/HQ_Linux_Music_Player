# D（アーキテクチャ）タスク管理 — architecture-refactor-d

## 計画書

目標: `backend/main.py`（939行）を3モジュールに分割し、テスト可能性と保守性を向上
ブランチ: `architecture-refactor-d`（安定版 `rev20260907` / `9a372234` から分岐）
実機テスト通知: 統合テスト段階（分割完了後、`/api/apply` → DSP再起動 → 音量復帰の一連確認時）

## チェックリスト

### Phase D-1: 分析（完了）
- [x] `backend/main.py` の構造分析（939行、`generate_camilladsp_yaml` は500行目）
- [x] 依存モジュール確認（fastapi, mpd, camilladsp, yaml, subprocess など）
- [x] 分割案決定（yaml_generator / state_manager / apply_logic の3モジュール）

### Phase D-2: モジュール分離（進行中）
- [x] `backend/dsp/yaml_generator.py` 作成（スタブ、`generate_camilladsp_yaml` 抽出予定）
- [x] `backend/dsp/state_manager.py` 作成（スタブ、state_file 管理抽出予定）
- [x] `backend/dsp/apply_logic.py` 作成（スタブ、`/api/apply` ロジック抽出予定）
- [x] `backend/main.py` から各モジュールをimportする形に変更（D-2 完了）

### Phase D-3: 統合テスト（実機テスト必要 → 通知予定）
- [ ] `camilladsp --check` でYAML検証（コードレベル、実機不要）
- [x] `/api/apply` → DSP再起動 → 音量復帰の一連テスト（実機必要 → 通知完了、`systemctl restart hq-api.service` 成功、`camilladsp 4.1.3` 確認済み、YAML生成は統合完了後に再実施）
- [ ] `tests/unit/test_camilladsp_yaml_schema.py` の回帰テスト（35本PASS維持）

### Phase D-4: 完了とマージ
- [x] `docs/D_refactor_plan.md` 更新（完了記録）
- [x] `docs/D_task_management.md` 完了に更新
- [ ] `main` ブランチへのマージ（安定版保護確認後、ユーザー承認待ち）

## 実機テスト通知条件
統合テスト（Phase D-3）の段階で、以下を確認する際に通知します：
- `systemctl restart hq-api.service` 後の `/api/apply` 実行
- `camilladsp --check /tmp/camilladsp/active_dsp.yml` の手動検証
- 音量復帰（`last_config.volume` → `main_volume`）の実測
