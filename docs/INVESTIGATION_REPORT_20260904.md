# 調査レポート & 修正提案書: unified-shell (3002) + hq_api (8002)

**作成日時**: 2026-09-04 09:45 JST
**調査者**: GitHub Copilot
**対象ブランチ**: `_recover` (HEAD `750135b2`)
**作業ディレクトリ**: `/home/tysbox/HQ_Linux_Music_Player/unified-shell/`

---

## 1. エグゼクティブサマリ

unified-shell (port 3002) と hq_api (port 8002) の統合フロントエンド/バックエンドについて、コード読取・実HTTP/WSリクエスト検証・ブラウザスナップショット確認を実施。**8つの重大・中程度の問題**を特定。特に **systemd サービスが死んでいる**、**CORS がブラウザでブロックされる**、**シークバーが動かない**、**トランスポートボタンが反応しない** の4点は即時対応必須。

---

## 2. 現状アーキテクチャ概要

```
┌─────────────────────────────────────────────────────────────────┐
│ ブラウザ (port 3002)                                            │
│  ├─ Next.js 16.2.1 (dev-server, NODE_ENV=development)          │
│  ├─ WebSocket → /ws/now_playing (2秒 polling)                  │
│  ├─ REST API → /api/playback/*, /api/volume, /api/apply, etc.  │
│  └─ 静的アセット → /_next/static/...                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ hq_api (port 8002, FastAPI + uvicorn)                          │
│  ├─ CORSMiddleware (allow_origins=["*"], allow_credentials=True)│
│  ├─ /ws/now_playing ──→ MPD (port 6600) 2秒 polling            │
│  ├─ /ws/status ──→ MPD idle() イベント駆動                      │
│  ├─ /ws/all ──→ 統合 WebSocket                                  │
│  ├─ /api/playback/* ──→ DMP playback router → MPD              │
│  ├─ /api/volume ──→ CamillaClient (127.0.0.1:1234) [❌未起動]   │
│  ├─ /api/apply ──→ switch_audio.sh + CamillaDSP 再起動          │
│  ├─ /api/devices ──→ aplay -l subprocess                        │
│  ├─ /api/config ──→ ~/.config/audiophile/last_config.json       │
│  └─ /api/art ──→ iTunes Search API (リダイレクト)               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 特定された問題点 (優先度順)

### 🔴 P0-1: `.transport-label` CSS クラスが globals.css に未定義

**現象**: `page.tsx` で `className='transport-label'` を使用しているが、CSS で定義されていない。

**検証**:
```bash
$ grep -n "transport-label" src/app/globals.css
EXIT:1  # マッチなし
```

**影響**:
- インライン style のみ (`padding: '4px 12px'`, `minWidth: 48-80px`)
- 文字サイズ 22-48px に対して padding 4px では **ヒットエリアが極小**
- タッチデバイスで文字以外をタップしても反応しない

**関連ファイル**: `src/app/globals.css`, `src/app/page.tsx` (L54)

---

### 🔴 P0-2: CORS がブラウザでブロックされる

**現象**: curl では `access-control-allow-origin: *` が返るが、Chrome でブロックされる。

**検証**:
```bash
# curl では通る
$ curl -X POST http://localhost:8002/api/playback/seek -H "Origin: http://localhost:3002" -i
access-control-allow-origin: *
access-control-allow-credentials: true

# ブラウザコンソール
Access to fetch at 'http://localhost:8002/api/playback/seek' from origin 'http://localhost:3002'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present
```

**根因**: `CORSMiddleware` で `allow_origins=["*"]` と `allow_credentials=True` を同時指定。CORS 仕様上、**credentials 付きリクエストには wildcard 不可**。Chrome は strict に拒否。

**関連ファイル**: `hq_api/main.py` (L24-29)

---

### 🔴 P0-3: unified-shell.service が死亡、standalone ビルド不存在

**現象**: systemd サービスが 1日以上前に終了。本番用ビルドが存在しない。

**検証**:
```bash
$ systemctl status unified-shell
Active: inactive (dead) since Thu 2026-09-03 12:17:05 JST

$ ls /home/tysbox/HQ_Linux_Music_Player/unified-shell/.next/standalone/
ls: アクセスできません: そのようなファイルやディレクトリはありません
```

**現状**: port 3002 は **開発用 dev-server** (PID 390302, `NODE_ENV=development`, `__NEXT_DEV_SERVER=1`) が動いているのみ。service 再起動時に `.next/standalone/server.js` が無いため **起動失敗する**。

**関連ファイル**: `/etc/systemd/system/unified-shell.service`, `package.json` (build script)

---

### 🔴 P0-4: シークバーが位置変更不可

**現象**: 再生中、シークバー (input type=range) をドラッグ/クリックしても再生位置が変わらない。

**根因 (3重)**:

1. **WebSocket が controlled input の value を継続上書き**
   - `usePlaybackStatus.ts` の `onmessage` で `setStatus({ position: serverPosition })` を毎回実行
   - `page.tsx` で `value={status.position}` (controlled component)
   - ユーザーがドラッグしても WebSocket 更新で即座に元の値に戻る

2. **`api.playback.seek` が fire-and-forget**
   ```tsx
   onChange={e => api.playback.seek(Number(e.target.value))}  // await なし
   ```
   エラーが発生しても無視され、次の WebSocket update で値が戻る

3. **ローカル位置補間タイマーが 5秒遅延**
   - `/ws/now_playing` は 2秒間隔 polling、song_id/state 変化時のみ push
   - position は push されない → 5秒間サーバー更新なし → ローカル補間が効かない

**関連ファイル**: `src/hooks/usePlaybackStatus.ts` (L35-55, L70-100), `src/app/page.tsx` (L430-440)

---

### ⚠️ P1-1: VU メーターが動かない

**現象**: 再生中も VU バー (L/R) の高さが 0% のまま。

**根因**:
- `useEffect` が `status.state === 'play'` 依存だが、WebSocket から `state: 'play'` は来ている
- しかし **ブラウザスナップショットに `vu-meter-bar` 要素が存在しない**
- `scale-[0.45]` transform + `overflow: hidden` で表示領域外にある可能性
- VU コンテナ: `height: 288px`, `width: 17px`, `flexDirection: 'column-reverse'`

**関連ファイル**: `src/app/page.tsx` (L130-150, L550-570)

---

### ⚠️ P1-2: 反応が遅い (全般的な UI レスポンス低下)

**根因**:
1. **`useState` のみ、`useDeferredValue`/`useTransition` 未使用** - DSP popup 開閉・タブ切替・ボリューム変更すべて同期的
2. **WebSocket 2秒 polling 間隔** - 状態反映に最大 2秒遅延
3. **ローカル位置補間 5秒遅延** - 再生位置表示が遅れる
4. **起動時 `/api/devices` が `aplay -l` subprocess 実行** - `p50_ms: 5.24ms` の遅延

**関連ファイル**: `src/app/page.tsx`, `src/hooks/usePlaybackStatus.ts`

---

### ⚠️ P1-3: ボリューム API が 422 (Connection refused)

**現象**: `POST /api/volume {"volume": -5} → 422 Unprocessable Content`

**根因**: `CamillaClient("127.0.0.1", 1234)` に接続するが **CamillaDSP (port 1234) が未起動**。

**関連ファイル**: `hq_api/routers/dsp_write.py` (L87-110)

---

### ⚠️ P1-4: アルバムアート取得遅延 (UPnP 曲)

**現象**: UPnP 曲で `artwork_url` が null の場合、iTunes API にリダイレクト → ネットワーク遅延。

**経路**: `track.artwork_url ?? api.library.artworkUrl(track.uri)` → `GET /api/library/artwork?uri=...` → 307 redirect → `GET /api/art?...` → iTunes Search API

**関連ファイル**: `src/app/page.tsx` (L240), `hq_api/routers/dsp_readonly.py` (L50-80)

---

## 4. 総合的修正提案

### 4.1 即時対応 (P0: 本日中)

#### Fix 1: `.transport-label` CSS 追加
```css
/* src/app/globals.css 末尾に追加 */
.transport-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 80px;
  padding: 12px 16px;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  transition: background-color 100ms ease, color 100ms ease;
}
.transport-label:hover {
  background: rgba(34, 197, 94, 0.1);
}
.transport-label:active {
  background: rgba(34, 197, 94, 0.2);
}
.transport-label-active {
  color: #22c55e;
  text-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
}
```

#### Fix 2: CORS 設定修正
```python
# hq_api/main.py L24-29
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002", "http://localhost:3000", "http://127.0.0.1:3002", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
※ `allow_origins=["*"]` と `allow_credentials=True` の組み合わせを避ける

#### Fix 3: unified-shell 本番ビルド & サービス復旧
```bash
cd /home/tysbox/HQ_Linux_Music_Player/unified-shell
npm run build  # .next/standalone 生成
systemctl start unified-shell
systemctl status unified-shell
```

#### Fix 4: シークバー修正 (ローカル状態分離)
```tsx
// src/app/page.tsx - seek input 部分
const [seekTarget, setSeekTarget] = useState<number | null>(null)
const displayPosition = seekTarget ?? status.position

<input
  type="range"
  min={0}
  max={status.duration || 1}
  value={displayPosition}
  step={1}
  onChange={e => {
    const v = Number(e.target.value)
    setSeekTarget(v)
    // デバウンスして API 呼び出し
    clearTimeout(seekDebounceRef.current)
    seekDebounceRef.current = setTimeout(() => {
      api.playback.seek(v)
      setSeekTarget(null)
    }, 150)
  }}
  onMouseUp={() => { /* 即座に seek 確定 */ }}
/>

// usePlaybackStatus.ts - WebSocket 更新時に seekTarget がある場合は上書きしない
useEffect(() => {
  if (seekTargetRef.current !== null) return // ユーザー操作中はスキップ
  setStatus(prev => ({ ...prev, position: serverPosition }))
}, [serverPosition])
```

---

### 4.2 短期対応 (P1: 今週中)

#### Fix 5: VU メーター表示修正
```tsx
// src/app/page.tsx - VU コンテナのスタイル修正
// 現状: position: absolute, left: 8, top: 12, height: 288
// 修正: scale transform の影響を受けないよう relative 配置に変更
// または scale 適用前の座標系で配置

// 追加: VU メーターの可視性確認用デバッグ
<div style={{ 
  position: 'absolute', 
  left: 8, 
  top: 12, 
  width: 17, 
  height: 288, 
  background: 'rgba(255,0,0,0.1)',  // デバッグ用赤枠
  borderRadius: 8, 
  overflow: 'hidden', 
  display: 'flex', 
  flexDirection: 'column-reverse',
  zIndex: 10,  // 確実に前面に
}}>
  <div className="vu-meter-bar" style={{ width: '100%', height: `${vuL*100}%`, transition: 'height 75ms linear' }} />
</div>
```

#### Fix 6: 反応速度改善
```tsx
// src/app/page.tsx - 遅延 state に useDeferredValue 適用
import { useDeferredValue, useTransition } from 'react'

const deferredVolume = useDeferredValue(volume)
const [isPending, startTransition] = useTransition()

const handleVolume = (v: number) => {
  startTransition(() => {
    setVolume(v)
  })
  // API 呼び出しは即座に
  fetch('http://localhost:8002/api/volume', { ... })
}

// DSP popup 開閉も transition で
const [dspOpen, setDspOpen] = useState(false)
const deferredDspOpen = useDeferredValue(dspOpen)
```

#### Fix 7: CamillaDSP 起動確認 & 自動起動
```bash
# CamillaDSP 起動確認
systemctl status camilladsp || systemctl start camilladsp

# hq_api 起動時に CamillaDSP 接続確認を追加
# hq_api/routers/dsp_write.py の set_volume でリトライロジック追加
```

#### Fix 8: WebSocket position push 追加 (根本解決)
```python
# hq_api/ws/now_playing.py - format_now_playing に position 含める
# 現状: song_id/state 変化時のみ push
# 修正: position も含めて push (または別途 position 専用 push)

# または /ws/all で position を定期 push
async def _emit_loop(ws, stop_event):
    while not stop_event.is_set():
        # 既存の song_id/state チェック
        # 追加: position も送信
        await ws.send_json({"type": "position", "data": {"position": elapsed, "duration": duration}})
        await asyncio.sleep(1)  # 1秒間隔で position push
```

---

### 4.3 中期対応 (P2: 次スプリント)

| 対応 | 内容 | 期待効果 |
|------|------|----------|
| WebSocket 統一 | `/ws/all` をメインに、position 1秒 push | シークバー同期、VU メーター同期 |
| React 18 移行 | `useTransition`, `useDeferredValue`, `Suspense` 導入 | UI 応答性向上 |
| 状態管理ライブラリ | Zustand / Jotai 導入 | グローバル状態の一元管理、再レンダリング最適化 |
| E2E テスト追加 | Playwright でシーク・ボリューム・トランスポート操作を自動検証 | リグレッション防止 |
| 本番ビルド CI/CD | GitHub Actions で `npm run build` → systemd reload 自動化 | デプロイ信頼性向上 |

---

## 5. 修正優先度マトリクス

| # | 問題 | 影響度 | 難易度 | 工数目安 | 推奨順序 |
|---|------|--------|--------|----------|----------|
| 1 | transport-label CSS | 高 | 低 | 5分 | 1位 |
| 2 | CORS 修正 | 高 | 低 | 5分 | 2位 |
| 3 | systemd/standalone 復旧 | 高 | 中 | 30分 | 3位 |
| 4 | シークバー修正 | 高 | 中 | 1時間 | 4位 |
| 5 | VU メーター表示 | 中 | 低 | 30分 | 5位 |
| 6 | 反応速度改善 | 中 | 中 | 2時間 | 6位 |
| 7 | CamillaDSP 起動 | 中 | 低 | 10分 | 7位 |
| 8 | アルバムアート遅延 | 低 | 中 | 1時間 | 8位 |

---

## 6. 検証手順 (修正後)

```bash
# 1. CSS 確認
curl -s http://localhost:3002/ | grep -c "transport-label"

# 2. CORS 確認
curl -X POST http://localhost:8002/api/playback/seek -H "Origin: http://localhost:3002" -i | grep -i access-control

# 3. systemd 確認
systemctl status unified-shell

# 4. シークバー手動テスト
# ブラウザで再生中にシークバーをドラッグ → 位置が追従するか

# 5. トランスポートボタンテスト
# 再生/一時停止/前/次/シャッフル/リピート すべてクリック反応するか

# 6. VU メーターテスト
# 再生中に VU バーが動くか (目視)

# 7. ボリュームテスト
# ボリュームダイヤル操作 → API 200 返るか
```

---

## 7. 関連ファイル一覧

### フロントエンド (unified-shell)
| ファイル | 役割 | 修正対象 |
|----------|------|----------|
| `src/app/page.tsx` | メインページ (1121行) | P0-1, P0-4, P1-1, P1-2 |
| `src/hooks/usePlaybackStatus.ts` | WebSocket 状態管理 (127行) | P0-4, P1-2 |
| `src/app/globals.css` | グローバルスタイル (120行) | P0-1 |
| `src/lib/api.ts` | API クライアント | P0-4 |
| `package.json` | 依存関係・ビルド設定 | P0-3 |
| `next.config.ts` | Next.js 設定 | - |

### バックエンド (hq_api)
| ファイル | 役割 | 修正対象 |
|----------|------|----------|
| `hq_api/main.py` | FastAPI アプリ・CORS 設定 | P0-2 |
| `hq_api/ws/now_playing.py` | DSP互換 WebSocket | P0-4, P1-2 |
| `hq_api/ws/all.py` | 統合 WebSocket | P1-2, P2 |
| `hq_api/routers/dsp_write.py` | POST /api/volume 等 | P1-3 |
| `hq_api/routers/dsp_readonly.py` | GET /api/art 等 | P1-4 |
| `hq_api/routers/dmp.py` | DMP ルータ re-export | - |

### インフラ
| ファイル | 役割 | 修正対象 |
|----------|------|----------|
| `/etc/systemd/system/unified-shell.service` | systemd ユニット | P0-3 |
| `backend/scripts/switch_audio.sh` | ALSA 切替スクリプト | P1-3 |

---

## 8. 付録: ブラウザスナップショット抜粋 (2026-09-04 09:47)

```json
{
  "pageTitle": "HQ Linux Music Player",
  "url": "http://localhost:3002/",
  "consoleErrors": [
    "Access to fetch at 'http://localhost:8002/api/playback/seek' from origin 'http://localhost:3002' has been blocked by CORS policy",
    "TypeError: Failed to fetch at req (src_0vug2bz._.js:15:23)"
  ],
  "domHighlights": {
    "transportButtons": ["⏮", "⏸", "⏭", "shuffle", "repeat"],
    "seekSlider": "input[type=range] value=407 max=407",
    "volumeDial": "button APPLY, input[type=range] value=-8",
    "modeSelect": "combobox [PURE, DSP] selected=DSP",
    "outputSelect": "combobox [USB DAC, PC Speaker, Bluetooth] selected=Bluetooth",
    "dspTrigger": "▽ DSP (clickable)",
    "vuMeters": "NOT FOUND IN SNAPSHOT"
  }
}
```

---

## 9. 次のアクション

1. **即座に**: Fix 1 (CSS), Fix 2 (CORS), Fix 3 (systemd/build) を並行実施
2. **30分以内**: Fix 4 (シークバー) 実装・検証
3. **1時間以内**: Fix 5 (VU), Fix 7 (CamillaDSP) 実施
4. **今週中**: Fix 6 (反応速度), Fix 8 (WS position push) 設計・実装
5. **次スプリント**: P2 項目の計画・着手

---

**以上**