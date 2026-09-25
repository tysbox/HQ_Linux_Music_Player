# ADR-004: DSP 固有機能のプロセス境界

> **ステータス**: Proposed
> **作成日**: 2026-09-02
> **対象フェーズ**: Phase 3a
> **関連**: ADR-002

---

## コンテキスト

DSP 機能（CamillaDSP 制御・ボリューム・デバイス列挙）は **DSP backend 単独**で
実装されており、Phase 3 で 1 プロセス化する際にどこまでを統合に含めるか
判断が必要。

## DSP 固有機能の分類

| 機能 | エンドポイント | 依存ライブラリ | 統合方針 |
|---|---|---|---|
| デバイス列挙 | `GET /api/devices` | `aplay -l` (subprocess) | **hq_api に移植** |
| CamillaDSP 状態 | `GET /api/dsp_status` | `camilladsp` | **hq_api に移植** |
| CamillaDSP 再起動 | `POST /api/dsp_restart` | `camilladsp` + `switch_audio.sh` | **hq_api に移植** |
| DSP 設定 | `GET/POST /api/config`, `/api/apply` | yaml 生成 | **hq_api に移植** |
| プリセット | `GET/POST/DELETE /api/presets` | ファイル I/O | **hq_api に移植** |
| ボリューム | `POST /api/volume` | `camilladsp.CamillaClient` | **hq_api に移植** |
| Now Playing | `GET /api/now_playing`, `/ws/now_playing` | MPD | **hq_api に移植** |
| アルバムアート | `GET /api/art` | MPD + iTunes API | **hq_api に移植** |
| 再生 watchdog | (background task) | MPD | **hq_api に移植** |

**結論: 全ての DSP 機能を hq_api に移植する**（DSP backend は空になる）。

## 移植時の注意点

### 1. ALSA loopback デバイスの前提

DSP モードは `snd-aloop` モジュールが必須。`/proc/asound/Loopback/pcm1c/info` の存在を
起動時に確認するロジック (`_has_loopback_capture_device`) は維持する。

### 2. ボリューム fade-in

`STARTUP_VOLUME_DB = -80.0` から始めて段階的に上げる fade-in 処理は
バックグラウンドスレッドで動いている。`hq_api` でも `threading.Thread` で
同様に動かす（asyncio 化は不要）。

### 3. switch_audio.sh の呼び出し

`/home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh` は
DSP 専用スクリプト。`hq_api` の WorkingDirectory に注意:

```ini
# hq-api.service
WorkingDirectory=/home/tysbox/HQ_Linux_Music_Player
# switch_audio.sh は絶対パスで参照
ExecStart=... 
Environment="SWITCH_AUDIO_SCRIPT=/home/tysbox/HQ_Linux_Music_Player/backend/scripts/switch_audio.sh"
```

### 4. systemd unit 統合

Phase 5 で 1 つの `hq-api.service` に集約。`After=mpd.service` と `After=camilladsp.service` の
双方を依存に設定。

## DSP 機能の永続化パス

| パス | 内容 | 移動方針 |
|---|---|---|
| `~/.config/audiophile/last_config.json` | 最終 DSP 設定 | 維持（パス変更なし） |
| `~/.config/audiophile/presets.json` | プリセット | 維持 |
| `~/.cache/audiophile/ir/` | 192kHz 変換済み IR | 維持 |
| `/tmp/camilladsp/active_dsp.yml` | CamillaDSP YAML | 維持 |
| `/tmp/hq_api_apply.log` | エラーログ | 維持 |

**`/home/tysbox/HQ_Linux_Music_Player/backend/` ディレクトリは
Phase 4 で削除するが、`scripts/switch_audio.sh` だけは `hq_api/scripts/` に移動する**。

## リスクと対策

| リスク | 対策 |
|---|---|
| CamillaDSP と MPD の起動順序 | systemd で `After=camilladsp.service mpd.service` |
| ボリューム fade-in 中の backend 再起動 | 永続化された last_config から復元 |
| ALSA loopback モジュール未ロード | `/api/apply` で 503 を返す既存挙動を維持 |

## ロールバック手順

Phase 3a の状態（旧 DSP / 旧 DMP + hq_api 並行稼働）に戻す:

```bash
sudo systemctl stop hq-api
sudo systemctl start audiophile-backend hq-dmp-backend
```

## 想定工数

| タスク | 工数 |
|---|---|
| DSP 機能の `hq_api` への移植 | 1〜1.5 日 |
| `switch_audio.sh` のパス調整 | 0.5 日 |
| systemd unit 統合準備 | 0.5 日 |
| **合計** | **2〜2.5 日** |
