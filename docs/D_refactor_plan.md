# D（アーキテクチャ）別ブランチ計画 — architecture-refactor-d

目標: `backend/main.py`（939行）のYAML生成とDSP制御をモジュール分割

分割案（3モジュール）
1. `backend/dsp/yaml_generator.py` — `generate_camilladsp_yaml()` のみ
2. `backend/dsp/state_manager.py` — `state_file_path` / `-s` オプション管理
3. `backend/dsp/apply_logic.py` — `/api/apply` の再起動・音量復帰ロジック

実機テストが必要な段階
- 各モジュールを分離後、`camilladsp --check` でYAML検証（手動実行不要、コードレベルで確認可能）
- 実機テストが必要なのは「分割後の統合テスト」（`/api/apply` → DSP再起動 → 音量復帰の一連の流れ）
- その段階で通知します

現在の進捗
- ブランチ `architecture-refactor-d` 作成済み（`9a372234` から分岐）
- 安定版 `rev20260907` は保護済み
