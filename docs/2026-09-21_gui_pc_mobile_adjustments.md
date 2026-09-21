# 2026-09-21 GUI 調整記録 — PCコンソール（ポート3003）＆モバイル

対象ファイル:
- `new-gui/app/page.tsx`
- `new-gui/src/components/QueueView.tsx`

検証: `npx tsc --noEmit` / `npm run build` ともにエラー 0 件。

---

## 1. PC コンソール（ポート3003 / PCブラウザー用）

### 1-1. シャッフル・リピートボタンの色彩統一
- 以前: ON 時がエメラルドグリーン表示。
- 変更後: 通常時は他ボタンと同じ**ダークグレー**（`text-neutral-700`）、適用時（ON）のみ**薄いアンバー色のライト点灯**
  （`text-amber-400 drop-shadow-[0_0_6px_rgba(251,191,36,0.9)]`）。

### 1-2. MODE / OUT 表示ラベルの左右対称化
- 両ピルを固定幅 `w-48` に揃え、`justify-between` でパネル左右両端に**対称配置**。
- OUT 表示はデバイス名に応じて**省略表記**に変更（`shortOutLabel()` ヘルパーを追加）:
  - Bluetooth 系デバイス → `BT`
  - その他 → `SP/HP`
  - 未選択 → `SELECT`

### 1-3. VU メーターの振れ幅改善
- 以前: 再生中は常に `0.2〜0.95` のランダム値で、無音に近くても針が高レベルに張り付いていた。
- 変更後:
  - 振れ幅を **0.04〜0.50 に圧縮**
  - **マスターボリューム連動**（-40dB〜0dB → 0.15〜1.0 の係数）を追加。低ボリューム時は針がほとんど動かない。
- 依存配列に `volume` を追加し、ボリューム変更が即座に反映されるようにした。
- ※ 制限事項: MPD/CamillaDSP から実音声レベル（RMS）は取得できないため疑似メーターの改善。実信号連動にはバックエンドのレベル検出機能追加が必要。

### 1-4. プリセット登録パネルのレイアウト刷新
- PRESET ボタンを **SAVE と同サイズ**（`px-4 py-1.5 text-xs`）にし、**SAVE の真上（右端揃え）**に配置。
- プリセット名入力欄は左側に配置（2 行レイアウト）。Enter キーでも保存可。
- プリセットを Apply すると、PRESET グリーンボタンの位置に**プリセット名がダークグレー文字**で表示される（クリックで MANAGER 再オープン可）。未適用時は通常の PRESET ボタンに戻る。
- 以前の緑の「APPLIED」バナーは廃止。

### 1-5. プリセット POPUP（PRESET MANAGER）の再配置・配色変更
- 配置: 画面中央 → **コンソール右下**（`fixed items-end justify-end`、6ダイヤル下〜Save横ブラックパネル付近を覆う位置）。
- スタイル: **透明度 50% のダークグレー**（`bg-neutral-800/50` + `backdrop-blur-sm`）パネルに**赤系テキスト**（リスト・ボタン・入力欄すべて赤系で統一）。
- ※ モバイルでも同一モーダルを共用（右下寄せ表示）。

### 1-6. 選曲パネル（QUE タブ / QueueView.tsx）
- ヘッダー（`Queue — N tracks` 行）以外のテキストを **1 段階拡大**し、**オレンジ系（アンバー）**に変更:
  - 曲名（アーティスト — タイトル）: 10px → 12px、`#fbbf24`
  - アルバム名: 8px → 10px、`rgba(251,191,36,0.55)`
  - 時間表示: 8px → 10px、`rgba(251,191,36,0.45)`
  - 再生中の曲は従来通りグリーン（`var(--color-green)`）。
- **タッチ範囲の拡大**:
  - 行の最小高さを 44px にし、**行全体をワンクリックで再生**（以前はダブルクリックのみ）。
  - ヘッダーの SHUFFLE / CLEAR ボタン: 高さ 22px→30px、文字 7px→10px。
  - 各行の削除（✕）ボタン: 20×20 → 28×28。
- ※ 「全曲選択」ボタンは現行実装に存在しないため、SHUFFLE/CLEAR の拡大で代替。別途必要な場合は今後対応。

---

## 2. モバイルコンソール（`block lg:hidden`）

### 2-1. プレイ / シャッフル / リピート → PCコンソールと完全同一の色彩
- **シャッフル・リピート**: エメラルド表示を廃止し、PC と同一 — 通常時ダークグレー、ON 時アンバー発光。
- **プレイボタン**: PC と同一の構成に刷新
  - 再生中: `ring-2 ring-emerald-400/60` + 外側グロー `shadow 0 0 18px rgba(52,211,153,0.55)`
  - 停止中: `ring-1 ring-white/30 shadow-md`（シルバーアルミのみ）
  - アイコン: 再生中 `text-emerald-600` + 発光 / 停止中ダークグレー（白ハイライト付き）
  - 内側エメラルドボーダーオーバーレイも PC と同一クラス。

### 2-2. モバイル DSP パネルの PRESET 機能をコンソールと統一
- PRESET ボタンを SAVE と同サイズにし、SAVE の真上（右揃え）に配置。入力欄は左（PC と同じ 2 行レイアウト、Enter 保存対応）。
- 適用中はプリセット名をダークグレー文字で PRESET ボタンの位置に表示。緑の「APPLIED」バナーは廃止。
- POPUP（PRESET MANAGER）は PC と共通の右下寄せ・半透明ダークグレー/赤テキスト版を使用。

### 2-3. モバイル VU メーター（20 セグメント LED）
- LED バーは PC と同じ `vuL` 状態を参照するため、振れ幅圧縮＋ボリューム連動の改善がそのまま反映される。無音時・低ボリューム時は下部 1〜数セグのみ点灯。

---

## 3. LIB / SRV / HIS / LIST タブへの適用（4タブ全て）

QUE と同一仕様を、選曲パネルの全タブ（LIB / SRV / HIS / LIST）に適用:

| タブ | 対象ファイル | 変更 |
|---|---|---|
| QUE | `src/components/QueueView.tsx` | 曲名 12px `#fbbf24` / 副行情報 10px 半透明アンバー / 行 44px・ワンタップ再生 |
| LIB | `src/components/LibraryView.tsx` | フォルダ名・曲名 12px アンバー / 副行 10px / 行 44px・ワンタップ再生・✕拡大 |
| SRV | `src/components/SoundgenicView.tsx` | サーバー名 11px `rgba(251,191,36,0.85)` / フォルダ・曲 12px `#fbbf24` / 件数・パンくず 10〜11px 半透明 / 行 44px |
| HIS | `src/components/HistoryView.tsx` | 曲名 12px アンバー / 副行 10px / 行 44px・ワンタップ再生 / CLEAR ボタン拡大 |
| LIST | `src/components/PlaylistsView.tsx` | プレイリスト名 12px アンバー / 曲数 10px / 行 44px・ワンタップ再生 |

再生中の曲のみ従来通りグリーン表示。

---

## 4. MODE / OUT ラベル幅の再調整

- `w-48`（192px）→ **`w-[7.25rem]`（約116px）** に縮小（元の MODE 幅相当）。
- 左右対称配置（`justify-between`）は維持。OUT は `BT` / `SP/HP` の省略表記。

---

## 5. プリセット入力パネルの位置

- PRESET 入力用ブラックパネルは上段へ移動していたものを **下段 SAVE の左** へ戻した。
- 上段は PRESET ボタン（または適用中プリセット名・ダークグレー文字）を SAVE と同サイズで右揃え配置。

---

## 6. 障害対応記録: 「GUI 変更が反映されない」問題（根本原因と恒久対策）

### 6-1. 症状
- シャッフル/リピートのアンバー点灯、SRV/LIB 等のオレンジ文字が、ブラウザーのキャッシュ削除・再起動後も反映されない。

### 6-2. 調査結果（実機検証 / ライブ配信物の検査）
実クリックによる計算済みスタイル取得で、**配信中のビルドは正しく動作**していることを確認:

```
DESKTOP OFF      : shuffle=lab(27.036 0 0) / repeat=lab(27.036 0 0)   ← ダークグレー
DESKTOP クリックON: shuffle=lab(80.164 16.60 99.21) / repeat=同上        ← アンバー点灯
DESKTOP 再度OFF  : shuffle=lab(27.036 0 0) / repeat=lab(27.036 0 0)
MOBILE  OFF      : shuffle=lab(27.036 0 0) / repeat=lab(27.036 0 0)
MOBILE  ON       : shuffle=lab(80.164 16.60 99.21)
SRV タブ         : UPnP Server 11px / ミュージック 12px すべて rgb(251,191,36) 系
```
→ PC・モバイル両レイアウトで「通常=ダークグレー / ON=アンバー点灯」が正しく機能。

### 6-3. 根本原因（2件の複合）
1. **`npm run build` が `.next/standalone` を再生成する**ため、稼働中インスタンスが配信する
   `standalone/.next/static` が消える。→ ブラウザーは新チャンクを取得できず（404）、
   キャッシュを消しても表示が変わらない／壊れる。
2. **`systemctl restart` は非対話環境では認証が必要**（`Interactive authentication required`）。
   非対話実行するとプロンプト待ちでタイムアウトし、`ExecStartPre` の途中
   （`rm -rf` 後、`cp` 前）で中断されて静的アセットが消失する。

### 6-4. 恒久対策
- **GUI リビジョン表示 `GUI_REV` を追加**（PC: 下部フッター `GUI REV R6` / モバイル: 上部ステータス `REV R6`）。
  → ブラウザーが最新ビルドかどうかを一目で判定できる。
- **キャッシュ制御の強化**（`next.config.ts`）:
  - HTML: `Cache-Control: no-store, must-revalidate` ＋ `export const dynamic = 'force-dynamic'`
  - `/_next/static/*`: `immutable, max-age=31536000` → **`no-cache, must-revalidate`**（毎回 ETag 再検証）。
- **デプロイスクリプト `scripts/deploy_gui.sh` を追加**:
  「build → static/public を standalone へ原子的に反映 → サービス再起動 → HTTP 200 確認」を一括実行。
  以後の GUI 更新はこのスクリプトを使う（ビルドと再起動の分離による事故を防止）。
- 運用注意: **稼働中に `npm run build` だけを行わない**。必ず `scripts/deploy_gui.sh` か、
  ビルド直後の `cp -r .next/static .next/standalone/.next/` ＋ 再起動を行う。

### 6-5. 復旧手順（静的アセットが消えた場合）
```bash
cd new-gui
systemctl show audiophile-new-gui.service -p MainPID --value   # PID 確認
kill -9 <PID>            # Restart=on-failure により systemd が ExecStartPre 込みで再起動
sleep 10
ls .next/standalone/.next/static/chunks | wc -l                # 8 個あれば正常
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3003
```

