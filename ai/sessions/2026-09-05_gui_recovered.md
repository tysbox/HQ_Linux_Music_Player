# 2026-09-05 — GUI Recovered

## Status
**GUI Recovered ✅** — Unified-shell (port 3002) のパネルクリック不可事象を解消。

## Root cause
`unified-shell/src/app/page.tsx` の `data-dsp-swipe-handle` div が
`position: absolute; top:0; height:50; zIndex:4` で黒パネルの上端を覆い、
タブ行 (LIB/SRV/QUE/HIS/LIST) と右上の ▽DSP トリガーのクリックを
すべて吸収していた。

## Fix (commit 72de6459 on branch _recover)
- `data-dsp-swipe-handle` を 12px / z-index:1 / pointerEvents:none に縮小
- MODE/OUTPUT 丸ボタンを `w-20→w-24`、ラベルも大きく
- `TabSw` を `height:40→68`、アイコン 13→26、ラベル 7→14 に拡大
- タブ行に `paddingRight:130` を追加し ♡LIST と ▽DSP の重なりを解消
- ▽DSP を右上端 (`top:10/right:14`) に縦並び (DSP上/▽下) 配置
  ボタン風枠は撤廃してテキストのみ

## Validation
- 3002 HTTP 200 / 8002 HTTP 200
- MPD 13 tracks 連続再生中 (#5/13 → #6/13)
- meta_cache 13 entries populated
- 全 API endpoint 動作確認済み

## Side fixes included in same commit
- `backend/main.py`: headroom_db=-4.0 / final_headroom=-3.0 復元
- `dmp/backend/app/routers/playback.py`: meta_cache.enrich() 追加 (artwork対応)
- `hq_api/main.py`: CORS allow_credentials=False / queue_router 行撤去
- 新規ドキュメント: HANDOVER0904.md, docs/INVESTIGATION_REPORT_20260905.md

## Next
- CamillaDSP は Bluetooth A2DP 切断中のため停止中
  → ユーザが SOUNDPEATS を物理的に電源 ON で再開
- 13-track キューは維持済み
