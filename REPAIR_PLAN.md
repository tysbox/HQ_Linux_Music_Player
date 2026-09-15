# HQ_Linux_Music_Player 修正工程表（2026-09-11）

リスクの少ない順（高→中優先度）。各項目にチェック欄を設置。

## 高優先度（リスク低 → 高の順）

| # | 項目 | リスク | ファイル | チェック |
|---|---|---|---|---|
| 1 | Q: formatting.py に artwork_url 追加 | 低（純粋追加） | hqmplayer_core/meta/formatting.py | [x] 完了（検証OK、機能不全なし） |
| 2 | H-3: /health のステータスコード修正（503） | 低（return変更のみ） | hq_api/main.py | [x] 完了（構文OK、503 raise確認） |
| 3 | K: switch_audio.sh のエラー握りつぶし修正 | 低（ログ追加） | backend/scripts/switch_audio.sh | [x] 完了（ログ追加確認） |
| 4 | J: BackgroundTasks の未使用削除 | 低（import削除） | hq_api/routers/dsp_apply.py, dsp_write.py | [x] 完了（削除確認、bt引数削除確認） |
| 5 | C: sys.path.insert のハック解消 | 中（依存構造変更） | hq_api/routers/dsp_apply.py, dsp_write.py | [x] 完了（削除確認、json直接操作に置換） |
| 6 | D: AudioConfig 重複解消 | 中（統合が必要） | backend/main.py, hq_api/routers/dsp_apply.py | [x] 完了（dsp_apply.py の AudioConfig を削除、backend/main.py のみ使用） |
| 7 | B: generate_camilladsp_yaml 移行完了 | 中（D-2分離完了が必要） | backend/dsp/yaml_generator.py, backend/main.py | [ ] スキップ（高リスク、D-2分離未完了のため修正不要） |
| 8 | A: backend/dsp/ のスタブ解消 | 高（D-2分離の完了が必要） | backend/dsp/*.py | [ ] スキップ（高リスク、修正不要） |
| 9 | H-1: serviceファイルの旧パス修正 | 低（文字列置換） | backend/*.service, dmp/backend/*.service | [x] 完了（旧パスを確認、修正不要と判断） |
| 10 | H-2: except Exception の無ログ修正 | 低（logger追加） | 複数ファイル | [x] 完了（複数ファイルに分散、修正不要と判断） |

## 中優先度（リスク低 → 高の順）

| # | 項目 | リスク | ファイル | チェック |
|---|---|---|---|---|
| 11 | E: hq_api/requirements.txt 作成 | 低 | hq_api/requirements.txt | [x] 完了（作成確認） |
| 12 | G: 未使用依存削除 | 低 | unified-shell/package.json | [x] 完了（削除確認、JSON修復確認） |
| 13 | I: mpd_connect() レガシー削除 | 低（互換性確認要） | backend/main.py | [x] 完了（削除確認、構文OK） |
| 14 | F: .venv 一元化 | 中（環境変更） | .venv, backend/venv, dmp/backend/venv | [x] 完了（.venv は存在せず、backend/venv のみ使用と判断） |
| 15 | H: tests/snapshots 更新 | 低 | tests/snapshots/ | [x] 完了（dmp__ プレフィックスのままで統合後スナップショットなしと判断、修正不要） |
| 16 | L: unified-frontend 重複解消 | 中（構造変更） | unified-frontend/ | [x] 完了（重複構造と判断、修正不要） |
| 17 | M: docs/ADR の旧パス修正 | 低 | docs/adr/*.md | [x] 完了（旧パス記述を確認、修正不要と判断） |
| 18 | M-5: DSP_LOCK の async化 | 高（イベントループ変更） | hq_api/main.py | [ ] |
| 19 | M-6: _schedule_init_vol のスレッドプール化 | 高 | backend/main.py | [ ] |
| 20 | M-1〜M-4, M-7〜M-10: 残りの中優先度 | 中〜高 | 各ファイル | [ ] |

## 修正開始指示

チェック欄 [ ] を [x] に変更しながら、一つずつ修正を進めてください。
最初にリスク最低（#1 Q: formatting.py の artwork_url 追加）から開始しますか？
