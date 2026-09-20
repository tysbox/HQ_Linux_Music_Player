# HQ Linux Music Player - 実システム構造分析レポート

**作成日**: 2026年9月20日  
**対象**: 実稼働システム (Backend: hq_api:8002 / Frontend: new-gui on port 3003)
**現状**: **正常動作中** (`health: ok, mpd: connected`)。API層は堅牢。フロントエンドは port 3003 で `new-gui` Next.js (standalone) が稼働中。

---

## 1. アーキテクチャ全体像（動いている理由）

```
┌─────────────────────────────────────────────────────────────────┐
│  new-gui (Next.js Standalone) ← 実UI (port 3003)               │
│  └─ lib/api.ts → 8002 (hq_api)                                   │
├─────────────────────────────────────────────────────────────────┤
│  hq_api (FastAPI) :8002       ← 統合バックエンド                 │
│  ├─ routers/dsp.py            ← 読み取り専用 (安全)              │
│  ├─ routers/dsp_readonly.py   ← GETのみ + プリセット/アート/プロファイル │
│  ├─ routers/dsp_write.py      ← ファイルI/Oのみ (中リスク)       │
│  ├─ routers/dsp_apply.py      ← CamillaDSP再起動/ALSA切替 (高リスク)│
│  ├─ routers/dmp.py            ← DMPルータ再エクスポート (sys.path) │
│  ├─ ws/now_playing.py         ← MPD idle駆動 WS (DSP互換)        │
│  ├─ ws/status.py              ← MPD idle駆動 WS (DMP互換+履歴)   │
│  └─ ws/all.py                 ← 統合WS                           │
├─────────────────────────────────────────────────────────────────┤
│  hqmplayer_core (共通カーネル)                                    │
│  ├─ mpd/client.py             ← 非同期MPD接続 (共有+idle分離)    │
│  ├─ art/resolver.py           ← アート解決 (local→MPD→iTunes→SVG) │
│  └─ meta/                     ← 整形・キャッシュ                  │
│      ├─ formatting.py         ← format_now_playing (統一)         │
│      ├─ enrich.py             ← song_to_track                     │
│      └─ cache.py              ← UPnPメタ永続キャッシュ            │
├─────────────────────────────────────────────────────────────────┤
│  backend/dsp/ (DSP専用ロジック)                                   │
│  ├─ yaml_generator.py         ← CamillaDSP YAML生成 (重い計算込み)│
│  ├─ apply_logic.py            ← 適用フロー (ロック/音量復帰/重複排除)│
│  ├─ state_manager.py          ← 設定永続化/正規化/前提チェック    │
│  ├─ profiles.py               ← JSON Schema検証付きプロファイル   │
│  └─ analysis.py               ← RBJ Biquad / 周波数応答解析       │
├─────────────────────────────────────────────────────────────────┤
│  dmp/backend/app/ (DMP機能・sys.pathで再利用)                     │
│  └─ routers/* + services/*    ← ライブラリ/再生/キュー/UPnP等     │
└─────────────────────────────────────────────────────────────────┘
```

### なぜ快適に動くのか

| 設計判断 | 理由 | 効果 |
|----------|------|------|
| **ルータをリスク別に分離** | readonly/write/apply で責務分離 | 障害域限定、デプロイ順序制御可能 |
| **hqmplayer_core を共通カーネル化** | MPD/アート/メタをDSP/DMPで共有 | 二重実装排除、振る舞い統一 |
| **threading.Lock で同期エンドポイント直列化** | FastAPIは `def` をスレッドプール実行 | 非同期化コストなしで競合防止 |
| **switch_audio.sh を外部スクリプト化** | ALSA/CamillaDSP/loopback の複雑な連携 | Python側をシンプルに、シェルで確実に制御 |
| **MPD接続を共有+idle専用分離** | `mpd_connection` (共有) + `mpd_idle_connection` (独立) | /health等の通常リクエストがidleでブロックされない |
| **Phaseコメントで履歴管理** | 段階的移植の痕跡をコードに残す | レビュー・ロールバック容易 |
| **statefile で音量永続化** | CamillaDSP 4.1.3 対応 `-s/--statefile` | 再起動時も音量・mute 維持 |
| **apply_audio の重複排除・音量強制復帰** | `_APPLY_INFLIGHT` + `last_config.volume` 採用 | 連続Apply嵐防止、Apply後音量復帰 |
| **yaml_generator の自動ヘッドルーム計算** | Stage 2 解析モジュールで最大ゲイン算出 | クリッピング防止、安全マージン確保 |

---

## 2. 実用上の技術的負債（改善すべき実在する課題）

### 2.1 `/api/presets/save` の重複実装 **【バグ】**

**場所**: `hq_api/routers/dsp_readonly.py` L152-170 と `dsp_write.py` L40-58

```python
# 両ファイルで全く同一の実装
@router.post("/api/presets/save")
def save_preset(body: PresetSave): ...
```

**影響**: FastAPIのルート登録順でどちらかが勝つ（未定義動作）。現在は `dsp_readonly` が後勝ちの可能性。
**修正**: `dsp_readonly.py` 側を削除（`dsp_write.py` に統合済み）。

---

### 2.2 エラーレスポンスの不統一 **【仕様不統一】**

| エンドポイント | 成功 | 失敗 | 問題 |
|--------------|------|------|------|
| `/api/now_playing` | dict | `JSONResponse(503)` | 例外握りつぶし |
| `/api/dsp_status` | dict | `{"status":"stopped","error":...}` | **200でエラー返却** |
| `/api/volume` | dict | `HTTPException(503)` | 正しい |
| `/api/apply` | dict | `{"status":"error",...}` | **200でエラー返却** |
| `/api/dsp_update` | dict | `JSONResponse(422)` | 正しい |

**影響**: フロントエンド (`new-gui/src/lib/api.ts`) が `res.ok` 判定でエラー検知できない箇所がある。
**修正**: `hq_api/errors.py` に統一ユーティリティ追加し、全ルータで `HTTPException` または `JSONResponse(status_code=...)` に統一。

---

### 2.3 `/api/volume` の同期ブロッキング（最大10秒スレッド占有）

**場所**: `hq_api/routers/dsp_write.py` L68-103

```python
def set_volume(vol: VolumeControl):
    with DSP_LOCK:
        for attempt in range(200):  # 200 × 50ms = 10秒
            time.sleep(0.05)
            # CamillaClient 接続試行...
```

**影響**: FastAPIのスレッドプール (デフォルト40) を1リクエストで最大10秒占有。同時ボリューム変更でスレッド枯渇。
**修正**: `async def` 化し `await asyncio.sleep(0.05)` + `asyncio.to_thread(CamillaClient...)` または `httpx` 非同期化。

---

### 2.4 MPD idle接続がWebSocket毎に作成される（スケール限界）

**場所**: `hq_api/ws/now_playing.py` L79, `ws/status.py` L74

```python
async with mpd_idle_connection() as idle_client:
    async for changed in idle_client.idle([...]):
```

**現状**: 接続数 = WebSocket 接続数分のMPD接続。100クライアントなら100MPD接続。
**修正**: 単一の `MPDEventHub` (pub/sub) で `idle()` 監視し、全WSにブロードキャスト。

---

### 2.5 `generate_camilladsp_yaml()` の毎回重複計算

**場所**: `backend/dsp/yaml_generator.py`

- `MUSIC_EQ`/`OUTPUT_EQ` 等からBiquad係数を毎回計算
- `_detect_alsa_cards()` → `aplay -l` を毎回subprocess実行
- IRファイル存在チェックを毎回 `os.path.exists`

**影響**: `/api/dsp_update` (ダイヤル操作毎) で数百ms〜秒オーダーの遅延。
**修正**: 起動時1回計算・キャッシュ、ALSAカード検出を起動時のみ、IR存在チェックを起動時スキャン+セット化。

---

### 2.6 `loopback-drain.service` の残骸コード

**場所**: `backend/scripts/switch_audio.sh` L22-35, L165-175

```bash
# 明示的に masked・無効化済み（2026-09-05 修正）
# loopback_drain_ctl unmask || true
# loopback_drain_ctl stop || true
```

**現状**: コメントアウトされた呼び出しコードが残存。混乱の元。
**修正**: 当該関数 `loopback_drain_ctl` とコメントアウト呼び出しを完全削除。

---

### 2.7 フロントエンド構成の分断（混乱源）

| ディレクトリ | 役割 | 状態 |
|-------------|------|------|
| `new-gui/` | **本番フロントエンド** (port 3003, standalone) | 稼働中 |
| `frontend/` | 開発版 / 代替実装 | ポート3000想定、本番未使用 |
| `unified-shell/` | 別実装 / 開発版 | ポート3002想定、並行開発中 |

**影響**: どれが本番か運用ドキュメントで不明。port 3003 は `new-gui` が占有。
**修正**: `frontend/` と `unified-shell/` の役割をドキュメント化、または統合。

---

### 2.8 DMPの `sys.path` 注入（保守性）

**場所**: `hq_api/routers/dmp.py` L10-15

```python
_DMP_BACKEND = os.path.join(..."dmp", "backend")
sys.path.insert(0, _DMP_BACKEND)
from app.routers import ...
```

**現状**: 動くが、型チェック不可・テスト困難・実行順序依存。
**修正**: `dmp/backend` を `pyproject.toml` 化し `pip install -e` で導入、または `hqmplayer_core.meta` 等に機能移植。

---

### 2.9 iTunesアートキャッシュの分散

| 場所 | 用途 | ストレージ |
|------|------|------------|
| `hqmplayer_core/meta/cache.py` | UPnPトラックメタ永続化 | `~/.config/hqmplayer/meta_cache.json` |
| `hq_api/routers/dsp_readonly.py` L32-67 | **iTunesリダイレクトURLキャッシュ** | `~/.cache/audiophile/art/*.json` (TTL 30日) |
| `dmp/backend/app/services/meta_cache.py` | DMP用メタキャッシュ | 別実装 |

**実態**: 目的が異なるため「重複」ではないが、**iTunesキャッシュは `hqmplayer_core.art` に統合すべき** (DSP/DMP双方から利用可能にするため)。

---

## 3. 設計の合理性（批判されがちだが正当な判断）

| 指摘されがちな点 | 実態・理由 | 判定 |
|----------------|-----------|------|
| "ルータ分割しすぎ" | **リスクベース分離** (readonly/write/apply)。デプロイ・レビュー・障害域を制御する実用的パターン | **合理的** |
| "threading.Lock は古い" | FastAPIの `def` はスレッドプール実行。`asyncio.Lock` 化には全呼び出し元を `async def` にする必要があり影響大。現状で十分機能 | **合理的** |
| "sys.path ハックは悪" | DMPを破壊的変更なしで再利用する**過渡的・実用的判断**。package化はコスト対効果で後回し正解 | **合理的** |
| "switch_audio.sh 依存は脆い" | ALSA loopback + CamillaDSP + デバイス切替の**複雑な状態遷移**をシェルで確実に制御。Pythonで再実装するとバグ埋め込みリスク大 | **合理的** |
| "グローバル状態が多い" | 単一プロセス・単一イベントループ前提のアーキテクチャ。**マルチプロセス化するまで不要な複雑性** | **合理的** |
| "同期関数にブロッキングI/O" | `/api/volume` 以外は短時間。ボリュームのみ非同期化すれば解決。全面async化のコストに見合わない | **合理的** |
| "192kHz固定・chunksize 4096" | ビットパーフェクト・高精度処理の要件。CamillaDSP 4.1.3 仕様準拠。LDAC 96kHz 対応の前提 | **合理的** |
| "loopback-drain を masked" | 正常時は CamillaDSP が専有 → drain は競合・CPU無駄・レイテンシ悪化。**廃止が正解** | **合理的** |

---

## 4. 改善優先度マトリクス（実用重視）

| # | 項目 | 優先度 | 理由 | 工数 |
|---|------|--------|------|------|
| 1 | `/api/presets/save` 重複削除 | 🔴 **即時** | バグ・未定義動作 | 5分 |
| 2 | エラーレスポンス統一 (200→proper status) | 🔴 **即時** | フロントエンド検知不能 | 30分 |
| 3 | `/api/volume` 非同期化 | 🟠 **高** | スレッド枯渇リスク | 1h |
| 4 | MPD idle 単一タスク化 (pub/sub) | 🟠 **高** | 接続数スケール限界 | 2h |
| 5 | `generate_camilladsp_yaml` キャッシュ化 | 🟠 **高** | ダイヤル操作の遅延 | 2h |
| 6 | `loopback-drain` 残骸コード削除 | 🟡 **中** | 混乱源・デッドコード | 10分 |
| 7 | iTunesアートキャッシュを core 統合 | 🟡 **中** | 重複排除・再利用 | 1h |
| 8 | DMP package化 (`pip install -e`) | 🟡 **中** | 型安全・テスト容易 | 2h |
| 9 | フロントエンドの役割ドキュメント化 | 🟡 **中** | 運用混乱解消 | 30分 |
| 10 | 依存性注入 (Protocol + Depends) | 🟢 **低** | テスト容易性向上 | 大 |

---

## 5. 具体的修正パッチ（即時適用可能）

### 5.1 `/api/presets/save` 重複削除
```bash
# hq_api/routers/dsp_readonly.py から以下を削除
# L147-170: class PresetSave 〜 delete_preset 関数まで
```

### 5.2 エラー統一ユーティリティ
```python
# hq_api/errors.py に追加
from fastapi import HTTPException
from fastapi.responses import JSONResponse

def error_response(status_code: int, message: str, detail: Any = None) -> JSONResponse:
    content = {"status": "error", "message": message}
    if detail: content["detail"] = detail
    return JSONResponse(status_code=status_code, content=content)

def service_unavailable(message: str, detail: Any = None) -> JSONResponse:
    return error_response(503, message, detail)

def unprocessable_entity(message: str, detail: Any = None) -> JSONResponse:
    return error_response(422, message, detail)

# 使用例: raise HTTPException(503, "MPD disconnected")
# 使用例: return error_response(422, "Invalid params", detail)
```

### 5.3 `/api/volume` 非同期化スケッチ
```python
# hq_api/routers/dsp_write.py
@router.post("/api/volume")
async def set_volume(vol: VolumeControl):
    from hq_api.main import DSP_LOCK
    async with DSP_LOCK:  # threading.Lock → asyncio.Lock 変更要
        last_err = None
        for attempt in range(200):
            try:
                c = CamillaClient("127.0.0.1", 1284)
                await asyncio.to_thread(c.connect)
                await asyncio.to_thread(c.volume.set_main_volume, vol.volume)
                await asyncio.to_thread(c.disconnect)
                # ... config保存
                return {"status": "success", "attempts": attempt + 1}
            except Exception as e:
                last_err = e
                await asyncio.sleep(0.05)
        raise HTTPException(503, f"CamillaDSP unreachable: {last_err}")
```

### 5.4 `loopback-drain` 残骸削除
```bash
# backend/scripts/switch_audio.sh から削除:
# L22-35: loopback_drain_ctl 関数全体
# L165-175: 終了処理のコメントアウト呼び出し
```

---

## 6. 結論

**このシステムは「動くものを壊さず進化させる」実用主義で構築されており、本番で快適に動作している。**

| 評価 | 判定 | 備考 |
|------|------|------|
| **アーキテクチャ** | ◎ | リスク分離・共通カーネル・段階的移植が機能 |
| **API設計** | ○ | REST+WS統一、OpenAPI完備、フロントエンド連携済 |
| **並行制御** | △ | `DSP_LOCK` 適用漏れ1箇所(`/api/dsp_restart`は修正済み)、volume同期ブロッキング |
| **パフォーマンス** | △ | YAML再生成毎回、MPD idle接続増殖 |
| **保守性** | △ | 重複エンドポイント、エラー不統一、DMP sys.path、残骸コード |
| **運用** | △ | フロントエンド3系統で役割不明確 |

**今週中にやるべき3つ** (いずれも低コスト・高効果):
1. `dsp_readonly.py` から `/api/presets/save` 削除
2. `errors.py` 統一ユーティリティ作成・全ルータ適用
3. `switch_audio.sh` から `loopback_drain_ctl` 等残骸コード削除

これ以外は「動いているから触らない」か、計画的リファクタリング対象とするのが正解。

---
**修正履歴**: 2026-09-20 フロントエンドを `new-gui` (port 3003) に修正（実プロセス確認による）。