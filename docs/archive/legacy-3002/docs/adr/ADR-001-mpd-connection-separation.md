# ADR-001: MPD 接続分離設計

> **ステータス**: Proposed
> **作成日**: 2026-09-02
> **対象フェーズ**: Phase 3 着手前
> **関連**: `BACKEND_UNIFICATION_WALKTHROUGH.md` Phase 2 修正, `DEVELOPMENT_ROADMAP.md` Phase 3.5-1

---

## コンテキスト

現状の [hqmplayer_core/mpd/client.py](hqmplayer_core/mpd/client.py) は、プロセス全体で
**1 本の MPD 接続と 1 つの `asyncio.Lock`** を全 API で共有している。

Phase 3 で DSP / DMP の 2 プロセスを 1 プロセスに統合すると、
**短時間 I/O (`status()`) と長時間 I/O (`readpicture()`) が同じロックを奪い合う**
可能性がある。

さらに DMP の WebSocket ([dmp/backend/app/routers/websocket.py](dmp/backend/app/routers/websocket.py#L53-L58))
は `idle()` 待ちのため **既に別ソケット (`idle_client`) を作っている**。

## 調査結果（A 調査より）

| API | 呼び出し元 | I/O 種別 | 想定所要時間 |
|---|---|---|---|
| `status()` | DSP watchdog / WebSocket polling | 短時間 | 10〜50ms |
| `currentsong()` | 同上 | 短時間 | 10〜50ms |
| `play/pause/next/seek` | playback 制御 | 短時間 | 10〜50ms |
| `idle()` | DMP WebSocket | **長時間（イベント待ち）** | 数秒〜数分 |
| `readpicture()` | album art 取得 | 中時間（バイナリ） | 100ms〜2s |
| `albumart()` | 同上 | 中時間 | 同上 |
| `playlist/listplaylist` | プレイリスト操作 | 短〜中時間 | 50ms〜500ms |

## 決定

`hqmplayer_core.mpd.client` に **`purpose` パラメータ**を導入し、**2 系統の接続** を持たせる。

```python
# 制御系: status / currentsong / play / pause / next / seek
async def mpd_connection(purpose: str = "control") -> AsyncContextManager[MPDClient]:
    ...
```

| `purpose` | 用途 | 接続 ID | Lock ID |
|---|---|---|---|
| `"control"` | 短時間 I/O（`status` / `currentsong` / 制御系） | `_client_control` | `_lock_control` |
| `"playback"` | 長時間 I/O（`idle` / `readpicture` / `albumart`） | `_client_playback` | `_lock_playback` |

**デフォルトは `"control"`**。既存コードを変更せずにそのまま動く。

## 影響範囲

### 変更が必要なファイル

1. [hqmplayer_core/mpd/client.py](hqmplayer_core/mpd/client.py) — `purpose` パラメータ追加
2. [hqmplayer_core/mpd/__init__.py](hqmplayer_core/mpd/__init__.py) — re-export 維持
3. [dmp/backend/app/routers/websocket.py](dmp/backend/app/routers/websocket.py) — 独自 `idle_client` を `purpose="playback"` の `mpd_connection` に置換
4. [hqmplayer_core/art/resolver.py](hqmplayer_core/art/resolver.py) — `mpd_readpicture` / `mpd_albumart` を `purpose="playback"` に変更

### 影響を受けないファイル（デフォルトで互換維持）

- [backend/main.py](backend/main.py) の `mpd_status` / `mpd_currentsong` / watchdog
- DMP 各ルータの `async with mpd_connection() as client:` 呼び出し

## 採用しなかった案

### 案 B: 既存の 1 接続のまま、ロックだけ分離

短時間 I/O と `readpicture` を別 Lock にしても、**同じソケットを共有する以上** 結局
MPD プロトコルレベルで混線する。却下。

### 案 C: 接続プール（複数接続の動的管理）

オーバースペック。現状の使用パターンでは「制御」「長時間待ち」の 2 系統で十分。
将来接続数が増える場合は別 ADR で対応。

## 検証方法

```bash
# 制御系と playback 系が別ソケットを使うことを確認
ss -tnp | grep :6600
# 期待値: 2 本の確立接続（control + playback）

# playback 系の readpicture 中に control 系の status() が即応するか
time curl -sf http://localhost:8000/api/now_playing
# 期待値: 200ms 以内（playback 中でも遅延しない）
```

## ロールバック手順

この ADR 実装は **新パラメータの追加** のみで、既存 API の削除は伴わない。
ロールバックは `purpose` 引数をすべて省略する状態に戻すことで実現可能。

```bash
git revert <commit-hash-of-this-ADR>
sudo systemctl restart audiophile-backend hq-dmp-backend
```

## 想定工数

**0.5〜1 日**（hqmplayer_core のみの変更、既存ルータは無変更）
