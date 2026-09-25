# HANDOVER — 現行構成（8002 + 3003）

## 現在の構成

| サービス | ポート | 役割 | 状態 |
|---|---:|---|---|
| `hq-api.service` | 8002 | 統合API（DSP + DMP） | active / enabled |
| `audiophile-new-gui.service` | 3003 | レスポンシブWeb GUI | active / enabled |

旧3000/3001/3002および旧8000/8001のサービスは現行構成から削除済みです。
旧3002のソースは次の読み取り専用アーカイブに保存されています。

```text
.safety_backups/archives/3002-unified-shell-20260925-171448.tar.gz
```

## 構成と依存関係

```text
new-gui:3003 -> hq_api:8002
hq_api -> backend/dsp
hq_api -> dmp/backend/app
hq_api -> hqmplayer_core
```

`backend/dsp`と`dmp/backend/app`は旧サービス用ではなく、8002がimportする共通実装です。
API version は `hq_api.__version__` を正とし、FastAPI metadata、root response、`/ws/all` の ready message で同一値を返します。WebSocket 状態は `/ws/now_playing` のイベント駆動 payload（曲情報、位置、queue、random、repeat）を主経路とし、GUI から2秒ごとの status polling は行いません。

`ALLOWED_ORIGINS` は既定 origin の置換、`HQ_GUI_ORIGINS` は追加の GUI origin です。重複は除去されます。

## 主なAPI

- DSP: `/api/devices`, `/api/config`, `/api/apply`, `/api/dsp_update`, `/api/volume`, `/api/presets*`
- DMP: `/api/library/*`, `/api/playback/*`, `/api/queue/*`, `/api/playlists/*`, `/api/history/*`, `/api/upnp/*`
- 共通: `/health`, `/`, `/ws/now_playing`, `/ws/status`, `/ws/all`

## 日常の起動・更新

```bash
sudo systemctl restart hq-api.service audiophile-new-gui.service
cd /opt/hqmplayer && ./scripts/deploy_gui.sh
journalctl -u hq-api.service -f
journalctl -u audiophile-new-gui.service -f
```

## 移植

新規デバイスへのインストールは`README.md`を参照してください。UNITはユーザー名とリポジトリパスを置換し、`/etc/hqmplayer/hqmplayer.env`でMPD、CamillaDSP、UPnP、CORSを設定します。

## 既知の別課題

`/health`の`dsp: disconnected`や`bt_sink: false`はCamillaDSP/Bluetoothの状態を表します。3003と8002の接続互換性とは別の音声DSP運用課題です。
