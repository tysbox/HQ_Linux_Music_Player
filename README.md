# HQ Linux Music Player

MPD と CamillaDSP を利用した、Linux向け高音質ミュージックプレイヤーです。
正式な構成は **フロントエンド 3003 / バックエンド 8002** の2プロセスです。

## 1. システム構成

```text
ブラウザ（PC・スマートフォン）
        │  HTTP / WebSocket
        ▼
new-gui（Next.js standalone）:3003
        │  REST / WebSocket（必ず8002）
        ▼
hq_api（FastAPI統合API）:8002
        ├── MPD / ライブラリ / キュー / 再生 / 履歴 / プレイリスト
        ├── DSP設定 / CamillaDSP YAML / 音量 / プリセット
        ├── UPnP / Soundgenic連携
        └── WebSocket（/ws/now_playing, /ws/status, /ws/all）
```

音声経路は次の2種類です。

- **Pure**: MPD → USB DAC
- **DSP**: MPD → ALSA Loopback → CamillaDSP → USB DAC

3003は旧3002の機能を置き換えるレスポンシブGUIです。旧3000/3001/3002および旧8000/8001のサービスは使用しません。

## 2. 動作環境

### 必須

- Linux（Debian系を推奨）
- Python 3.11以上（3.13で動作確認済み）
- Node.js 20.9以上または22 LTS
- npm
- MPD
- ALSA loopback（`snd-aloop`）
- CamillaDSP 4.x
- 出力用USB DACまたはPCサウンドカード

### 任意

- Bluetooth出力: BlueALSA
- UPnP連携: UPnP対応サーバー
- `curl`、`mpc`、`alsa-utils`、`git`、`tar`

## 3. リポジトリとディレクトリ

```bash
git clone <repository-url> /opt/hqmplayer
cd /opt/hqmplayer
```

最低限の構成は以下です。

```text
backend/              DSP共通ロジックと音声切替（8002から利用）
backend/scripts/      switch_audio.sh
backend/venv/         Python仮想環境（インストール時に作成）
dmp/backend/app/      8002から利用するDMP共通ロジック
hq_api/               統合FastAPI（8002）
hqmplayer_core/       MPD・メタデータ共通処理
new-gui/              現行GUI（3003）
config/               ALSA・systemdテンプレート
scripts/              導入・更新・監視スクリプト
```

`backend/dsp/`と`dmp/backend/app/`は8002のソース部品です。旧サービスとして起動しませんが、削除してはいけません。

## 4. インストール

以下は`$USER`が通常の実行ユーザー、`/opt/hqmplayer`がリポジトリの例です。sudo操作の実行ユーザーは実際の環境に合わせて変更してください。

### 4-1. システムパッケージ

```bash
sudo apt update
sudo apt install -y \
  mpd mpc alsa-utils alsa-tools python3 python3-venv python3-pip \
  nodejs npm git curl tar
```

Bluetoothを使う場合のみ追加します。

```bash
sudo apt install -y bluez bluealsa
```

### 4-2. ALSA Loopback

```bash
sudo modprobe snd-aloop
sudo install -m 0644 config/modules-load/snd-aloop.conf /etc/modules-load.d/snd-aloop.conf
aplay -l
```

`Loopback`が表示されることを確認してください。ALSAカード番号は環境ごとに異なるため、固定値にしないこと。

### 4-3. CamillaDSP

公式リリースの実行バイナリを取得し、`/usr/local/bin/camilladsp`へ配置します。バージョンは4.xを使用してください。

```bash
camilladsp --version
```

設定ファイルとIRファイルは、系统中で次のように配置します。

```bash
sudo mkdir -p /etc/hqmplayer /tmp/camilladsp
sudo chmod 1777 /tmp/camilladsp
# IRを使う場合は、192kHz Float32 stereoのWAVを環境側へ配置
```

### 4-4. MPD

リポジトリに汎用的な`config/mpd.conf`はありません。`/etc/mpd.conf`を作成し 次listenerAllocatorを推測せず、システムの音源と出力名に合わせて設定してください。最低限、次の3つが必要です。

```ini
music_directory "/srv/music"
bind_to_address "127.0.0.1"
port "6600"

audio_output {
    type "alsa"
    name "ALSA Loopback"
    device "hw:Loopback,0,0"
    mixer_type "software"
    format "192000:32:2"
}

audio_output {
    type "alsa"
    name "USB DAC"
    device "plughw:X,0"
    mixer_type "software"
}
```

`X`は`aplay -l`で確認したカード番号です。`mpd`ユーザーは音楽ディレクトリを読み書きできるよう権限を設定してください。

```bash
sudo systemctl enable --now mpd
mpc outputs
```

### 4-5. ALSA設定

`config/asound.conf`は例であり、`PCH`やBluetoothのデバイス名は環境固有です。必要な場合だけ編集して配置します。

```bash
sudo cp config/asound.conf /etc/asound.conf
sudo chmod 644 /etc/asound.conf
```

Bluetoothを使わない Machinesでは、BlueALSA関連の行を削除するか、既存の設定とマージしてください。

## 5. Python API (8002)

```bash
cd /opt/hqmplayer
python3 -m venv backend/venv
backend/venv/bin/pip install --upgrade pip
backend/venv/bin/pip install -r hq_api/requirements.txt
```

`hq_api/requirements.txt`は8002の実行時依存の正規リストです。Pythonからimportできることを確認した後、CamillaDSPの接続先を設定します。

```bash
sudo mkdir -p /etc/hqmplayer
sudo cp config/systemd/hqmplayer.env.example /etc/hqmplayer/hqmplayer.env
sudo nano /etc/hqmplayer/hqmplayer.env
```

最低限、移植先では次を設定します。

```dotenv
MPD_HOST=127.0.0.1
MPD_PORT=6600
CAMILLA_HOST=127.0.0.1
CAMILLA_PORT=1234
ALLOWED_ORIGINS=http://<端末のIP>:3003
HQ_GUI_ORIGINS=http://<端末のIP>:3003
```

## 6. 現行GUI (3003)のビルド

```bash
cd /opt/hqmplayer/new-gui
npm ci
npm run build
```

`next.config.ts`が`output: "standalone"`を設定しています。ビルド成果物：

```text
new-gui/.next/standalone/server.js
```

## 7. systemdUNITの導入

8002とCamillaDSPのUNITは、テンプレートから環境変数で実機パスへ変換します。まずdry-runで確認します。

```bash
cd /opt/hqmplayer
HQM_ROOT=/opt/hqmplayer HQM_USER="$USER" ./scripts/install_systemd_units.sh
```

検証用stageと実機への適用:

```bash
HQM_ROOT=/opt/hqmplayer HQM_USER="$USER" ./scripts/install_systemd_units.sh --stage=/tmp/hqm-units
sudo env HQM_ROOT=/opt/hqmplayer HQM_USER="$USER" ./scripts/install_systemd_units.sh --apply --reload
```

GUI UNITは3003用の`new-gui/audiophile-new-gui.service`を使います。移植先のパスとユーザー名に置換して配置します。

```bash
sudo sed \
  -e "s#/home/tysbox/HQ_Linux_Music_Player#/opt/hqmplayer#g" \
  -e "s/tysbox/$USER/g" \
  new-gui/audiophile-new-gui.service | sudo tee /etc/systemd/system/audiophile-new-gui.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now mpd.service camilladsp.service hq-api.service audiophile-new-gui.service
```

CamillaDSPのYAMLが存在するまでCamillaDSPは起動できません。`switch_audio.sh`または8002のDSP適用機能経由でYAMLを生成してください。起動直後に空のYAMLを検査するとCamillaDSPが異常終了するため、CamillaDSPだけを先行起動しないでください。

## 8. 起動と動作確認

```bash
sudo systemctl status hq-api.service audiophile-new-gui.service mpd.service camilladsp.service
ss -ltnp | grep -E ':(3003|8002|6600|1234)\b'
curl -fsS http://127.0.0.1:8002/health
curl -I http://127.0.0.1:3003/
```

期待される主要API:

```text
GET /health
GET /api/library/*
GET /api/playback/*
GET /api/queue/*
GET /api/history/
GET /api/playlists/
GET /api/upnp/*
GET /api/devices
GET /api/config
GET /api/presets
```

ブラウザは次 Opens.

```text
http://<端末のIP>:3003/
```

同じLAN以外から公開する場合は、リバースプロキシとHTTPSを推奨します。8002を直接公開しないでください。

## 9. 日常運用

GUIの更新:

```bash
cd /opt/hqmplayer
./scripts/deploy_gui.sh
```

サービス再起動:

```bash
sudo systemctl restart hq-api.service audiophile-new-gui.service
```

監視スクリプトの対象は`hq-api.service`と`audiophile-new-gui.service`です。

```bash
./scripts/monitor_services.sh
```

ログ:

```bash
journalctl -u hq-api.service -f
journalctl -u audiophile-new-gui.service -f
journalctl -u camilladsp.service -f
```

## 10. トラブルシューティング

### `health`がdegraded

`mpd`と`dsp`を分けて確認します。

```bash
systemctl status mpd.service camilladsp.service
ss -ltnp | grep -E ':(6600|1234)\b'
journalctl -u camilladsp.service -n 100 --no-pager
```

Bluetoothを接続していない場合の`bt_sink: false`やDSP停止は環境前提です。先にMPD・CamillaDSPのログを確認してください。

### ポート8002が使用中

```bash
ss -ltnp | grep :8002
sudo systemctl status hq-api.service
```

### ポート3003が動かない

```bash
cd /opt/hqmplayer/new-gui
npm ci && npm run build
sudo systemctl restart audiophile-new-gui.service
journalctl -u audiophile-new-gui.service -n 100 --no-pager
```

### 音声が出ない

1. `mpc outputs`でMPD出力を確認
2. `aplay -l`でDACとLoopbackを確認
3. CamillaDSPのYAMLとログを確認
4. 8002の`/api/dsp_status`を確認
5. Bluetoothを使う場合はBlueALSAと接続デバイスを確認

### APIは動くがブラウザからCORSエラーになる

```dotenv
ALLOWED_ORIGINS=http://<端末のIP>:3003
HQ_GUI_ORIGINS=http://<端末のIP>:3003
```

を設定して`hq-api.service`を再起動します。ブラウザのURLと完全一致させてください。

## 11. 旧構成の扱い

旧3000/3001/3002および旧8000/8001のソース・UNITは現行構成から削除済みです。旧3002は次の読み取り専用アーカイブから復元できます。

```text
.safety_backups/archives/3002-unified-shell-20260925-171448.tar.gz
```

復元する場合は、リポジトリへ戻さず/tmpで展開し、比較専用として使用してください。旧ポートを現行の起動手順に再統合しないでください。
