# Development Roadmap — HQ Linux Music Player

DSP / DMP バックエンド統合後の開発指針。
Phase 2 修正までの教訓を踏まえ、新規参加者でも迷わない構成。

> **最終更新**: Phase 2 修正完了時点（`integ` ブランチ `62587c0`）
>  **現在のステータス**: Phase 0〜2 完了、Phase 3〜5 は今後の作業

---

## 目次

1. [現在の状態サマリ](#1-現在の状態サマリ)
2. [アーキテクチャ原則（必読）](#2-アーキテクチャ原則必読)
3. [Phase 3: FastAPI ルータ統合](#3-phase-3-fastapi-ルータ統合)
4. [Phase 4: 旧 backend 退役](#4-phase-4-旧-backend-退役)
5. [Phase 5: systemd unit 統合](#5-phase-5-systemd-unit-統合)
6. [オプション改善タスク](#6-オプション改善タスク)
7. [テスト戦略](#7-テスト戦略)
8. [開発ワークフロー](#8-開発ワークフロー)
9. [トラブルシューティング](#9-トラブルシューティング)
10. [判断に迷ったときのチェックリスト](#10-判断に迷ったときのチェックリスト)

---

## 1. 現在の状態サマリ

### 1 1 ブランチ構成

| ブランチ | 役割 |
|  --- | --- |
| `MX` | 本番運用中の DSP backend のメインライン（Phase 0 まで） |
| `integ` | 統合作業用ブランチ（Phase 0〜2 修正まで完了） |
| `Standalone` | 単独 DSP 機能ブランチ（参照用） |
| `ambience-fix` | 過去の修正（参照用） |

### 1 2 コミット履歴（`integ` ブランチ）

```
62587c0 Phase 2 修正: MPD クライアントを async 専用化
5f46f33 Phase 2 準備: systemd unit の PYTHONPATH 追加と WebSocket 修正
6694ba5 Phase 1d: アルバムアート経路を共通モジュールに統合
1ea19d5 Phase 1c: meta_cache を共通モジュールに統合
d8faa57 Phase 1b: 整形ロジックを共通モジュールに統合
a297dd6 Phase 1a: MPD 接続モデルを共通モジュールに統一
57ce7e2 Phase 0: hqmplayer_core 共有モジュール骨格を追加
```

### 1 3 ディレクトリ構成

```
HQ_Linux_Music_Player/
├── hqmplayer_core/                ← 共有モジュール（Phase 1〜2 で構築）
│   ├── mpd/                       ← MPD クライアント（async 専用）
│   ├── meta/                      ← メタデータ整形・キャッシュ
│   └── art/                       ← アルバムアート解決
├── backend/                       ← DSP バックエンド (port 8000)
│   ├── main.py                    ← FastAPI エントリ
│   ├── audiophile-backend.service ← systemd unit
│   └── scripts/switch_audio.sh    ← DSP モード切替
├── dmp/
│   └── backend/                   ← DMP バックエンド (port 8001)
│       ├── app/
│       │   ├── main.py
│       │   ├── routers/           ← FastAPI ルータ
│       │   ├── services/          ← サービス層（一部は re-export）
│       │   └── models/            ← Pydantic モデル
│       └── dmp-backend.service    ← systemd unit（実体は hq-dmp-backend.service）
├── unified-shell/                 ← Next.js フロントエンド（DSP 統合 UI）
├── unified-frontend/              ← 旧フロントエンド（DSP + DMP 切替）
├── frontend/                      ← DSP 単独フロントエンド
├── docs/                          ← 設計・手順ドキュメント
│   ├── BACKEND_UNIFICATION_WALKTHROUGH.md
│   └── DEVELOPMENT_ROADMAP.md     ← このファイル
├── ai/                            ← AI セッション履歴
└── config/                        ← システム設定ファイル
```

### 1 4 起動中のサービス

```bash
sudo systemctl status audiophile-backend.service    # DSP (port 8000)
sudo systemctl status hq-dmp-backend.service        # DMP (port 8001)
sudo systemctl status audiophile-frontend.service   # Next.js DSP UI
sudo systemctl status hq-dmp-frontend.service       # Next.js DMP UI
```

### 1 5 動作確認済みエンドポイント

| サービス | エンドポイント | 状態 |
|  --- | --- | --- |
| DSP | `/api/devices` | ✅ 200 |
| DSP | `/api/now_playing` | ✅ 200 |
| DSP | `/api/dsp_status` | ✅ 200 |
| DSP | `/api/art` | ✅ 307 (iTunes リダイレクト) |
| DSP | `/ws/now_playing` | ✅ push 配信 |
| DMP | `/api/library/artists` | ✅ 200 |
| DMP | `/api/playback/status` | ✅ 200 |
| DMP | `/api/queue/` | ✅ 200 |
| DMP | `/ws/status` | ✅ push 配信 |

---

## 2. アーキテクチャ原則（必読）

新規参加者・今後の作業者は**必ずこのセクションを通読**してください。
Phase 2 修正で痛感した教訓が凝縮されています。

### 2 1 原則 1: Loop は 1 つ

> **「メインのイベント loop を 1 つに統一する」** が大原則。

**禁止事項**:

```python
# ❌ 絶対にやってはいけない
def sync_status():
    async def _get():
        async with mpd_connection() as c:
            return await c.status()
    return _run_sync(_get())  # asyncio.new_event_loop() で別 loop を立てる

@app.get("/api/now_playing")
def get_now_playing():  # FastAPI が run_in_executor で別スレッドに逃がす
    st = sync_status()   # ← 別スレッド + 別 loop = マルチ loop 競合
```

**正しい形**:

```python
# ✅ これが正解
@app.get("/api/now_playing")
async def get_now_playing():
    async with mpd_connection() as c:
        st = await c.status()
```

### 2 2 原則 2: async or sync を混ぜない

| ハンドラ | 使える I/O |
|  --- | --- |
| `async def` | メイン loop 上で `await mpd_connection()` |
| `def` | 別ライブラリ（ファイル I/O、外部 HTTP、設定ファイル読み込み） |

**`def` ハンドラから MPD 接続を触ってはいけない**。代わりに `async def` に変更する。

### 2 3 原則 3: 共有リソースは 1 つの loop から触る

| リソース | アクセス元 | 注意点 |
|  --- | --- | --- |
| `_client`（MPD ソケット） | メイン loop 1 つだけ | 別 loop から触ると プロトコル混線 |
| `_lock`（asyncio.Lock） | loop 単位 | **複数 loop にまたがるロックは無効** |
| `_cache`（meta_cache 永続化） | スレッドセーフ（dict + `_save()` はファイル IO） | 問題なし |

### 2 4 原則 4: WebSocket は polling でもよい

Phase 2 で `idle` の async generator 取扱いの複雑さが判明したため、
`ws_now_playing` は **2 秒間隔のシンプルな polling** に変更した。
MPD 接続がプロセス全体で 1 本に統一されたため、polling コストは小さい。

### 2 5 原則 5: 共通モジュールは Web フレームワーク非依存

`hqmplayer_core/` は FastAPI 等に依存しない。テスト容易性と将来のフレームワーク移行のため。
**例外**: `hqmplayer_core/mpd/client.py` は `mpd.asyncio` に依存する（MPD 接続のため、不可避）。

---

## 3. Phase 3: FastAPI ルータ統合

**目標**: DSP / DMP の 2 プロセスを 1 プロセスに統合
**想定工数**: 1〜2 週間
**リスク**: 中（systemd 切替を伴う）

### 3 1 やること

1. `hq_api/` パッケージを新設
2.  DSP と DMP の **重複しないルータ群** をマージ
   - DSP: `/api/devices`, `/api/now_playing`, `/api/dsp_status`, `/api/config`, `/api/apply`, `/api/presets`, `/api/art`, `/ws/now_playing`
   - DMP: `/api/library/*`, `/api/playback/*`, `/api/queue/*`, `/api/playlists/*`, `/api/history/*`, `/api/upnp/*`, `/ws/status`
3.  旧 `dmp-backend.service` / `audiophile-backend.service` を **新 `hq-api.service` 1 つに集約**
4.  すべてのエンドポイントを新プロセスで提供（port は 8000 に統一、または別ポートで共存）

### 3 2 段階的アプローチ

| Step | 内容 |
|  --- | --- |
| 3a | 新 `hq_api/` にすべてのルータをコピーし、port 8002 で起動（既存 8000/8001 は生かす） |
| 3b |  既存 8000/8001 を停止、新プロセスに切り替え |
| 3c |  旧 backend コード（`backend/main.py`, `dmp/backend/app/main.py`）を **段階的に削除** |
| 3d |  検証・コミット |

### 3 3 注意点

- **asyncio.Lock はプロセス単位**。プロセス統合後は DSP と DMP が同じ `mpd_connection` を共有する
-  履歴機能（`history_service`）の統合は DSP 側に API が無いので、Phase 3 で DSP 側に追加するか、DMP のみに集約するかを決める
-  UPnP 機能（`upnp_service.py`）も統合対象に。`SERVERS` のハードコードは環境変数化を併せて実施

### 3 4 受け入れ基準

- [ ]  新プロセスが port 8000 で全エンドポイントを提供
- [ ]  systemd 経由で自動起動
- [ ]  アルバムアート表示・VU メータ・Now Playing push が正常動作
- [ ]  旧 8001 ポートは無効化（停止）

---

## 4. Phase 4: 旧 backend 退役

**目標**: 旧 DSP / DMP バックエンドコードの削除
**想定工数**: 0.5〜1 日

### 4 1 やること

1.  `backend/main.py` の DSP 専用部分を新 `hq_api/` に移植完了後、`backend/` を削除
2.  `dmp/backend/app/` の DMP 専用部分を新 `hq_api/` に移植完了後、`dmp/backend/app/` を削除
3.  `audiophile-backend.service` / `hq-dmp-backend.service` を **新 `hq-api.service` に置換**
5.  旧 systemd unit を `disable` して削除
6.  フロントエンドの `.env` で新エンドポイントを参照

### 4 2 注意点

-  **systemd unit の削除前に新プロセスが安定稼働していることを最低 1 週間確認**
-  旧コードは一旦 `legacy/` に退避させ、半年後に完全削除する運用が無難

---

## 5. Phase 5: systemd unit 統合

**目標**: 起動スクリプトの整理
**想定工数**: 0.5 日

### 5 1 やること

1.  `hq-api.service` に **PYTHONPATH / Environment / WorkingDirectory** を設定
2.  旧 `audiophile-backend.service` と `hq-dmp-backend.service` を `disable` + `rm`
3.  起動確認テスト（systemd 再起動で自動復旧するか）

### 5 2 推奨 unit 設定

```ini
[Unit]
Description=HQ Linux Music Player — Unified API
After=network.target mpd.service
Wants=mpd.service
Requires=mpd.service

[Service]
Type=simple
User=tysbox
Group=tysbox
WorkingDirectory=/home/tysbox/HQ_Linux_Music_Player
Environment="PYTHONPATH=/home/tysbox/HQ_Linux_Music_Player"
ExecStart=/home/tysbox/HQ_Linux_Music_Player/venv/bin/python3 -m uvicorn hq_api.main:app --host 0.0.0.0 --port 8000 --log-level info
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hq-api

[Install]
WantedBy=multi-user.target
```

---

## 6. オプション改善タスク

優先度順に：

|  優先度 | タスク | 影響範囲 |
|  --- | --- | --- |
|  高 | 履歴機能を DSP 側にも追加（または DMP 側に集約） | 機能追加 |
|  高 |  DMP `/api/library/artwork` を `resolve_art()` 経由に拡張 | 機能統一 |
|  中 |  旧 `mpd_connect()` の削除（DSP backend 互換用残置） | コード整理 |
|  中 |  UPnP `server_id` の を環境変数化（現状はハードコード） | 運用性 |
|  中 |  単体テスト導入（pytest + aiompd モック） | 品質 |
|  低 |  `_check_local_art` の dirname バグ修正（`os.path.exists` が False のときにフルパスを dirname にする問題） | エッジ |

### 6 1 履歴機能の統合方針

現状：
- DMP 側：`add_to_history(track)` を `playback.py:next_track()` で呼ぶ
- DSP 側：履歴機能なし

**推奨**：履歴機能を `hqmplayer_core.history.service` に移植し、両 backend から同じ実装を使う。
バックエンド統合後は DSP 側 も自動的に履歴を持つ。

### 6 2 UPnP サーバー定義の環境変数化

```python
# 現状（upnp_service.py）
SERVERS = {
    "soundgenic": {"ip": "192.168.0.116", ...},
    ...
}

# 推奨
def _load_servers() -> dict:
    return {
        "soundgenic": {"ip": os.getenv("HQM_SOUNDGENIC_IP", "192.168.0.116"), ...},
        ...
    }
```

---

## 7. テスト戦略

### 7 1 単体テスト（`tests/` を新設）

```
tests/
├── test_meta_enrich.py
├── test_meta_formatting.py
├── test_meta_cache.py
├── test_art_resolver.py
└── test_mpd_client.py  （モック使用）
```

`pytest` + `pytest-asyncio` を使用。`aiompd` のモックは `unittest.mock.AsyncMock` で実装。

```python
# テスト例
async def test_mpd_connection_ping_reconnect():
    """ping 失敗時に再接続することを確認"""
    from unittest.mock import AsyncMock, patch
    from hqmplayer_core.mpd import mpd_connection
    
    with patch("hqmplayer_core.mpd.client._connect") as mock_connect:
        mock_c = AsyncMock()
        mock_c.ping.side_effect = [ConnectionError, None]
        mock_connect.return_value = mock_c
        async with mpd_connection() as c:
            assert c is mock_c
        assert mock_connect.call_count == 2
```

### 7 2 統合テスト（実機）

```bash
# /api/now_playing の連続呼び出し（スレッド競合確認）
for i in 1 2 3 4 5; do
    curl -sf http://localhost:8000/api/now_playing > /dev/null \
        || echo "FAIL $i"
done

# WebSocket 初回 push 確認
python3 -c "
import asyncio, json, websockets
async def t():
    async with websockets.connect('ws://localhost:8000/ws/now_playing') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(json.loads(msg))
asyncio.run(t())
"
```

### 7 3 ブラウザシナリオテスト

`unified-shell/` を `pnpm dev` または `pnpm build && pnpm start` で起動し、以下を確認：

- [ ] アルバムアートが永続的に表示される（リフレ後でも消えない）
- [ ] VU メータが反応する
- [ ] Now Playing の曲情報が更新される
- [ ] ライブラリ / キュー / プレイリストが操作可能
- [ ] DSP 設定変更が反映される

---

## 8. 開発ワークフロー

### 8 1 新機能追加の手順

1.  **issue  で議論**（または個人メモ）
2.  **`integ` ブランチで作業**（本番運用中の `MX` を直接触らない）
3.  `hqmplayer_core/` に新機能を追加する場合は **docstring + type hints 必須**
4.  Web フレームワーク（FastAPI）に依存しないことを確認
5.  単体テスト追加（該当する場合）
6.  systemd 再起動 → 実機検証
7.  コミット・プッシュ

### 8 2 バグ修正の手順

1.  **再現手順をログ / journal から確認**（`sudo journalctl -u audiophile-backend.service -n 50`）
2.  **テストで再現**（必要なら追加）
3.  `integ` ブランチで修正
4.  検証（実機）
6.  コミット・プッシュ

### 8 3 コミットメッセージ規約

```
<Phase or 種別>: <要約>

<詳細>

検証済み:
- <検証項目>
- <検証項目>
```

例：

```
Phase 3: DMP /api/library/artwork を resolve_art() 経由に拡張

DMP backend のアルバムアート取得も共通 resolve_art() を使うようにし、
DSP / DMP 間のアート戦略を完全統一する。

検証済み:
- /api/library/artwork?uri=... で iTunes フォールバックが動作
- /api/art?file=... も同じ結果
```

---

## 9. トラブルシューティング

### 9 1 WebSocket が push を出さない / `/api/now_playing` が 503

**症状**: ブラウザでアルバムアート・VU メータ が消える。

**真因候補**: マルチイベント loop競合。Phase 2 修正前の `sync_*` が残っていないか確認。

```bash
# sync_* が残っていないか確認
grep -rn "sync_status\|sync_currentsong\|sync_idle\|sync_readpicture\|sync_albumart\|new_event_loop\|_run_sync" hqmplayer_core/ backend/ dmp/

# 検出された場合
# - hqmplayer_core/mpd/client.py に sync_* があれば削除
# - backend/main.py の def ハンドラがあれば async def に変更
# - 共通モジュールの mpd_connection を直接 await するように修正
```

### 9 2 MPD 切断検出が頻発

**症状**: ログに `MPD切断検出、再接続します` が連発。

**真因候補**: 別プロセスから同じ MPD に接続しようとして競合、または上のマルチ loop 問題。

```bash
# MPD への接続元を確認
ss -tnp | grep :6600

# 期待値: DSP と DMP から 1 本ずつ、合計 2〜3 本程度
# 異常値: 多数、または、短時間で connect/disconnect が頻発
```

### 9 3 systemd unit が見つからない

```bash
# 正式名称を確認
systemctl list-unit-files | grep -iE 'hq|dmp|audiophile|music'

# 期待値:
#   audiophile-backend.service        ← DSP
#   hq-dmp-backend.service          ← DMP（dmp-backend.service ではない）
```

### 9 4 `_check_local_art` の dirname バグ

**症状**: ファイル存在しないときに `dirname` がフルパスを返すため、ローカルアートがヒットしない。

**修正案**:

```python
def _check_local_art(filepath: str) -> Optional[str]:
    if filepath.startswith("http"):
        try:
            filepath = urllib.parse.unquote(urlparse(filepath).path)
        except Exception:
            pass
    dirname = os.path.dirname(filepath) if os.path.exists(filepath) else os.path.dirname(filepath)
    # ↑ False のときでも dirname を使う（フルパスを dirname にすべき）
    if not dirname:
        return None
    for name in ("Folder.jpg", "folder.jpg", "cover.jpg", "Cover.jpg"):
        path = os.path.join(dirname, name)
        if os.path.exists(path):
            return path
    return None
```

---

## 10. 判断に迷ったときのチェックリスト

新しいコードを書く前に、以下を確認：

- [ ]  ハンドラは `async def` か？（`def` で MPD を触っていないか？）
- [ ]  MPD 接続は `async with mpd_connection()` を直接 await しているか？（`sync_*` を使っていないか？）
- [ ]  WebSocket で `await loop.run_in_executor()` や `asyncio.to_thread()` を使って MPD 接続に触っていないか？
- [ ]  共通モジュールは FastAPI 等の Web フレームワークに依存していないか？
- [ ]  systemd unit に PYTHONPATH が設定されているか？

###  チェックリストに引っかかったら

| 引っかかった項目 | 対処 |
|  --- | --- |
|  `def` ハンドラで MPD を触ろうとしている |  `async def` に変更 |

---

## 11. 追加フェーズ: 再生品質・信頼性の強化（Phase 3.5 / 4.5 / 5.5）

プロセス統合（Phase 3〜5）に加えて、**再生システムの安定性と音質**を直接的に底上げする
3 つの追加フェーズを定義する。各 Phase 3.5/4.5/5.5 は、対応する番号の Phase 完了直後に
実施する。

### 11 1 Phase 3.5: 再生パイプラインの統合と品質向上

**目標**: 1 プロセス統合で懸念される `asyncio.Lock` 共有問題を事前に潰し、
**CamillaDSP のホットリロードと音量正規化**を共通層に持ち込む。

**想定工数**: 1〜1.5 週間
**リスク**: 中（MPD 接続分離は本番影響大）

#### やること

1. **MPD 接続の再生専用分離** — `hqmplayer_core.mpd.client` に `mpd_connection(purpose="control" | "playback")` を追加
   - `control`: `status()` / `currentsong()` / `play()` / `pause()` / `next()` などの **短時間 I/O** 用
   - `playback`: `idle()` / `readpicture()` / `albumart()` などの **長時間待ち/ブロッキング I/O** 用
   - それぞれ **別ソケット・別 `asyncio.Lock`** を保持
   - DSP/DMP 統合時に再生ポーリングがアート取得でブロックされる問題を根絶
2. **CamillaDSP ホットリロード** — `hqmplayer_core.dsp.reload(config_dict)` を実装
   - `camilladsp.apply()` を async 化（既存は同期）
   - systemd unit に `SIGHUP` ハンドラを追加 → 設定ファイル更新で自動反映
3. **ReplayGain 統一** — `hqmplayer_core.meta.replay_gain.apply()` を実装
   - MPD の `replay_gain_mode` を `hqmplayer_core` 経由で一元管理
   - DSP/DMP 両方の `/api/playback/status` に `replay_gain_db` を含めて返す
4. **バッファリング最適化** — `hqmplayer_core.mpd.config.apply_buffering()` を実装
   - MPD の `buffer_before_play` を UPnP ストリームとローカルファイルで別プロファイルに

#### 受け入れ基準

- [ ]  `purpose` フラグを切り替えても MPD プロトコルエラーが **0 件 / 24h**
- [ ]  CamillaDSP 設定変更後 **1 秒以内** に新プロファイルが反映
- [ ]  `/api/playback/status` に `replay_gain_db` が含まれる
- [ ]  UPnP ストリームの再生開始遅延が **500ms 以下**

### 11 2 Phase 4.5: 再生信頼性の強化

**目標**: 旧 backend 退役と並行して、**「MPD 切断」「WebSocket 切断」「プロセス再起動」** の
3 大障害に対する自動回復を完成させる。

**想定工数**: 1 週間
**リスク**: 低（既存ロジックの拡張が中心）

#### やること

1. **MPD 自動再接続バックオフ** — `mpd_connection()` 内の再接続ロジックを **指数バックオフ**化
   - 初期待機 100ms → 最大 5s まで倍々に
   - 連続失敗が 10 回に達したら `_client = None` にして次回 `connect()` からやり直し
   - 起動時の MPD 未起動状態でも 503 を返さず、**graceful に待つ** ように
2. **WebSocket ヘルスチェック** — `ws_now_playing` / `ws_status` に **30 秒間隔の ping/pong** を追加
   - pong が 3 回連続未応答でサーバ側から切断
   - クライアント側 (`unified-shell/`) に `reconnect with backoff` を実装
3. **再生状態の永続化** — `hqmplayer_core.playback.state` を新設
   - 再生中/停止中/曲 ID/ボリューム を **3 秒ごとに** `~/.hqmplayer/playback_state.json` に保存
   - プロセス再起動時に **最後に再生していた曲の先頭から** 自動再開（オプトイン設定）

#### 受け入れ基準

- [ ]  MPD 停止中に backend を起動しても 503 を出さず、MPD 起動後 **1 秒以内** に復旧
- [ ]  WebSocket を意図的に切断してから 30s 以内に **自動再接続** される
- [ ]  systemd 再起動後、最後の再生状態が復元される（オプトイン時のみ）

### 11 3 Phase 5.5: 音質監視とメトリクス

**目標**: 音質と体感品質を **数値で測定できる状態** にする。
聴感テストだけに頼らず、**機械的に品質劣化を検知** できる基盤を整える。

**想定工数**: 1 週間
**リスク**: 低（追加エンドポイントと UI のみ）

#### やること

1. **VU メータデータの高解像度化** — `hqmplayer_core.playback.vu` を実装
   - 10ms 間隔の `status()` ポーリングタスク
   - `left` / `right` の RMS を 16bit で返却
2. **音声遅延測定エンドポイント** — `GET /api/dsp_status` を拡張
   - CamillaDSP の `GetLatency()` を 1 秒間隔でキャッシュ
   - `latency_ms` をレスポンスに含める
3. **再生履歴の統計 API** — `hqmplayer_core.history.stats` を実装
   - 再生回数 / 時間帯別ヒストグラム / よく聴くアーティスト Top 10
   - `GET /api/history/stats?days=30` で取得

#### 受け入れ基準

- [ ]  VU メータのフレームレートが **50fps 以上**（20ms 以下の更新間隔）
- [ ]  `/api/dsp_status` に `latency_ms` が含まれ、**±1ms の精度** で取得できる
- [ ]  `/api/history/stats` が **100ms 以内** にレスポンスを返す

---

## 12. 再生品質 SLA（Service Level Agreement）

Phase 5.5 完了時点から **24 時間連続運用** した状態で、以下を保証する。

| 指標 | 目標値 | 測定方法 | 計測箇所 |
|  --- | --- | --- | --- |
| **WebSocket 接続確立率** | 99.9% 以上 | ping 応答成功率 / 接続試行数 | `unified-shell/` の E2E テスト |
| **`/api/now_playing` レイテンシ** | 200ms 以下 (p95) | `curl -w '%{time_total}\n'` を 1 分間隔で 24h 実行 | cron + journal 解析 |
| **アルバムアート表示率** | 95% 以上 | 再生曲のうち `/api/art` が 200/307 を返す割合 | ブラウザ E2E テスト |
| **MPD 再接続成功率** | 99% 以上 | MPD 切断後 10s 以内に復旧した回数 / 切断回数 | `journal` 解析 |
| **VU メータ フレームレート** | 50fps 以上 (p95) | `unified-shell/` で計測 | ブラウザ E2E テスト |
| **DSP 設定反映時間** | 1s 以内 | 設定変更 → `latency_ms` 変化の検知 | 手動 + 自動テスト |

### 12 1 SLA 計測の実装

`tests/sla/` を新設し、24 時間の負荷試験を CI で実行：

```
tests/sla/
├── test_websocket_availability.py    # WebSocket 接続成功率
├── test_now_playing_latency.py       # /api/now_playing レイテンシ
├── test_art_availability.py          # /api/art の表示率
├── test_mpd_reconnect.py             # MPD 切断/再接続シナリオ
└── test_dsp_reload.py                # DSP 設定反映時間
```

### 12 2 SLA 違反時の対応フロー

1. CI で SLA 違反を検知 → 自動で GitHub Issue を作成
2. `journal` から該当時刻のログを抽出
3. `BACKEND_UNIFICATION_WALKTHROUGH.md` の「トラブルシューティング」セクションを参照
4. 該当 Phase のテストケースを追加して再発防止

---

## 13. 改編後のフェーズ全体像

```
Phase 0〜2    : 共有モジュール構築（完了済み）
Phase 3      : FastAPI ルータ統合
Phase 3.5    : 再生パイプライン統合と品質向上   ★ NEW
Phase 4      : 旧 backend 退役
Phase 4.5    : 再生信頼性の強化                 ★ NEW
Phase 5      : systemd unit 統合
Phase 5.5    : 音質監視とメトリクス             ★ NEW
SLA 達成     : 24h 連続運用で 12 章の指標を満たす  ★ NEW
```

**凡例**: ★ NEW = 本評価を受けて追加したフェーズ

### 13 1 改編の根拠

| 追加 | 根拠（評価より） |
|  --- |  --- |
| Phase 3.5-1 (MPD 接続分離) | 「プロセス統合時の `asyncio.Lock` 共有問題」への直接対策 |
| Phase 3.5-2 (DSP ホットリロード) | 音質向上に直結する DSP 切替の即時性確保 |
| Phase 3.5-3/4 (ReplayGain/バッファ) | 音量差・ストリーム遅延の体感品質改善 |
| Phase 4.5-1 (再接続バックオフ) | 起動時 503 連発問題の根絶 |
| Phase 4.5-2/3 (WebSocket HC / 状態永続化) | ブラウザリフレ・プロセス再起動時の体験向上 |
| Phase 5.5-1/2 (VU / 遅延測定) | 音質とレイテンシの**数値化**でチューニング基盤を提供 |
| Phase 5.5-3 (履歴統計) | ユーザーの聴取傾向分析 |
| SLA 12 章 | 全ての追加フェーズが**目標を達成したか**を機械的に判定 |

---

## 14. Phase 3 着手前チェックリスト

Phase 3 は「山場」となる統合作業。着手前に**必ず**以下を完了させること。

### 14 1 事前調査（完了済み: integ `479f4b9`）

| # | タスク | 成果物 | 状態 |
|---|---|---|---|
| A | MPD 呼び出し箇所の全件 grep | `docs/adr/ADR-001` に整理 | ✅ |
| B | ルータ・サービスの依存関係マップ | `docs/adr/ADR-002` に整理 | ✅ |
| C | WebSocket 実装比較と統合設計 | `docs/adr/ADR-003` に整理 | ✅ |
| D | systemd unit の環境変数整理 | `docs/adr/ADR-004` §systemd 統合準備 | ✅ |
| E | レスポンススナップショット取得 | `tests/snapshots/*.json` (17 ファイル) | ✅ |

### 14 2 ADR レビュー（着手前必須）

| ADR | タイトル | 承認の判断ポイント |
|---|---|---|
| [ADR-001](docs/adr/ADR-001-mpd-connection-separation.md) | MPD 接続分離 | `purpose` パラメータで OK か / デフォルト `"control"` で互換維持 |
| [ADR-002](docs/adr/ADR-002-router-package-structure.md) | ルータ統合 | `hq_api/` 新設で OK か / 8002 での並行稼働で OK か |
| [ADR-003](docs/adr/ADR-003-websocket-integration.md) | WebSocket 統合 | 2 系統維持の方針で OK か / `/ws/all` 追加時期 |
| [ADR-004](docs/adr/ADR-004-dsp-feature-boundary.md) | DSP 機能境界 | 全機能を `hq_api` に移植で OK か |
| [ADR-005](docs/adr/ADR-005-error-handling-strategy.md) | エラーハンドリング | 統一形式 `{error: {code, message}}` で OK か |

### 14 3 ロールバック体制（必須）

- **作業ブランチ**: `integ` から `phase3-integ` を切る（`integ` を直接汚さない）
- **旧 backend の systemd unit は当面 `disable` せず残す**
  - `audiophile-backend.service` (port 8000)
  - `hq-dmp-backend.service` (port 8001)
- **緊急時の戻し方**:
  ```bash
  sudo systemctl stop hq-api
  sudo systemctl start audiophile-backend hq-dmp-backend
  ```
  旧 2 プロセス構成に 30 秒以内に戻る
- **スナップショット検証**:
  ```bash
  # Phase 3 実装後に比較
  diff <(curl -s http://localhost:8000/api/now_playing) tests/snapshots/dsp__api_now_playing.json
  ```

### 14 4 着手前ミーティングで確認すべき事項

1. **URL パス方針**: `/api/now_playing` と `/api/playback/status` のどちらに統一するか
2. **WebSocket 方針**: `/ws/all` を追加するか、当面 2 系統維持か
3. **統合 backend のポート番号**: `8000`（DSP 互換）か `8002`（新ポート）か
4. **UPnP 設定の環境変数化**: Phase 3 に含むか、Phase 3.5 に分離するか
5. **履歴機能の DSP 側露出**: DSP 側にも `/api/history` を追加するか

### 14 5 Phase 3 の想定工数（再掲）

| Step | 内容 | 工数 |
|---|---|---|
| 3a | `hq_api/` を port 8002 で並行起動 | 2〜3 日 |
| 3b | 旧 backend 停止、`hq_api` を 8000 で起動 | 0.5 日 |
| 3c | 旧 main.py 段階削除、テスト | 1 日 |
| 3d | 検証・コミット | 0.5〜1 日 |
| **合計** | | **3.5〜4.5 日** |

---

## 15. 進捗サマリ

| コミット | 内容 | 日付 |
|---|---|---|
| `512af77` | DEVELOPMENT_ROADMAP に Phase 3.5/4.5/5.5 と SLA 章を追加 | 2026-09-02 |
| (snapshot) | Phase 3 着手前のエンドポイント応答スナップショット取得 (17 ファイル) | 2026-09-02 |
| `479f4b9` | Phase 3 着手前の ADR ドラフト 5 件作成 | 2026-09-02 |
| **次の作業** | Phase 3 着手前チェックリスト (§14) のレビューと合意 | TBD |

### 13 2 想定工数の合算

| フェーズ | 既存 (週) | 追加 (週) | 累計 (週) |
|  --- | --- | --- | --- |
| Phase 3 | 1〜2 | +1.5 (3.5) | 2.5〜3.5 |
| Phase 4 | 0.5〜1 | +1.0 (4.5) | 1.5〜2.0 |
| Phase 5 | 0.5 | +1.0 (5.5) + SLA 計測 | 2.0 程度 |
| **合計** | **2〜3** | **+3.5** | **6〜7.5** |
|  `sync_*` を使っている |  共通モジュールの `mpd_connection` を直接 await |
|  `await loop.run_in_executor()` で MPD を触ろうとしている |  止める。`async with mpd_connection()` を使う |
|  共通モジュールが Web フレームワークに依存している |  依存を外す（DI で注入する形に） |
|  PYTHONPATH が設定されていない |  systemd unit に `Environment="PYTHONPATH=..."` を追加 |

---

## 11. 参考コミット

Phase 2 修正までの実装参考になる主要コミット：

| コミット | 内容 |
|  --- | --- |
| `62587c0` | MPD クライアント async 化（マルチ loop 競合解消） |
| `5f46f33` | systemd unit + WebSocket 修正 |
| `6694ba5` | Phase 1d: アルバムアート統合 |
| `1ea19d5` | Phase 1c: meta_cache 統合 |
| `d8faa57` | Phase 1b: 整形ロジック統合 |
| `a297dd6` | Phase 1a: MPD 接続モデル統一 |
| `57ce7e2` | Phase 0: 共有モジュール骨格 |

各コミットは **「外部観測不変」を維持** しているので、revert / cherry-pick が可能。

---

## 12. 次の担当者へのメッセージ

Phase 2 修正で痛感したことは、**「async/event-loop の競合は単体テストでは検出できない」** ことです。
必ず systemd 経由で再起動し、ブラウザリフレまで含めた実機検証を行ってください。

不明点があれば、`docs/BACKEND_UNIFICATION_WALKTHROUGH.md` とこのファイル、
および `integ` ブランチのコミット履歴を順に追っていただければ、設計の意図と経緯が理解できるはずです。

よろしくお願いします。