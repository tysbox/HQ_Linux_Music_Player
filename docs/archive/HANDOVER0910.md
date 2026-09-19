# HANDOVER0910 — 開発経過記録（2026-09-10）

## 元の状態（コミット 9a372234 / rev20260907）
- ブランチ: `architecture-refactor-d`
- 修正完了: cycleDial修正、参照不一致防止策、B/C実装、D-2分離、D-3実機テスト、IR修正（enable_rate_adjust削除 + chunksize維持 + WET 20% + Church基準上書き）、ゲイン差解消（S32_LE統一 + final_headroom削除）
- 安定版 `rev20260907` 保護済み

## 今回の開発経過（2026-09-10）
1. クロスフィード原理確認（外部知識: Wikipedia Crossfeed / Interaural Time Difference）
2. デジタルクロスフィード実装（`backend/dsp/apply_logic.py` に `Delay` + `Gain` 減衰 + `Conv` 空間処理を追加、角度ベースパラメータ `Off-15-30-60-90`、距離パラメータ `0.5m-3m-20m`）
3. クロストーク打ち消し実装（`CROSSTALK_CANCEL_PARAMS`、逆位相混合 `inverted: True`、角度ベースパラメータ統一）
4. UI変更（`unified-shell/src/app/page.tsx` の `Preset` ダイヤルを廃止、`crossfeed` を角度ベースに変更、`distanceRatio` 追加、`cycleCrossfeed` / `handleCrossfeedChange` / `handleDistanceChange` 関数追加）
5. ビルドエラー発生（`reverbInt` 変数の削除ミス、`presetName` 参照残存、`enable_rate_adjust` のYAML残存）
6. 修正途中でユーザーから「直前のコミットへ戻して経過のみ残す」指示を受け、`git reset --hard 9a372234` を実行

## 最終状態（リセット後）
- `HEAD` は `9a372234`（`rev20260907` と同一）
- 作業ディレクトリはクリーン（`git status` で変更なし）
- `backend/dsp/apply_logic.py` は元のスタブ状態に戻っている（デジタルクロスフィードの追加はリセットにより消去）
- `unified-shell/src/app/page.tsx` は元の状態に戻っている（`Preset` ダイヤル残存、`crossfeed` は `none`/`light`/`standard` のまま）

## 学習記録
- デジタル（DSP）クロスフィードは `Delay`（遅延、`ITD` 模擬）+ `Gain`（減衰、`ILD` 模擬）+ `Conv`（空間処理、`HRTF` 模擬）の組み合わせで実現
- クロストーク打ち消しは逆位相の混合（`inverted: True`）を加えることで、スピーカーの自然な混合を打ち消す
- `CamillaDSP` の `Conv` は `Wav` ファイル（`IR`）を直接参照できるため、空間処理に利用可能
- `Biquad` Mixer はアナログ方式（`gain` のみ、遅延なし）であり、デジタル方式への変更には `Delay` フィルターの追加が必要
- `UI` 側のダイヤル変更（角度ベース、距離感バー）は `page.tsx` の `XF_OPTS` と `cycleCrossfeed` 関数の変更で対応可能
- `Preset` ダイヤルの廃止は `presetName` 関連変数とUI表示部分の削除で対応可能

## 次の課題（リセット後の状態から再開する場合）
- `D-4`: `main` ブランチへのマージ（`architecture-refactor-d` → `main`、安定版 `rev20260907` 保護済み、ユーザー承認待ち）
- `A`: 音質改善（`docs/A_measurement_steps.md` の手順実行、`IR` 測定ベース化）
- `B`: E2Eテスト拡充（`test_hq_api_compat.py` にDSP更新テスト追加）
- `C`: 運用強化（`monitor_services.sh` のcron自動化設定）
- クロスフィードUI変更（`Preset` ダイヤル廃止、角度ダイヤル + 距離感バー追加）はリセットにより消去されたため、再実装が必要
