# ADR-003: WebSocket 統合方針

> **ステータス**: Proposed
> **作成日**: 2026-09-02
> **対象フェーズ**: Phase 3c
> **関連**: `BACKEND_UNIFICATION_WALKTHROUGH.md` Phase 2 修正, ADR-001

---

## コンテキスト

DSP の `/ws/now_playing` と DMP の `/ws/status` の 2 種類の WebSocket が
**異なる実装方針** で動いている。

| 項目 | DSP `ws_now_playing` | DMP `websocket_status` |
|---|---|---|
| イベント検知 | **polling (2 秒間隔)** | **idle() イベント駆動** |
| 共有接続 | `_client` 共有 + Lock | 共有 + 別 `idle_client` |
| クライアント管理 | `WSManager` (複数) | 1 接続 1 クライアント |
| 履歴自動追加 | なし | あり（曲変化時） |
| 初回 push | なし（最初の poll まで遅延） | あり（accept 直後） |

## 決定

**当面は 2 系統を維持**。Phase 3 統合時に新エンドポイント `/ws/all` を追加し、
フロントエンドの `unified-shell` が利用する。

### 短期（Phase 3a〜3b）

- `/ws/now_playing` と `/ws/status` は **そのまま維持**
- 既存フロントエンドは変更なし

### 中期（Phase 3c）

- 新 `/ws/all` を追加
- メッセージスキーマ:
  ```json
  {
    "type": "now_playing" | "status" | "dsp" | "error",
    "data": { ... }
  }
  ```
- フロントエンド (`unified-shell`) を `/ws/all` に切替

### 長期（Phase 4 以降）

- `/ws/now_playing` と `/ws/status` を削除
- 旧 frontend (`frontend/`, `unified-frontend/`) を引退

## DMP の `idle_client` の扱い

DMP 側で既に動いている **別ソケットで `idle()` する方式** は、ADR-001 の
`purpose="playback"` 化と整合性が取れる。Phase 3b で以下のように変更:

```python
# 旧: 独自ソケット
idle_client = MPDClient()
await idle_client.connect(MPD_HOST, MPD_PORT)
async for changed in idle_client.idle([...]):
    ...

# 新: 共通 playback 接続
async with mpd_connection(purpose="playback") as idle_client:
    async for changed in idle_client.idle([...]):
        ...
```

## DSP の polling を idle() に変更するか？

**現時点では変更しない**。理由:

1. Phase 2 修正で「idle の async generator 取り扱いの複雑さ」が確認されている
2. 2 秒間隔の polling コストは MPD 的に無視できる
3. Phase 3 で再検証 → 必要に応じて別 ADR で対応

## 影響範囲

| ファイル | 変更内容 |
|---|---|
| `hq_api/routers/websocket/__init__.py` | 新規 |
| `hq_api/routers/websocket/now_playing.py` | DSP 版を移植 |
| `hq_api/routers/websocket/status.py` | DMP 版を移植（idle_client → mpd_connection(purpose="playback")） |
| `hq_api/routers/websocket/all.py` | 新規 |
| `unified-shell/src/lib/api.ts` | `/ws/all` への切替（Phase 3c） |

## ロールバック手順

```bash
# /ws/all の追加を取り消して旧エンドポイントを維持
git revert <commit-hash-of-ws-all>
```

## 想定工数

| Step | 工数 |
|---|---|
| DSP / DMP WebSocket 移植 | 0.5 日 |
| `/ws/all` 実装 | 1 日 |
| フロントエンド切替 | 1 日 |
| **合計** | **2.5 日** |
