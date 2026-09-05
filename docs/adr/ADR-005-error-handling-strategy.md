# ADR-005: エラーハンドリング戦略

> **ステータス**: Proposed
> **作成日**: 2026-09-02
> **対象フェーズ**: Phase 3a
> **関連**: ADR-002, ADR-004

---

## コンテキスト

旧 DSP / DMP backend はそれぞれ **独自のエラーレスポンス形式** を持っている。
Phase 3 統合時にこれらを統一する必要がある。

## 現状のエラーパターン

### DSP backend

```python
# 503: MPD 切断時
@app.get("/api/now_playing")
async def get_now_playing():
    try:
        st = await mpd_status()
        so = await mpd_currentsong()
        return format_now_playing(st, so)
    except Exception:
        return JSONResponse(status_code=503, content={"error": "MPD offline"})

# 422: 設定エラー
@app.post("/api/apply")
def apply_audio(config: AudioConfig, bt: BackgroundTasks):
    ...
    return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})

# 422: ALSA loopback 不在
def _ensure_dsp_prerequisites(config: "AudioConfig"):
    if config.mode == "dsp":
        if not _has_loopback_capture_device():
            raise HTTPException(
                status_code=503,
                detail="ALSA Loopback device is unavailable. ..."
            )
```

### DMP backend

```python
# 404: リソース不在
@router.get("/artists/{artist}/albums")
async def get_albums(artist: str):
    async with mpd_connection() as client:
        albums = await client.list("album", "artist", artist)
    if not albums:
        raise HTTPException(status_code=404, detail="Artist not found")
    ...

# 500: 内部エラー（暗黙的 FastAPI ハンドラ）
```

## 決定

**統一形式**: 全てのエラーを以下の形式に統一:

```json
{
  "error": {
    "code": "MPD_OFFLINE",
    "message": "MPD サーバーに接続できません",
    "details": { ... }   // オプション
  }
}
```

### HTTP ステータスコード方針

| 状況 | ステータス | `code` |
|---|---|---|
| MPD 切断 | 503 | `MPD_OFFLINE` |
| CamillaDSP 切断 | 503 | `DSP_OFFLINE` |
| ALSA loopback 不在 | 503 | `DSP_PREREQUISITE_MISSING` |
| リソース不在（アルバム等） | 404 | `RESOURCE_NOT_FOUND` |
| バリデーションエラー | 422 | `VALIDATION_ERROR` |
| 内部エラー | 500 | `INTERNAL_ERROR` |
| UPnP サーバ未検出 | 503 | `UPNP_SERVER_UNAVAILABLE` |

## 実装方針

`hq_api/errors.py` を新設し、統一エラーハンドラを実装:

```python
# hq_api/errors.py
from fastapi import HTTPException
from fastapi.responses import JSONResponse

class HQError(HTTPException):
    def __init__(self, code: str, message: str, status_code: int = 500, details: dict = None):
        super().__init__(status_code=status_code, detail={
            "code": code,
            "message": message,
            "details": details or {},
        })

# MPD 切断
async def safe_mpd_call(coro):
    try:
        return await coro
    except ConnectionError as e:
        raise HQError("MPD_OFFLINE", str(e), status_code=503)
    except Exception as e:
        raise HQError("INTERNAL_ERROR", str(e), status_code=500)
```

各ルータで `safe_mpd_call` を使う:

```python
@app.get("/api/now_playing")
async def get_now_playing():
    st = await safe_mpd_call(mpd_status())
    so = await safe_mpd_call(mpd_currentsong())
    return format_now_playing(st, so)
```

## 後方互換性

旧 DSP / 旧 DMP のエンドポイントは **当面維持** されるため、エラー形式の
統一は **Phase 4**（旧 backend 退役）以降とする。

Phase 3a〜3c では:
- 新 `hq_api` のエンドポイントは新形式で返す
- 旧 DSP / 旧 DMP のエンドポイントは旧形式のまま（**API レスポンスをコピーで複製**）

## 影響範囲

| ファイル | 変更 |
|---|---|
| `hq_api/errors.py` | 新規 |
| `hq_api/main.py` | グローバルエラーハンドラ登録 |
| 各ルータ | `try/except` を `safe_mpd_call` に置換 |

## ロールバック手順

新エラー形式は **レスポンス body の `error` キーが増えるだけ**。
旧形式を期待するクライアントは `data.error` を見るか、
`status_code` を見るかで判定しているため、HTTP ステータスは変えない方針。

問題があれば `error` キー追加を旧形式に合わせるだけでロールバック可能。

## 想定工数

| タスク | 工数 |
|---|---|
| `errors.py` 実装 | 0.5 日 |
| 各ルータへの適用 | 1 日 |
| 検証 | 0.5 日 |
| **合計** | **2 日** |
