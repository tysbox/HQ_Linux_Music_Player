# 2026-09-06 DSP_LOCK + Apply時 volume強制復帰 実装手順書

## 目的

`docs/2026-09-06_8002-3002-maintenance.md` の「今後の開発課題 優先度 高」
- 課題 2: DSP更新処理の直列化
- 課題 3: 音量の安全制御(部分対応: 起動時・Apply・デバイス切替で直前の volume に戻す)

を、安全かつ最小侵襲で実装する手順。

加えて、調査中に発見した **副次バグ 1件** の修正も含む:
- 副次 A: `/health` が MPD 接続成功時に `null` を返す(成功時の `return` 文が欠落)

---

## 最重要仕様(2026-09-06 ご指示)

> Apply ボタンでエフェクト変更後、再起動や生成ファイル変更でプレイ開始時は
> Vol 位置に関係なく (-8 であろうと -20 であろうと) **直前の音量に戻る**

**解釈**:
- ユーザーが `/api/volume` で設定した volume (例: -15.0) が「真の現在音量」
- その後 `/api/apply` で `config.volume` が -8.0 (Pydantic デフォルト) でも -20.0 でも、
  **常に `last_config.volume` (= 直前の /api/volume 設定値) を採用**
- ユーザーの明示的な volume 指定は **無視** される
- 結果: ダイヤル位置と無関係に、**直前の音量**で再生開始

---

## 設計判断(なぜこの方式か)

### 1. なぜ `asyncio.Lock` ではなく `threading.Lock` か

- FastAPI の同期エンドポイント(`def apply_audio`, `def set_volume`, `def update_dsp_params`)
  は内部で `anyio` 経由の **スレッドプール** で実行される
- `asyncio.Lock` を使うには該当エンドポイントを `async def` に書き換える必要があり、
  `try/except`、`BackgroundTasks`、内部の `subprocess.Popen`、`open()` 等の I/O ブロックを
  すべて `await` 化する影響が出る
- `threading.Lock` なら `with DSP_LOCK:` を1行追加するだけで済み、既存ロジックを**完全に保全**できる
- スレッドプール上の同期コード間での競合防止には `threading.Lock` で十分

### 2. なぜ volume 強制適用か

- ユーザーが `/api/volume` を最後に実行した値が「真の現在音量」
- `/api/apply` 実行時、payload の `volume` フィールドは **常に `last_config.volume` で上書き**
- ユーザーが意図的に「Apply と同時に volume も変更」したい場合は `/api/volume` を別実行する
- これで「Apply 後に音量がリセットされる」「ダイヤル位置と実音量が一致しない」現象を根絶

### 3. 副次 A の扱い

- `b14ed064` には `return {"status":"ok","mpd":"connected"}` があった
- `53f8dcf5 Restore GUI recovered baseline` の巻き込みで消失
- 1行追加で復活可能

---

## ロールバック体制(2026-09-06 04:26 確立済み)

| ロールバック手段 | コマンド |
|---|---|
| ファイル単位 | `git restore hq_api/main.py hq_api/routers/dsp_apply.py hq_api/routers/dsp_write.py` |
| コミット単位 | `git reset --hard pre-dsp-lock-20260906` (タグ地点) |
| バックアップから | `cp /tmp/20260906_pre_*.py <元のパス>` |
| サービス再起動 | `sudo systemctl restart hq-api.service unified-shell.service` |

git tag: `pre-dsp-lock-20260906` (commit `b76599b0`)
ファイルバックアップ: `/tmp/20260906_pre_main.py`, `/tmp/20260906_pre_dsp_apply.py`, `/tmp/20260906_pre_dsp_write.py`

---

## 変更対象ファイル(3ファイル)

1. `hq_api/main.py` — `DSP_LOCK` 定義 + `/health` 成功時 return
2. `hq_api/routers/dsp_write.py` — `/api/volume` を DSP_LOCK で包む
3. `hq_api/routers/dsp_apply.py` — `/api/apply`, `/api/dsp_update` を DSP_LOCK で包む + `/api/apply` に volume 強制適用

---

## 実装手順(チェックリスト形式)

各ステップは **前のステップが成功した場合のみ** 次へ進むこと。
失敗したらその場で停止し、`git restore` で巻き戻して報告する。

### ステップ 0: ベースライン保全

```bash
cd /home/tysbox/HQ_Linux_Music_Player
git status --short
git tag --list | grep pre-dsp-lock
ls -la /tmp/20260906_pre_*.py
```

期待:
- `git status --short` が `?? docs/2026-09-06_dsp_lock_volume_plan.md` のみ
- `pre-dsp-lock-20260906` タグが存在
- バックアップ3ファイルが `/tmp/` に存在

### ステップ 1: タイムスタンプ付き追加バックアップ

```bash
TS=$(date +%s)
cp hq_api/main.py            /tmp/20260906_${TS}_main.py
cp hq_api/routers/dsp_apply.py /tmp/20260906_${TS}_dsp_apply.py
cp hq_api/routers/dsp_write.py /tmp/20260906_${TS}_dsp_write.py
ls -la /tmp/20260906_${TS}_*.py
```

### ステップ 2: 変更前構文チェック

```bash
cd /home/tysbox/HQ_Linux_Music_Player
./backend/venv/bin/python3 -m py_compile \
    hq_api/main.py \
    hq_api/routers/dsp_apply.py \
    hq_api/routers/dsp_write.py
echo "STEP 2 OK: $?"
```

期待: エラーなしで完了。

### ステップ 3: `hq_api/main.py` に `DSP_LOCK` 追加 + 副次 A `/health` 修正

**3.1**: `DSP_LOCK` 定義を追加

挿入位置: `app = FastAPI(...)` ブロック終了 `)` の **直後**(`app.add_middleware(...)` の直前)

挿入文字列(全文):
```python

# ─────────────────────────────────────────────────────────────────────────────
# DSP 直列化ロック (2026-09-06 課題 2)
# /api/apply, /api/dsp_update, /api/volume はいずれも CamillaDSP の状態・YAML・
# ALSA デバイスに影響するため、短時間に並列実行すると競合して音量リセット・
# YAML 破損・CamillaDSP 未起動などを引き起こす。
# FastAPI の同期エンドポイントは内部でスレッドプール実行されるため、
# threading.Lock で十分直列化できる (async.Lock 化は呼び出し側を async def に
# 変える必要があり、影響範囲が大きくなるため本コミットでは見送り)。
# ─────────────────────────────────────────────────────────────────────────────
import threading  # noqa: E402

DSP_LOCK = threading.Lock()
```

**3.2**: 副次 A — `/health` 成功時 return 追加

現在の `/health` ハンドラの `except` ブロックの `return` の直後に **成功時の return を追加**:

```python
    except Exception as e:
        mpd_ok = False
        return {
            "status": "degraded",
            "mpd": "disconnected",
            "error": str(e),
        }
    return {
        "status": "ok",
        "mpd": "connected",
    }
```

**3.3**: 構文チェック
```bash
./backend/venv/bin/python3 -m py_compile hq_api/main.py && echo "STEP 3 OK"
```

### ステップ 4: `dsp_write.py` `/api/volume` を DSP_LOCK で包む

`set_volume` 関数の先頭に追加:

```python
@router.post("/api/volume")
def set_volume(vol: VolumeControl):
    """DSP:8000 と完全互換のボリューム設定.

    CamillaDSP のメイン音量を即座に変更。再生は途切れない。
    CamillaDSP 未起動時は最大3回 (各200ms) リトライ。

    2026-09-06 課題 2: DSP_LOCK で /api/apply /api/dsp_update と同時実行を直列化。
    """
    from hq_api.main import DSP_LOCK
    with DSP_LOCK:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                ...
```

既存ロジックを1段インデント深くする。`for` ループ本体・`return`・`raise` を変更せず、インデントだけを1段深くする。

構文チェック:
```bash
./backend/venv/bin/python3 -m py_compile hq_api/routers/dsp_write.py && echo "STEP 4 OK"
```

### ステップ 5: `dsp_apply.py` `/api/apply` を DSP_LOCK で包む + volume 強制適用

`apply_audio` 関数を変更:

```python
@router.post("/api/apply")
def apply_audio(config: AudioConfig, bt: BackgroundTasks):
    """DSP:8000 と完全互換の DSP 設定適用.

    副作用:
    - 必要に応じて CamillaDSP / ALSA Loopback を再起動
    - ~/.config/audiophile/last_config.json を更新
    - ボリューム fade-in

    2026-09-06 課題 2: DSP_LOCK で /api/dsp_update /api/volume と同時実行を直列化。
    2026-09-06 課題 3: volume 強制復帰。
    ユーザーが /api/volume で設定した値 (last_config.volume) を真の現在音量とし、
    config.volume の値に関わらず必ず last_config.volume で上書きする。
    効果: 起動時 / Apply / デバイス切替 / DSP 再生成 / ALSA 切替のいずれでも
    直前の音量で再生開始される (ダイヤル位置と無関係)。
    """
    from hq_api.main import DSP_LOCK
    if not _HAS_BACKEND:
        raise HTTPException(
            status_code=503,
            detail=f"backend.main を import できません: {_IMPORT_ERROR}",
        )
    with DSP_LOCK:
        # 2026-09-06 課題 3: volume 強制復帰
        # ユーザー指示: "Apply ボタンでエフェクト変更後、再起動や生成ファイル変更で
        # プレイ開始時は Vol 位置に関係なく (-8 であろうと -20 であろうと) 直前の音量に戻る"
        # → config.volume の値に関わらず、last_config.volume を必ず採用する。
        try:
            last_cfg = _dsp_main._load_last_config() if os.path.exists(_dsp_main.LAST_CONFIG_PATH) else None
        except Exception:
            last_cfg = None
        if last_cfg and "volume" in last_cfg:
            try:
                last_vol = float(last_cfg["volume"])
                config = config.model_copy(update={"volume": last_vol})
            except Exception:
                pass
        try:
            requested_mode = config.mode
            ...
```

以降の `try` ブロック本体をすべて1段インデント深くする。
**注意**: 既存の `if not _HAS_BACKEND` チェックは **`with DSP_LOCK:` の外** に置く。
こうすることで、backend がない場合の早期 return はロック取得コストなしで実行できる。

構文チェック:
```bash
./backend/venv/bin/python3 -m py_compile hq_api/routers/dsp_apply.py && echo "STEP 5 OK"
```

### ステップ 6: `dsp_apply.py` `/api/dsp_update` を DSP_LOCK で包む

`update_dsp_params` 関数を変更:

```python
@router.post("/api/dsp_update")
def update_dsp_params(params: DspParams):
    """DSP パラメータのみ更新 — CamillaDSP ホットリロード (停止/ポーズなし).

    ユーザー要件: ダイヤル変更 = ユーザーが意図した変更。
    ALSA Loopback / MPD output は変更せず、CamillaDSP の YAML のみ更新して
    ホットリロードする。音は途切れない。

    2026-09-06 課題 2: DSP_LOCK で /api/apply /api/volume と同時実行を直列化。
    """
    from hq_api.main import DSP_LOCK
    with DSP_LOCK:
        if not _HAS_BACKEND:
            raise HTTPException(
                status_code=503,
                detail=f"backend.main を import できません: {_IMPORT_ERROR}",
            )
        try:
            # 既存 last_config に dial 値のみマージ
            ...
```

`/api/apply` と同じく `if not _HAS_BACKEND` を `with DSP_LOCK:` の外側に置く。
既存ロジックを完全に保全してインデント調整。

構文チェック:
```bash
./backend/venv/bin/python3 -m py_compile hq_api/routers/dsp_apply.py && echo "STEP 6 OK"
```

### ステップ 7: 全構文チェック

```bash
cd /home/tysbox/HQ_Linux_Music_Player
./backend/venv/bin/python3 -m py_compile \
    hq_api/main.py \
    hq_api/routers/dsp_apply.py \
    hq_api/routers/dsp_write.py \
    hq_api/routers/dsp.py \
    hq_api/routers/dsp_readonly.py \
    hq_api/routers/dmp.py \
    hq_api/middleware.py \
    hq_api/errors.py \
    hq_api/metrics.py && echo "STEP 7 OK"
```

### ステップ 8: サービス再起動と /health 検証

```bash
sudo systemctl restart hq-api.service
sleep 3
systemctl is-active hq-api.service
curl -s http://localhost:8002/health
```

期待: `{"status":"ok","mpd":"connected"}` (副次 A 修正の確認)

### ステップ 9: 実機エンドポイント確認

```bash
# 現在の last_config.volume 確認
curl -s http://localhost:8002/api/config | head -c 200

# volume 設定 (-15.0 にする)
curl -s -X POST http://localhost:8002/api/volume \
    -H "Content-Type: application/json" \
    -d '{"volume": -15.0}'

# 直後 last_config.volume 確認 (-15.0 になっているはず)
curl -s http://localhost:8002/api/config | grep -o '"volume":[^,]*'

# 既存 3002 への影響確認
curl -s -o /dev/null -w "3002: %{http_code}\n" http://localhost:3002/
```

### ステップ 10: diff 確認とコミット

```bash
cd /home/tysbox/HQ_Linux_Music_Player
git diff --stat
git diff hq_api/main.py hq_api/routers/dsp_apply.py hq_api/routers/dsp_write.py
```

期待差分:
- `hq_api/main.py`: `DSP_LOCK` 追加 + `/health` 成功時 return 追加
- `hq_api/routers/dsp_apply.py`: 2エンドポイント + volume 強制適用
- `hq_api/routers/dsp_write.py`: 1エンドポイント

コミット & プッシュ:
```bash
git add hq_api/main.py hq_api/routers/dsp_apply.py hq_api/routers/dsp_write.py
git commit -m "GUI&IR Comp: DSP_LOCK serialization + apply volume override

- hq_api/main.py: add DSP_LOCK (threading.Lock) for serializing
  /api/apply, /api/dsp_update, /api/volume (priority-high task 2)
- hq_api/main.py: restore /health success return
  (b14ed064 regression; was returning null on MPD connect)
- dsp_apply.py: wrap /api/apply and /api/dsp_update in with DSP_LOCK
- dsp_apply.py: apply volume override (priority-high task 3)
  /api/apply now always uses last_config.volume regardless of
  config.volume, per user requirement: after Apply / restart /
  device-switch / DSP-regenerate, playback must start at the
  previous volume (-8 or -20 makes no difference).
- dsp_write.py: wrap /api/volume in with DSP_LOCK

threading.Lock chosen over asyncio.Lock to avoid converting
existing sync endpoints to async (BackgroundTasks, subprocess,
file I/O would all need await)."

git push origin clean-main
```

---

## 即時ロールバック手順(問題発生時)

```bash
cd /home/tysbox/HQ_Linux_Music_Player
# 方法 1: ファイル単位
git restore hq_api/main.py hq_api/routers/dsp_apply.py hq_api/routers/dsp_write.py

# 方法 2: コミット単位 (未プッシュ時)
git reset --hard pre-dsp-lock-20260906

# 方法 3: バックアップから
cp /tmp/20260906_<TS>_main.py      hq_api/main.py
cp /tmp/20260906_<TS>_dsp_apply.py hq_api/routers/dsp_apply.py
cp /tmp/20260906_<TS>_dsp_write.py hq_api/routers/dsp_write.py

# サービス再起動で反映
sudo systemctl restart hq-api.service
```

---

## 検証チェックリスト(戻られたら実行)

- [ ] ステップ 0: `git status --short` が `?? docs/...` のみ、タグとバックアップ存在
- [ ] ステップ 1: タイムスタンプ付きバックアップ3ファイル作成
- [ ] ステップ 2: 構文チェック OK
- [ ] ステップ 3: 構文チェック OK、`/health` のコードに `return {"status":"ok"...` が追加された
- [ ] ステップ 4: 構文チェック OK、`/api/volume` 内に `from hq_api.main import DSP_LOCK` と `with DSP_LOCK:` が存在
- [ ] ステップ 5: 構文チェック OK、`/api/apply` 内に `with DSP_LOCK:` と volume 強制適用コード (`if last_cfg and "volume" in last_cfg:`) が存在
- [ ] ステップ 6: 構文チェック OK、`/api/dsp_update` 内に `with DSP_LOCK:` が存在
- [ ] ステップ 7: 全ファイル構文 OK
- [ ] ステップ 8: `/health` が `{"status":"ok","mpd":"connected"}` を返す
- [ ] ステップ 9: `/api/volume` 200、`/api/config` 200、3002 HTTP 200、`/api/volume -15.0` → `/api/config` の `volume` が `-15.0`
- [ ] ステップ 10: コミット成功、push 成功

すべて OK なら、本日の締め完了。
問題があれば **ステップ 0 のベースライン**に戻すだけで安全に復旧可能。
