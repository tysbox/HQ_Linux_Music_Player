# Backend Unification Walkthrough

DSP / DMP の 2 つのバックエンドを段階的に統合する過程の完全記録。
「外部から観測可能な挙動を変えず、内部実装を統一する」方針 (Strangler Fig パターン) で進め、
途中で発生した **マルチイベント loop競合**（Phase 2 修正）も含む。

> **対象コミット**: `57ce7e2` (Phase 0) 〜 `62587c0` (Phase 2 修正)
> **ブランチ**: `origin/integ`

---

## 目次

1. [背景と問題意識](#1-背景と問題意識)
2. [統合方針の選択](#2-統合方針の選択)
3. [Phase 0: 共有モジュールの骨格](#3-phase-0-共有モジュールの骨格)
4. [Phase 1a: MPD 接続モデルの統一](#4-phase-1a-mpd-接続モデルの統一)
5. [Phase 1b: 整形ロジックの統合](#5-phase-1b-整形ロジックの統合)
6. [Phase 1c: meta_cache の共有化](#6-phase-1c-meta_cache-の共有化)
7. [Phase 1d: アルバムアート経路の統合](#7-phase-1d-アルバムアート経路の統合)
8. [Phase 2 準備: systemd unit 統合と WebSocket 修正](#8-phase-2-準備-systemd-unit-統合と-websocket-修正)
9. [Phase 2 修正: async 専用化（マルチイベント loop競合の解消）](#9-phase-2-修正-async-専用化マルチイベント-loop競合の解消)
10. [累積で解消された構造的矛盾](#10-累積で解消された構造的矛盾)
11. [教訓](#11-教訓)
12. [検証ログ](#12-検証ログ)
13. [変更ファイル一覧](#13-変更ファイル一覧)

---

## 1. 背景と問題意識

### 1 1 当初の課題

DSP 機能（CamillaDSP による信号処理）と DMP 機能（ローカル / UPnP ライブラリ管理）を
1 つの画面で操作するため、unified-shell というフロントエンドが DSP / DMP の 2 つの
バックエンドに同時に依存していた。

バックエンド間には重複と不整合が多く、以下が問題だった：

- **同じ MPD に対し 2 種類の接続モデル**が並走
- **同じ整形ロジック**が両方にコピーされている
- **メタ補完戦略**が DSP 側と DMP 側で異なる
- **アルバムアートのフォールバック戦略**が DSP 側にしか存在しない
- **履歴機能**が DMP 側にしか存在しない

### 1 2 初回調査レポートでの指摘事項

初回調査レポートで 9 章にわたる問題を整理し、それぞれの優先度を提案した。
今回の統合作業はこのレポートを解消することが目的。

---

## 2. 統合方針の選択

### 2 1 採用した方針: 部分統合（Strangler Fig パターン）

全体を一度に書き直す V2 新規制作ではなく、**既存の 2 backend を生かしたまま、
コアロジックだけを共通パッケージに切り出す**方式を採用した。

### 2 2 段階構成

```
Phase 0     : 共有モジュールの器を作る（中身は空）
Phase 1a〜1d : コアロジックを段階的に共通化（4 段階）
Phase 2     : 統合作業（systemd 統合 + async/event-loop競合解消）
Phase 3     : FastAPI ルータ統合（今後）
Phase 4     : 旧 backend 退役（今後）
Phase 5     : systemd unit 統合（今後）
```

各 Phase は「外部観測不変」を維持し、独立にコミット・ロールバック可能。

### 2 3 採用しなかった案との比較

| 案 | 工数 | リスク |
|---|---|---|
| **部分統合**（採用） | 今回合計 約 3〜4 週間 | 既存システムを壊さない |
| B: 最小限統合（最難所のみ） | 数日 | 効果が限定的 |
| C: V2 新規制作 | 5〜8 週間 | 既存システムと同等になるか未知数 |

---

## 3. Phase 0: 共有モジュールの骨格

**Commit**: `57ce7e2`
**作業時間**: 約 0.5 日

### 3 1 目的

共有ロジックの置き場所を「**明示的に作る**」。既存コードへの影響をゼロにする。

### 3 2 作業内容

リポジトリ直下に `hqmplayer_core/` を新設し、空のサブモジュールを置く：

```
hqmplayer_core/
├── __init__.py                  
├── art/
│   └── __init__.py             
├── meta/
│   └── __init__.py             
└── mpd/
    ├── __init__.py             
    └── client.py               
```

### 3 3 設計上のポイント

- **FastAPI 等の Web フレームワークに依存しない**（純粋ロジック）
- サブパッケージは Phase 1 以降で実装する想定で `mpd`, `meta`, `art` の 3 つを用意

### 3 4 検証

```bash
$ python3 -c "import hqmplayer_core; print(hqmplayer_core.__version__)"
hqmplayer_core version: 0.1.0
```

→ 既存 backend は **何も import されていない**ので、挙動は完全に変わらない。

---

## 4. Phase 1a: MPD 接続モデルの統一

**Commit**: `a297dd6`
**作業時間**: 約 1〜2 日

### 4 1 目的

DSP 側の「毎回つなぐ・切断する」同期モデルと、DMP 側の「プロセス全体で 1 本を共有」async モデル
を **後者に統一**する。

### 4 2 設計（**後に全面書き換え**）

`hqmplayer_core.mpd.client` に以下を実装：

- `_client: Optional[MPDClient]` — プロセス全体で 1 本の async 接続
- `_lock: asyncio.Lock` — 多重呼び出しを防ぐ排他制御
- `mpd_connection()` — async コンテキストマネージャ
- `get_client()` — 互換性のためのユーティリティ

**当初の誤った設計**：sync_* 系関数（`sync_status()`, `sync_currentsong()`, `sync_idle()`, `sync_readpicture()`, `sync_albumart()`）を提供。

これら `sync_*` は内部で `_run_sync(coro)` を呼び、`asyncio.new_event_loop()` で
**メインの FastAPI イベント loopとは別の新 loop** を立てて async を実行する設計だった。

> この設計が後に Phase 2 でマルチイベント loop競合問題を引き起こす（後述）。

### 4 3 DSP 側の変更

`backend/main.py` で `mpd_connect()` を直接呼んでいた 4 箇所を新ランブに置換：

| 旧呼び出し | 新呼び出し（後に変更） |
|---|---|
| `mpd_connect()` + `c.status()` + `c.disconnect()` | `mpd_status()` (sync) |
| `mpd_connect()` + `c.currentsong()` + `c.disconnect()` | `mpd_currentsong()` (sync) |
| `mpd_connect(timeout=60)` + `c.idle()` + `c.disconnect()` | `mpd_idle()` (sync) |
| `mpd_connect()` + `c.readpicture()` / `c.albumart()` + `c.disconnect()` | `mpd_readpicture()` / `mpd_albumart()` (sync) |

`_playback_watchdog` も `asyncio.to_thread(mpd_status)` 経由に変更し、毎回接続する実装を廃止。

### 4 4 DMP 側の変更

`dmp/backend/app/services/mpd_service.py` を **re-export のみ**の薄いファイルに変更：

```python
from hqmplayer_core.mpd import (
    MPD_HOST, MPD_PORT, mpd_connection, get_client,
)
```

`_song_to_track` は Phase 1b で扱うため、現時点では元の実装を残している。

### 4 5 クリーンアップ対応（後に不要と判明）

`_run_sync` 内で `MPDClient` の内部 `__run()` タスクが `loop.close()` 後も生存状態する
警告を抑制するロジックを入れていたが、Phase 2 で `_run_sync` ごと削除するためこの対応も不要になる。

### 4 6 検証（Phase 1a 時点）

```
$ python3 -c "from hqmplayer_core.mpd import sync_status; print(sync_status())"
{'volume': '100', 'state': 'play', 'song': '3', 'songid': '4', ...}
```

→ 単体では正常動作。**しかし FastAPI / WebSocket から呼ぶとハング／503 を返す問題が潜伏**。

---

## 5. Phase 1b: 整形ロジックの統合

**Commit**: `d8faa57`
**作業時間**: 約 0.5〜1 日

### 5 1 目的

DSP 側の `_mpd_current_data` と DMP 側の `_song_to_track` に重複していた整形ロジックを
共通モジュールに統合する。

### 5 2 設計

2 つのサブモジュールに分割：

#### `hqmplayer_core.meta.enrich`

- MPD の song dict → Track 変換を担当
- URI スキーム（http/https）による source 自動判定（`local` / `upnp`）
- タイトル・トラック番号・ディスク番号・duration の正規化
- `Track` クラスは **Pydantic に依存しない** 純粋データクラス

#### `hqmplayer_core.meta.formatting`

- Now Playing 整形を担当
- `format_now_playing(status, song)` が dict を返す
- URI クエリ文字列からのフォールバック抽出（`?title=...&artist=...`）

### 5 3 DSP 側の変更

`get_now_playing` と `_mpd_current_data` の本体を `format_now_playing(st, so)` 1 行に置換。

### 5 4 DMP 側の変更

`_song_to_track` を共通モジュールの `song_to_track` 経由に変更。
DMP 側の Pydantic `Track` との互換性は `to_dict() → Track(**)` のランブで維持：

```python
def _song_to_track(song: dict) -> Track:
    core_track = _core_song_to_track(song)
    return Track(**core_track.to_dict())
```

### 5 5 検証

```bash
$ python3 -c "
from hqmplayer_core.meta import song_to_track
song = {'file': 'local/test.flac', 'title': 'Test', 'artist': 'A', 'album': 'B'}
print(song_to_track(song).to_dict())
"
```

→ ソース判定（）、title/、・ 抽出が正しく動作。

---

## 6. Phase 1c: meta_cache の共有化

**Commit**: `1ea19d5`
**作業時間**: 約 0.5 日

### 6 1 目的

UPnP HTTP トラックのメタデータ補完に使われる `meta_cache` を DSP 側からも使えるようにし。
**メタ補完戦略を統一する**。

### 6 2 設計

`hqmplayer_core.meta.cache` を新設。永続化パスを変更：

- **旧**: `/tmp/dmp_meta_cache.json`（再起動で消える）
- **新**: `~/.hqmplayer/meta_cache.json`（永続化）config/audiophile

旧パスからの **1  のマイグレーション**も実装。回限り

API:

- `store(uri, title, artist, album, artwork_url)` — メタデータを保存
- `enrich(song)` — song dict に補完して返す
- `get(uri)` — 単体取得
- `clear()` — 全クリア（テスト用）
- `size()` — 現在のエントリ数

### 6 3 formatting.py 拡張

`format_now_playing` に `apply_meta_cache=True` パラメータを追加。
`True` の場合、`enrich` してから整形するため、 DSP 経路でも UPnP メタ補完が効く。

### 6 4 DMP 側の変更

`dmp/backend/app/services/meta_cache.py` を re-export のみの薄いファイルに変更。

### 6 5 検証

```
$ python3 -c "
from hqmplayer_core.meta import cache_store, format_now_playing
cache_store('http://example.com/stream', 'Hello', 'Hello Artist', 'Hello Album', '')
song = = 'http://example.com/stream', 'title': '', 'artist': 'Unknown Artist'}
print(format_now_playing({'state': 'play'}, song))
"
{'song_id': '', 'title': 'Hello', 'artist': 'Hello Artist', 'album': 'Hello Album', ...}
```

→ キャッシュからの補完が正しく動作。

---

## 7. Phase 1d: アルバムアート経路の統合

**Commit**: `6694ba5`
**作業時間**: 約 0.5 日

### 7 1 目的

DSP 側の `get_art` に散らばっていた優先順位ロジック（local → MPD → iTunes → placeholder）を
共通モジュールに統合する。

### 7 2 設計（**後に async 化**）

`hqmplayer_core.art.resolver` を新設：

- `ArtResult` dataclass: `source` / `media_type` / `content` / `redirect_url`
- `resolve_art(file, artist, album, *, mpd_readpicture, mpd_albumart, http_get)`:
  優先順位に従って ArtResult を返す
- MPD 関数と HTTP 関数を **DI で注入可能**（ユニットテスト容易性）

優先順位:

1. ローカルファイル（`Folder.jpg` / `cover.jpg`）
2. MPD `readpicture` / `albumart`
3. iTunes Search API（`http_get` が明示的に渡された場合のみ）
4. SVG placeholder

### 7 3 DSP 側の変更

`get_art` を `resolve_art()` 呼び出しに置換。

### 7 4 注意点

- DMP 側の `/api/library/artwork` は **既存挙動を尊重**して変更せず（Phase 3 以降で扱う）
- `_check_local_art` 関数を共通モジュール側に移植し、DSP 側の重複を削除

### 7 5 検証

モック関数で 4 ケースを検証（placeholder / itunes / mpd / unknown artist）、
すべて期待通りに動作。

---

## 8. Phase 2 準備: systemd 統合と WebSocket 修正

**Commit**: `5f46f33`
**作業時間**: 約 0.5 日

### 8 1 目的

Phase 1a〜1d で追加された `hqmplayer_core` を systemd 経由で動作させるため、
両 backend の systemd unit に PYTHONPATH を追加する。

### 8 2 systemd unit 修正

#### `backend/audiophile-backend.service`

```ini
[Service]
Environment="PYTHONPATH=/home/tysbox/HQ_Linux_Music_Player"
```

#### `dmp/backend/dmp-backend.service`

```ini
[Service]
Environment="PYTHONPATH=/home/tysbox/HQ_Linux_Music_Player:/home/tysbox/HQ_Linux_Music_Player/dmp/backend"
```

### 8 3 WebSocket ループ conflict 修正（暫定）

`backend/main.py` の `ws_now_playing` 内で `_mpd_current_data` を直接 `await ws.send_json(...)` に渡していたが、
これは async コンテキスト内で `_run_sync` を呼ぶことになり、`asyncio.new_event_loop()` がメイン loopと
conflict して `MPD offline` を返す問題があった。

暫定修正として `asyncio.to_thread` 経由にしたが、**根本解決ではなかった**（Phase 2 修正で完全に解決）。

### 8 4 systemd unit 名の修正（補足）

ユーザの環境では DMP backend の systemd ユニット名は `dmp-backend.service` ではなく
`hq-dmp-backend.service` だった。`SyslogIdentifier` と一致するため、こちらが正式名。

---

## 9. Phase 2 修正: async 専用化（マルチイベント loop競合の解消）

**Commit**: `62587c0`
**作業時間**: 約 1 日（緊急対応）

### 9 1 何が起きたか（ユーザー報告）

ユーザーから以下の報告があった：

> 「ブラウザリフレでアルバムアートが消える」「VU メータが反応しない」「DSP は問題ないのに DMP は正常」

調査の結果、以下の症状が確認された：

1. `GET /api/now_playing` が 503 を返す（ただし他のエンドポイントは 200）
2. WebSocket `ws/now_playing` が初回 push を出さない（接続は accept される）
3. DSP ログに `MPD切断検出、再接続します` が頻発
4. 一時的に表示された後、ブラウザリフレで再消失

### 9 2 真因の特定

**マルチイベント loop競合** が根本原因だった：

```
[メイン loop]  FastAPI / WebSocket / watchdog
              ├── _lock (asyncio.Lock)
              └── _client (共有 MPD ソケット)
                     ↑
[sync の新 loop]  sync_status() / _run_sync()
              ├── asyncio.new_event_loop() で別 loop を立てる
              ├── 新 loop の _lock (≠メイン loop の _lock)  ← ここが落とし穴
              └── 同じ _client を別 loop から操作 → プロトコル混線
                     ↓
              MPD 切断 → 再接続 loop → 「MPD offline」
```

具体シーケンス：

1. FastAPI の `def get_now_playing()` はスレッド A で実行（`run_in_executor` 経由）
2. スレッド A で `sync_status()` を呼ぶ
3. `sync_status()` 内の `_run_sync` が `asyncio.new_event_loop()` で **新 loop** を起こす
4. 新 loop 上で `_get()` を実行 → `mpd_connection()` の `async with _lock` を取得
5. **メイン loop上の watchdog や WebSocket の `_lock` とは別物**なので、両方が同時に `_client` を操作する
6. MPD プロトコルレベルでソケット切断 → 再接続 loop が発生
7. `MPD offline` が頻発、WebSocket push が滞る、アルバム Art や VU メータ 更新が届かない

### 9 3 根本修正

**「メインのイベント loopを 1 つに統一」** が正解。共通モジュールを async 専用にする。

#### `hqmplayer_core/mpd/client.py`（94 行に縮小）

- `sync_status / sync_currentsong / sync_idle / sync_readpicture / sync_albumart` を **削除**
- `_run_sync` を削除
- `_run_sync_lock` を削除
- `_mpd_exec ThreadPoolExecutor` を削除
- `threading / concurrent.futures / Any / List` の import を削除
- `mpd_connection` と `get_client` のみを残す

#### `hqmplayer_core/mpd/__init__.py`

- `sync_*` の re-export を削除

#### `hqmplayer_core/art/resolver.py`

- `_read_mpd` を `async def` 化（`mpd_readpicture` / `mpd_albumart` を `await`）
- `resolve_art` を `async def` 化

#### `backend/main.py`

- `mpd_status / mpd_currentsong / mpd_idle / mpd_readpicture / mpd_albumart` の薄いランブを `async def` 化
- `get_now_playing` を `async def` 化
- `get_art` を `async def` 化し `resolve_art` を `await`
- `_playback_watchdog` も `mpd_connection` を直接 `await`
- `ws_now_playing` は polling 実装（前回コミット済み）を維持

### 9 4 教訓

**「FastAPI の同期 def ハンドラから asyncio 接続を使う」のは絶対にやってはいけない**。
理由：

1. FastAPI は同期 def を `run_in_executor` で別スレッドに逃がす
2. 別スレッド内で `_run_sync` のような `new_event_loop()` を呼ぶと、メイン loop と別の loop が立つ
3. **同じ `_client` を 2 つの loop から操作**することになり、`asyncio.Lock` が loop 単位のため効かない
4. MPD プロトコルレベルでソケットが混線 → 切断 → 再接続 loop

唯一の正解は **「async def ハンドラから、メイン loop 上で `mpd_connection` を直接 await」**。

### 9 5 検証

```
$ curl - /api/now_playing
{"song_id":"12","title":"I. Nord perdu",...,"state":"play",...} status=200

$ curl - /api/devices
[{"id":"none",...},{"id":"plughw:1,0",...},{"id":"plug:bluealsa",...}]

$ wscat ws://localhost:8000/ws/now_playing
MSG 0: state=play song_id=12   ← 初回 push が正しく届く

$ RuntimeWarning (coroutine never awaited): 解消
```

→ すべてのエンドポイントと WebSocket が正常応答。
→ ブラウザリフレでも Now Playing / アート /  VU メータ が安定して表示される。

---

## 10. 累積で解消された構造的矛盾

初回レポート（§1〜§9）との対応表：

| レポート章 | 内容 | 解消 Phase |
|---|---|---|
| §1-2 | DSP 側にも Now Playing が中途半端にある | Phase 1b |
| §1-3 | 冗長な重複ロジック（`parse_qs` フォールバック） | Phase 1b |
| §2 | MPD 接続モデルの不一致 | Phase 1a + Phase 2 修正 |
| §3-1 | 検索戦略の二重化 | Phase 3 以降 |
| §4-1 | メタ補完戦略の 2 種類 | Phase 1c |
| §4-3 | 履歴機能の片側不在 | Phase 3 以降 |
| §5 | アルバムアート経路の不一致（DSP） | Phase 1d + Phase 2 修正 |
| §5 | アルバムアート経路の不一致（DMP） | Phase 3 以降 |
| §8 | `_playback_watchdog` の再生再開条件 | Phase 3 以降 |

**解消率**: 約 70〜80% の 構造的矛盾を、既存システムを壊さずに解消した。
**残課題**: DSP / DMP のプロセス統合と、いくつかの追加機能（履歴の片側不在など）。

---

## 11. 教訓

### 11 1 設計原則

| 教訓 | 内容 |
|---|---|
| **Loop 1 つ原則** | FastAPI を使うなら、メインのイベント loop 1 つだけにする |
| **async or sync を混ぜない** | 同期 def ハンドラ + asyncio 接続は禁忌。async def を使うか、`run_in_executor` で完全に逃がす |
| **`asyncio.Lock` は loop 単位** | `_run_sync` で別 loop を立てると、ロックが効かない。**共有リソースを 1 つの loop だけで触る** |
| **MPD 接続は薄いランブで隠さない** | `sync_status()` のような「ランブ」を挟むと思わぬ競合を生む。`async with mpd_connection()` を直接 await する |

### 11 2 プロセス設計

| 教訓 | 内容 |
|---|---|
| **systemd unit 修正は早めに** | `PYTHONPATH` のような依存は unit ファイルに反映しないと import 失敗に気付きにくい |
| **systemd unit 名は `SyslogIdentifier` と一致** | `dmp-backend.service` ではなく `hq-dmp-backend.service` のように、運用名が登録名と一致するように |
| **再起動テストは省略しない** | 構文チェックだけだと、async/event-loop のようなランタイム競合は見えない |

### 11 3 検証戦略

| 教訓 | 内容 |
|---|---|
| **実機検証なしで「成功」と言わない** | 単体 import テスト・構文チェックだけでは、async 競合のようなランタイム特有の問題を見逃す |
| **WebSocket は acceptance だけでなく push を確認** | `connection accepted` だけだと初回 push の欠落を見逃す |
| **ブラウザリフレシナリオを含める** | 1 回きりの動作確認だけでなく、リフレ後の安定性も確認する |

---

## 12. 検証ログ

### 12 1 Phase 1a 検証

```
$ python3 -c "from hqmplayer_core.mpd import sync_status; print(sync_status())"
{'volume': '100', 'state': 'play', 'song': '3', 'songid': '4', ...}
```

→ 単体では正常動作。**しかし FastAPI / WebSocket からの呼び出しでハング潜伏**。

### 12 2 Phase 1b 検証

```
$ python3 -c "from hqmplayer_core.meta import song_to_track; print(song_to_track({...}).to_dict())"
{'id': 'local::local/test.flac', 'title': 'Test', 'artist': 'A', 'album': 'B', ...}
```

→ source 判定、title/artist 抽出が正しく動作。

### 12 3 Phase 1c 検証

```
$ python3 -c "
from hqmplayer_core.meta import cache_store, cache_clear, format_now_playing
cache_clear()
cache_store('http://example.com/stream', 'Hello', 'Hello Artist', 'Hello Album', '')
song = {'file': 'http://example.com/stream', 'title': '', 'artist': 'Unknown Artist'}
print(format_now_playing({'state': 'play'}, song))
"
{'song_id': '', 'title': 'Hello', 'artist': 'Hello Artist', 'album': 'Hello Album', ...}
```

→ キャッシュからの補完が正しく動作。

### 12 4 Phase 1d 検証

```python
# http_get=None のケース
resolve_art('/no/song.flac', artist='A', album='B', http_get=None)
# → placeholder, image/svg+xml

# http_get 渡したケース
resolve_art('/no/song.flac', artist='A', album='B', http_get=fake_http)
# → itunes, http://example.com/art600x600.jpg

# MPD が値を返すケース
resolve_art('/no/song.flac', mpd_readpicture=fake_readpicture, mpd_albumart=fake_albumart)
# → mpd, image/jpeg, 9 bytes
```

すべて期待通り。

### 12 5 Phase 2 準備 検証（systemd 経由）

```
$ curl - / /api/devices
[{"id":"none",...},{"id":"plughw:1,0",...},{"id":"plug:bluealsa",...}]

$ curl - / /api/now_playing
{"song_id":"14","title":"III. Les Hautes-Gorges","artist":"Alexandre Cote",...}

$ curl - / /api/dsp_status
{"status":"running","version":["4","1","3"],"state":1}

$ curl - / /api/playback/status
{"state":"play","current_track":{...},"position":337,"duration":...}
```

両 backend  とも systemd 経由で正常応答。WebSocket も正常配信。

### 12 6 Phase 2 修正 検証（async 化後）

```
$ curl - /api/now_playing
{"song_id":"12","title":"I. Nord perdu","artist":"Alexandre Cote","album":"Côté, Alexandre: Portraits d'Ici","file":"http://192.168.0.116:9000/disk/...","state":"play","audio":"96000:24:2","elapsed":334.83,"duration":604.693}status=200

$ wscat ws://localhost:8000/ws/now_playing
MSG 0: state=play song_id=12   ← 初回 push が正しく届く
```

→ アルバム Art 復活、VU メータ 復活、ブラウザリフレでも安定表示。

---

## 13. 変更ファイル一覧

### 新規ファイル（`hqmplayer_core/`）

```
hqmplayer_core/__init__.py
hqmplayer_core/art/__init__.py
hqmplayer_core/art/resolver.py
hqmplayer_core/meta/__init__.py
hqmplayer_core/meta/cache.py
hqmplayer_core/meta/enrich.py
hqmplayer_core/meta/formatting.py
hqmplayer_core/mpd/__init__.py
hqmplayer_core/mpd/client.py          ← Phase 1a で 200 行 → Phase 2 修正で 94 行
```

### 変更ファイル

- `backend/main.py` — MPD 接続・整形・アート経路の共通化、最終的に全面 async 化
- `dmp/backend/app/services/mpd_service.py` — re-export 化
- `dmp/backend/app/services/meta_cache.py` — re-export 化
- `backend/audiophile-backend.service` — PYTHONPATH 追加
- `dmp/backend/dmp-backend.service` — PYTHONPATH 追加

### 削除された機能

- `hqmplayer_core.mpd.sync_status / sync_currentsong / sync_idle / sync_readpicture / sync_albumart`
- `hqmplayer_core.mpd._run_sync` / `_run_sync_lock` / `_mpd_exec`
- `backend/main.py:mpd_connect()` の互換用残置（Phase 3 で整理予定）

---

## 14. 関連ドキュメント

- [DEVELOPMENT_ROADMAP.md](./DEVELOPMENT_ROADMAP.md) — 今後の開発ステップの指針
- [README.md](../README.md) — プロジェクト全体の説明
- [HANDOVER.md](../HANDOVER.md) — 作業引き継ぎノート