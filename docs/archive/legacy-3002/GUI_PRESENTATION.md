# GUI 統合（port3002 unified-shell）提示ファイル一覧

このセッションで構築した「DSP/DMP 統合 GUI（iframe シェル方式）」の全容をクラウドAIエージェントに提示する際に必要なファイル。

---

## A. このセッションで新規構築した統合シェル（port3002）

### 必須（構造を理解するために必須）
| ファイル | 行数 | 役割 |
|---------|------|------|
| `unified-shell/src/app/page.tsx` | 1278 | 統合ページ（DMPタブUI + DSPモード切替を含む統合版） |
| `unified-shell/src/app/globals.css` | 179 | 統合UIのスタイル（3D flip、アルミパネル、オーク枠） |
| `unified-shell/src/app/layout.tsx` | 14 | レイアウト |
| `unified-shell/src/components/FlipTurn.tsx` | 0 | （空ファイル — このセッションでは未実装、CSSのみでflip実現） |
| `unified-shell/src/components/DSPMode.tsx` | 0 | （空ファイル） |
| `unified-shell/src/components/DMPMode.tsx` | 0 | （空ファイル） |

### 設定・ビルド
| ファイル | 役割 |
|---------|------|
| `unified-shell/package.json` | 依存（next 14, react 18, tailwind 3） |
| `unified-shell/tsconfig.json` | TypeScript 設定 |
| `unified-shell/next.config.js` | `output: standalone`（systemd配信用） |
| `unified-shell/postcss.config.js` | Tailwind v3 設定 |
| `unified-shell/tailwind.config.ts` | Tailwind 設定 |

### サービス登録
| ファイル | 役割 |
|---------|------|
| `unified-shell/unified-shell.service` | systemd unit（port3002） |

---

## B. 参照元（iframe で読み込む既存フロントエンド）

統合シェルは以下の2つをiframeで読み込むだけなので、**変更不要**。ただしクラウドAIが「統合の仕組み」を理解するために参照が必要。

### DSP 側（port3000）
| ファイル | 行数 | 役割 |
|---------|------|------|
| `frontend/src/app/page.tsx` | 869 | DSP専用UI（Dial、VUメーター、プリセット、モード切替） |
| `frontend/src/app/globals.css` | 60 | DSP UIスタイル（アルミパネル、オーク枠） |
| `frontend/src/app/layout.tsx` | 30 | レイアウト |

### DMP 側（port3001）
| ファイル | 行数 | 役割 |
|---------|------|------|
| `dmp/frontend/src/app/page.tsx` | 400 | DMP専用UI（Library/Queue/History/Playlistsタブ） |
| `dmp/frontend/src/app/globals.css` | 80 | DMP UIスタイル（ダークテーマ） |
| `dmp/frontend/src/app/layout.tsx` | 20 | レイアウト |

---

## C. バックエンド（無変更 — 参考情報として提示）

統合シェルはバックエンドを変更していない。CORSは既に `allow_origins=["*"]` で許可済み。

| ファイル | 役割 |
|---------|------|
| `backend/main.py` | DSPバックエンド（port8000） |
| `dmp/backend/app/main.py` | DMPバックエンド（port8001） |

---

## D. このセッションで変更したファイル（差分提示用）

クラウドAIに「何を変更したか」を明確に伝えるため、以下の差分を提示することを推奨。

1. **新規作成**: `unified-shell/` ディレクトリ全体（10ファイル、約200行のコード）
2. **変更なし**: `frontend/`（DSP）、`dmp/frontend/`（DMP）、`backend/`、`dmp/backend/`
3. **CSS変更**: `unified-shell/src/app/globals.css` の `.flip-btn`（アルミ＋オークの二重構造、角丸長方形、縦書きラベル、`⇋` glyph）
4. **HTML変更**: `unified-shell/src/app/page.tsx` の `.flip-btn-inner` 追加（アルミ盤面を内側に配置）
