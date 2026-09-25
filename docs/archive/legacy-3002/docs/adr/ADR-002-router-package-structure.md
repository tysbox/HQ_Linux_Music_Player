# ADR-002: ルータ統合のパッケージ構造

> **ステータス**: Proposed
> **作成日**: 2026-09-02
> **対象フェーズ**: Phase 3a
> **関連**: `DEVELOPMENT_ROADMAP.md` Phase 3-1

---

## コンテキスト

DSP の `backend/main.py` (約 950 行) と DMP の `dmp/backend/app/main.py` (約 60 行 +
7 ルータ) を 1 プロセスに統合する必要がある。

## 決定

**`hq_api/` パッケージを新設** し、DSP / DMP のルータをマージする。

```
HQ_Linux_Music_Player/
├── hq_api/                      ← NEW: 統合バックエンド
│   ├── __init__.py
│   ├── main.py                  ← FastAPI app (lifespan 含む)
│   ├── routers/                 ← DSP + DMP のルータを統合
│   │   ├── dsp/                 ← DSP 固有 (devices, dsp_status, config, apply, presets, art)
│   │   ├── playback/            ← DMP 由来 (status, play, pause, next, ...)
│   │   ├── library/             ← DMP 由来
│   │   ├── queue/               ← DMP 由来
│   │   ├── playlists/           ← DMP 由来
│   │   ├── history/             ← DMP 由来
│   │   ├── upnp/                ← DMP 由来
│   │   └── websocket/           ← DSP + DMP を統合
│   └── deps.py                  ← DI ヘルパー
├── hqmplayer_core/              ← 既存（変更なし）
├── backend/                     ← 旧 DSP（Phase 4 で削除）
├── dmp/backend/                 ← 旧 DMP（Phase 4 で削除）
└── ...
```

## URL パス戦略

DSP 側は `/api/*`、DMP 側は `/api/*` で **同じ prefix** を持つが、
**エンティティが異なる** のでパス衝突は基本的に発生しない。

| パス | 由来 | 用途 |
|---|---|---|
| `/api/devices` | DSP | オーディオデバイス一覧 |
| `/api/now_playing` | DSP | 軽量 Now Playing（DSP/DMP 共通化） |
| `/api/dsp_status` | DSP | CamillaDSP 状態 |
| `/api/config` | DSP | DSP 設定 |
| `/api/apply` | DSP | DSP 設定適用 |
| `/api/presets` | DSP | DSP プリセット |
| `/api/art` | DSP | アルバムアート |
| `/api/library/*` | DMP | ライブラリ |
| `/api/playback/*` | DMP | 再生制御 |
| `/api/queue/*` | DMP | キュー |
| `/api/playlists/*` | DMP | プレイリスト |
| `/api/history/*` | DMP | 履歴 |
| `/api/upnp/*` | DMP | UPnP |
| `/ws/now_playing` | DSP | Now Playing push |
| `/ws/status` | DMP | ステータス push |
| `/ws/all` | **NEW** | 統合 push（Phase 3c で追加） |

## 段階的アプローチ（ROADMAP 通り）

| Step | 内容 | 既存 backend の扱い |
|---|---|---|
| 3a | `hq_api/` を port 8002 で並行起動 | 8000 / 8001 は生かす |
| 3b | 8000 / 8001 を停止、`hq_api` を 8000 で起動 | 統合 backend 単独運用 |
| 3c | 旧 `backend/main.py` / `dmp/backend/app/main.py` を段階削除 | Phase 4 |

## リスクと対策

| リスク | 対策 |
|---|---|
| 旧 backend との同時起動でポート衝突 | 3a は **8002** で起動、既存は無改変 |
| CORS / Cookie などの Origin 依存挙動 | `allow_origins=["*"]` を維持 |
| 旧 backend の `loopback` との通信（DSP → switch_audio.sh） | `hq_api/` からも `subprocess` で直接実行可能 |
| 履歴機能の競合 | DMP 由来ルータをそのまま移植（DSP には追加しない） |

## ロールバック手順

```bash
# Step 3a の状態に戻す（hq_api を停止し、旧 backend を再起動）
sudo systemctl stop hq-api
sudo systemctl start audiophile-backend hq-dmp-backend
```

## 想定工数

| Step | 工数 |
|---|---|
| 3a | 2〜3 日（ルータのコピーと import 修正） |
| 3b | 0.5 日（systemd 切替と動作確認） |
| 3c | 1 日（テストと削除） |
| **合計** | **3.5〜4.5 日** |
