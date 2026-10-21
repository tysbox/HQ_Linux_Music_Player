# HQ Linux Music Player

MPD と CamillaDSP を利用した、Linux向け高音質ミュージックプレイヤーです。
正式な構成は **フロントエンド 3002 / バックエンド 8003** の2プロセスです。

## 1. システム構成

```text
ブラウザ（PC・スマートフォン）
        │  HTTP / WebSocket
        ▼
new-gui（Next.js standalone）:3002
        │  REST / WebSocket（必ず8003）
        ▼
hq_api（FastAPI統合API）:8003
        ├── MPD / ライブラリ / キュー / 再生 / 履歴 / プレイリスト
        ├── DSP設定 / CamillaDSP YAML / 音量 / プリセット
        ├── UPnP / Soundgenic連携
        └── WebSocket（/ws/now_playing, /ws/status, /ws/all）
```

音声経路は次の2種類です。

- **Pure**: MPD → USB DAC
- **DSP**: MPD → ALSA Loopback → CamillaDSP → USB DAC

DSP経路では、CamillaDSPの後段に **bisen-dspd**（Bisen C++ DSP デーモン）を
挿入できます。Tube / Restore / TruePeakLimiter を担当します。

- **DSP + Bisen**: MPD → ALSA Loopback → CamillaDSP → Loopback → bisen-dspd → USB DAC

bisen-dspd は既定で `routing=0`（standby）のため、ALSAデバイスを一切開かず
既存の CamillaDSP 直結構成に影響しません。Tube / Restore を使うときだけ
8003 が経路を切り替えます。詳細は `dmp/bisen-dspd/README.md` を参照してください。

3002は旧3002の機能を置き換えるレスポンシブGUIです。旧3000/3001/3003および旧8000/8001/8002のサービスは使用しません。

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
- C++ビルド環境: `cmake` 3.16以上、`g++`（C++17対応）— bisen-dspd のビルドに必要
- `ffmpeg`（`ffprobe`）— 8003の「ファイル真理」が原本を解析するために使用

### 任意

- Bluetooth出力: BlueALSA
- UPnP連携: UPnP対応サーバー（`upmpdcli` をMPDのUPnPレンダラーとして使用）
- `curl`、`mpc`、`alsa-utils`、`git`、`tar`
- `socat` — bisen-dspdの制御ソケットを手動確認する場合（§9）

## 3. リポジトリとディレクトリ

```bash
git clone <repository-url> /opt/hqmplayer
cd /opt/hqmplayer
```

最低限の構成は以下です。

```text
backend/              DSP共通ロジックと音声切替（8003から利用）
backend/scripts/      switch_audio.sh
backend/venv/         Python仮想環境（インストール時に作成）
dmp/backend/app/      8003から利用するDMP共通ロジック
dmp/bisen-dspd/       Bisen C++ DSP デーモン（Tube / Restore / TruePeakLimiter）
dmp/bisen-dspd/build/ ビルド成果物（.gitignore対象・§7で生成）
hq_api/               統合FastAPI（8003）
hqmplayer_core/       MPD・メタデータ共通処理
new-gui/              現行GUI（3002）
config/               ALSA・systemdテンプレート
config/sudoers/       switch_audio.sh 用 sudoers 雛形
scripts/              導入・更新・監視スクリプト
docs/                 点検記録・設計資料
  V3.0_INSPECTION_AND_FIX_REPORT.md  点検・修正の記録と未完了項目
  BISEN_FEATURE_PORT_PLAN.md         Bisen移植の計画書
```

`backend/dsp/`と`dmp/backend/app/`は8003のソース部品です。旧サービスとして起動しませんが、削除してはいけません。

`dmp/bisen-dspd/`は独立したC++デーモンで、systemdの`bisen-dspd.service`として常駐します
（§7・§8を参照）。

## 4. インストール

以下は`$USER`が通常の実行ユーザー、`/opt/hqmplayer`がリポジトリの例です。sudo操作の実行ユーザーは実際の環境に合わせて変更してください。

### 4-1. システムパッケージ

```bash
sudo apt update
sudo apt install -y \
  mpd mpc alsa-utils alsa-tools python3 python3-venv python3-pip \
  nodejs npm git curl tar ffmpeg \
  cmake g++ build-essential libasound2-dev
```

`cmake` / `g++` / `libasound2-dev` は bisen-dspd のビルドに必要です。
`ffmpeg` は 8003 の「ファイル真理」（`ffprobe` による原本解析）に必要です。
未導入でも 8003 は起動しますが、ファイル真理は `available=false` を返します。

Bluetoothを使う場合のみ追加します。

```bash
sudo apt install -y bluez bluealsa
```

UPnPレンダラー（MPDをUPnPから操作する場合）を使う場合は追加します。

```bash
sudo apt install -y upmpdcli
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
port "6601"

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

**MPD は常に ALSA Loopback へ出力します。** USB DAC / PC Speaker / Bluetooth
への切替は CamillaDSP の YAML (`devices.playback.device`) が担うため、
MPD 側の `audio_output` は「ALSA Loopback」だけを有効にしてください
（MPD の出力デバイスを切り替えると DSP 経路が成立しません）。

`port "6601"` は `config/systemd/mpd.socket.d/override.conf` の
`ListenStream=127.0.0.1:6601` と揃える必要があります。パッケージ既定
(6600) のままだと接続が不安定になります。

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

## 5. Python API (8003)

```bash
cd /opt/hqmplayer
python3 -m venv backend/venv
backend/venv/bin/pip install --upgrade pip
backend/venv/bin/pip install -r hq_api/requirements.txt
```

`hq_api/requirements.txt`は8003の実行時依存の正規リストです。`pycamilladsp`は
GitHubから取得するため、`git`が必要です。Pythonからimportできることを確認した後、
CamillaDSPの接続先を設定します。

```bash
sudo mkdir -p /etc/hqmplayer
sudo cp config/systemd/hqmplayer.env.example /etc/hqmplayer/hqmplayer.env
sudo nano /etc/hqmplayer/hqmplayer.env
```

API version は `hq_api.__version__` を正とし、FastAPI metadata、`/`、`/ws/all` の ready message で同一値を返します。

`ALLOWED_ORIGINS` は既定の許可 origin を置換し、`HQ_GUI_ORIGINS` は追加の GUI origin として加算します。重複は除去されるため、LAN 端末の GUI を追加する場合は `HQ_GUI_ORIGINS` を使用してください。

```dotenv
MPD_HOST=127.0.0.1
MPD_PORT=6601
CAMILLA_HOST=127.0.0.1
CAMILLA_PORT=1234
ALLOWED_ORIGINS=http://<端末のIP>:3002
HQ_GUI_ORIGINS=http://<別ホストのIP>:3002
```

## 6. 現行GUI (3002)のビルド

```bash
cd /opt/hqmplayer/new-gui
npm ci
npm run build
```

`next.config.ts`が`output: "standalone"`を設定しています。ビルド成果物：

```text
new-gui/.next/standalone/server.js
```

## 7. bisen-dspd (Bisen C++ DSP) のビルド

Tube / Restore / TruePeakLimiter を使う場合のみ必要です。ビルド成果物は
`.gitignore` 対象のため、clone 直後は存在しません。

```bash
cd /opt/hqmplayer/dmp/bisen-dspd
cmake -B build && cmake --build build -j4
./build/test_dsp_chain   # オフラインDSP検証 (ALSA不要)
ctest --test-dir build --output-on-failure
```

`test_dsp_chain`が`ALL TESTS PASSED`を出力すれば、係数パリティ（96kHz=Bisen原値 /
192kHz=§3-B変換値）・高調波生成・Restore 3モード・リミッタ・バイパス等価性は
正常です。ビルドに失敗する場合は`libasound2-dev`の導入を確認してください。

## 8. systemdUNITの導入

8003・CamillaDSP・bisen-dspdのUNITは、テンプレートから環境変数で実機パスへ変換します。まずdry-runで確認します。

```bash
cd /opt/hqmplayer
HQM_ROOT=/opt/hqmplayer HQM_USER="$USER" ./scripts/install_systemd_units.sh
```

検証用stageと実機への適用:

```bash
HQM_ROOT=/opt/hqmplayer HQM_USER="$USER" ./scripts/install_systemd_units.sh --stage=/tmp/hqm-units
sudo env HQM_ROOT=/opt/hqmplayer HQM_USER="$USER" ./scripts/install_systemd_units.sh --apply --reload
```

`--apply`は`camilladsp.service`・`hq-api.service`・`bisen-dspd.service`の3つを配置します。
`bisen-dspd.service`の`ExecStart`は`dmp/bisen-dspd/build/bisen-dspd`を指すため、
**先に §7 のビルドを完了してください**（未ビルドだと起動に失敗します）。

GUI UNITは3002用の`new-gui/audiophile-new-gui.service`を使います。移植先のパスとユーザー名に置換して配置します。

```bash
sudo sed \
  -e "s#/home/tysbox/HQ_Linux_Music_Player#/opt/hqmplayer#g" \
  -e "s/tysbox/$USER/g" \
  new-gui/audiophile-new-gui.service | sudo tee /etc/systemd/system/audiophile-new-gui.service >/dev/null
```

**注意**: このUNITの`ExecStart`と`PATH`はNode.jsの絶対パス
（`/home/tysbox/.local/nodejs/node/bin/node`）を前提にしています。§4-1の
`apt install nodejs`で導入した場合はパスが異なるため、`command -v node`で
確認した実際のパスへ置換してください。置換しないとGUIが起動しません。

```bash
# 例: apt 導入の node を使う場合
sudo sed -i "s#/home/tysbox/.local/nodejs/node/bin/node#$(command -v node)#g" \
  /etc/systemd/system/audiophile-new-gui.service
```

Bluetoothを使う場合はBlueALSAのoverrideを配置します（内容は§13-3）。

```bash
sudo mkdir -p /etc/systemd/system/bluealsa.service.d
sudo cp config/systemd/bluealsa-override.conf /etc/systemd/system/bluealsa.service.d/override.conf
```

MPD の待受ポートを 6601 に固定します（`/etc/mpd.conf` の `port` と揃える）。

```bash
sudo mkdir -p /etc/systemd/system/mpd.socket.d
sudo cp config/systemd/mpd.socket.d/override.conf /etc/systemd/system/mpd.socket.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart mpd.socket
```

`switch_audio.sh`が`loopback-drain.service`をsudoで操作するため、sudoersを配置します。
`tysbox`の部分は実際の実行ユーザー名に置換してください。

```bash
sudo sed "s/^tysbox/$USER/" config/sudoers/hq-loopback-drain \
  | sudo tee /etc/sudoers.d/hq-loopback-drain >/dev/null
sudo chmod 0440 /etc/sudoers.d/hq-loopback-drain
sudo visudo -c
```

起動します。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mpd.service camilladsp.service hq-api.service audiophile-new-gui.service
sudo systemctl enable --now bisen-dspd.service   # standby 起動 (routing=0 のため無影響)
```

Bluetooth / UPnPを使う場合は追加で有効化します。

```bash
sudo systemctl enable --now bluealsa.service
sudo systemctl enable --now upmpdcli.service
```

CamillaDSPのYAMLが存在するまでCamillaDSPは起動できません。`switch_audio.sh`または8003のDSP適用機能経由でYAMLを生成してください。起動直後に空のYAMLを検査するとCamillaDSPが異常終了するため、CamillaDSPだけを先行起動しないでください。

## 9. 起動と動作確認

```bash
sudo systemctl status hq-api.service audiophile-new-gui.service mpd.service camilladsp.service bisen-dspd.service
ss -ltnp | grep -E ':(3002|8003|6601|1234)\b'
curl -fsS http://127.0.0.1:8003/health
curl -I http://127.0.0.1:3002/
```

bisen-dspdはTCPポートを使わず、Unixドメインソケット`/run/bisen-dspd/control.sock`で
制御します。稼働確認は次のとおりです。

```bash
systemctl is-active bisen-dspd.service
ls -l /run/bisen-dspd/control.sock
echo 'ping' | socat - UNIX-CONNECT:/run/bisen-dspd/control.sock
curl -fsS http://127.0.0.1:8003/api/bisen/status
```

Debianの`netcat-traditional`は`nc -U`に対応していません。`socat`を使うか、
`netcat-openbsd`を導入してください。

`/api/bisen/status`の`alive`が`true`なら、デーモンは正常に応答しています。
`routing`が`false`（standby）は既定の正常状態です。

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
http://<端末のIP>:3002/
```

同じLAN以外から公開する場合は、リバースプロキシとHTTPSを推奨します。8003を直接公開しないでください。

## 10. 日常運用

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
journalctl -u bisen-dspd.service -f
```

bisen-dspdを再ビルドした場合は、配置済みバイナリを更新してから再起動します。

```bash
cd /opt/hqmplayer/dmp/bisen-dspd
cmake --build build -j4
sudo systemctl restart bisen-dspd.service
```

## 11. トラブルシューティング

### `health`がdegraded

`mpd`と`dsp`を分けて確認します。

```bash
systemctl status mpd.service camilladsp.service
ss -ltnp | grep -E ':(6601|1234)\b'
journalctl -u camilladsp.service -n 100 --no-pager
```

Bluetoothを接続していない場合の`bt_sink: false`やDSP停止は環境前提です。先にMPD・CamillaDSPのログを確認してください。

### bisen-dspdが起動しない

`ExecStart`のバイナリが未ビルドの可能性があります。

```bash
ls -l /opt/hqmplayer/dmp/bisen-dspd/build/bisen-dspd
journalctl -u bisen-dspd.service -n 100 --no-pager
```

存在しない場合は§7のビルドを実行してください。`Type=notify`のため、
起動時に`sd_notify`が届かないと`WatchdogSec=15`で再起動を繰り返します。

### Tube / Restoreが効かない

bisen-dspdが停止していると、8003は警告を返してCamillaDSP直結へフォールバックします
（音は出ますがTube / Restoreは適用されません）。

```bash
curl -fsS http://127.0.0.1:8003/api/bisen/status
journalctl -u hq-api.service -n 100 --no-pager | grep -i bisen
```

`alive`が`false`の場合は`bisen-dspd.service`を起動してください。`routing`を
`true`にしたのに`playback_open`が`false`のままの場合は、DACを他プロセスが
占有していないか確認します。

```bash
fuser -v /dev/snd/* 2>&1 | head
```

### ポート8003が使用中

```bash
ss -ltnp | grep :8003
sudo systemctl status hq-api.service
```

### ポート3002が動かない

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
4. 8003の`/api/dsp_status`を確認
5. Bluetoothを使う場合はBlueALSAと接続デバイスを確認

### APIは動くがブラウザからCORSエラーになる

```dotenv
ALLOWED_ORIGINS=http://<端末のIP>:3002
HQ_GUI_ORIGINS=http://<端末のIP>:3002
```

を設定して`hq-api.service`を再起動します。ブラウザのURLと完全一致させてください。

## 12. 旧構成の扱い

旧3000/3001/3003および旧8000/8001/8002のソース・UNITは現行構成から削除済みです。旧3002は次の読み取り専用アーカイブから復元できます。

```text
.safety_backups/archives/3002-unified-shell-20260925-171448.tar.gz
```

復元する場合は、リポジトリへ戻さず/tmpで展開し、比較専用として使用してください。旧ポートを現行の起動手順に再統合しないでください。

## 13. オーディオ経路の推奨設定（2026-10-02 点検で確定）

再生品質と安定性に直結する設定です。**CamillaDSP と BlueALSA は
リアルタイム優先度で動作させる必要があります。**

### 12-1. なぜ RT 優先が必要か

CamillaDSP は `playback` デバイスを開けられないと `exit 0` で停止します。
`Restart=on-failure` は正常終了に反応しないため、**一度落ちると復帰しません**。
また Bluetooth 出力時、IO スレッドがリアルタイム優先でないと WiFi との
2.4GHz 干渉で A2DP パケットが遅延した場合に buffer underrun（雑音・音飛び）が
発生します。

### 12-2. CamillaDSP ユニット

`/etc/systemd/system/camilladsp.service` に以下が含まれることを確認してください。

```ini
Restart=always
RestartSec=3
CPUSchedulingPolicy=fifo
CPUSchedulingPriority=50
LimitRTPRIO=95
LimitMEMLOCK=infinity
Nice=-5
```

`LimitRTPRIO` が無いと `CAP_SYS_NICE` を渡しても `sched_setscheduler` が
EPERM になり RT 化が静かに失敗します。CamillaDSP は内部スレッド
（AlsaPlayback / AlsaCapture）を自前で生成するため、systemd の
`CPUSchedulingPolicy` は全スレッドに適用されます。

### 12-2-1. CamillaDSP の chunksize は全出力 16384

生成される YAML (`/var/lib/camilladsp/active_dsp.yml`) の
`devices.chunksize` は **全出力（USB DAC / PCH / Bluetooth）で 16384** にします。

CamillaDSP 4.0.0 の `enable_rate_adjust` は USB 出力側で効かず、
`chunksize: 4096` のままだとバッファ枯渇が数秒〜数十秒間隔で発生して
再生が途切れます（`PB: Prepare playback after buffer underrun`）。
16384（約85ms @192kHz）へ変更すると underrun が消えます。

実測（2026-10-21、SMSL USB DAC / hw:3,0）:

| chunksize | 90秒間の underrun |
|-----------|------------------|
| 4096      | 多数発生            |
| 16384     | **0 件**           |

再生フォーマットは **32bit（S32_LE）固定**です。DAC 側 negotiate 結果と
不一致すると `write underrun / Broken pipe` が発生するため、
S16_LE へのダウングレードは行いません。

### 12-2-2. Ambience（reverb）の Wet 比率

Wet（残響）信号の絶対レベルは `backend/dsp/yaml_generator.py` の
`rev_out` フィルタで決まります。3 つの項が加算されます。

```python
wet_gain_db = -24.0 + (reverb_intensity / 100.0) * 18.0   # intensity カーブ
wet_gain_db += REVERB_WET_TRIM_DB[reverb]                  # プリセット別 IR RMS 補正
wet_gain_db += REVERB_WET_ATTENUATION_DB                   # 全体減衰 (既定 -6.0)
```

- `REVERB_WET_TRIM_DB` は IR ごとの RMS 差を吸収します。各 IR は
  peak -6.02 dBFS に正規化済みですが RMS が異なるため
  （hall -39.7 / jazz_club -40.2 / large_bottle_hall -39.7 /
  st_nicolaes_church -36.5 dBFS）、この補正でプリセット間の Wet 比率を揃えます。
  **この値を削除するとプリセット間で Wet 比率が ±7pt ばらつきます。**
- `REVERB_WET_ATTENUATION_DB` は Wet 全体を一様に減衰します。既定 `-6.0` dB は
  Wet 振幅比 1/2（Wet 比率の半減）に相当します。`0.0` にすると原本そのままです。

**CamillaDSP の Mixer ソース gain は dB 単位**です（実測: gain `6.0` で
出力 RMS が正確に 2 倍）。線形値を mixer の `gain` に入れても比率制御には
なりません。Wet 比率の制御は必ず `rev_out`（Filter Gain）側で行い、
`mix` mixer の WET ソースは unity (`0.0` dB) のままにしてください。

実測（2026-10-22、192kHz / S32_LE、SignalGenerator 入力、
Wet 振幅シェア = Wet振幅 / (Wet振幅 + Dry振幅)）:

| プリセット | 原本 (減衰なし) | 減衰 -6dB | 原本比 |
|-----------|-----------------|-----------|--------|
| hall                   | 28.2% | 20.2% | 72% |
| jazz_club              | 23.3% | 17.5% | 75% |
| large_bottle_hall      | 33.2% | 26.4% | 79% |
| st_nicolaes_church     | 32.0% | 20.7% | 65% |

Wet 振幅そのものは -6.0 dB（1/2）ですが、DRY と合成した**比率**は
Wet 側の寄与が小さくなるほど変化の割合が緩やかになるため、
最終 Wet 比率の原本比は 65〜79% になります。

### 12-3. BlueALSA ユニット

`/etc/systemd/system/bluealsa.service.d/override.conf`:

```ini
[Service]
AmbientCapabilities=CAP_SYS_NICE
CapabilityBoundingSet=CAP_SYS_NICE
RestrictRealtime=false
LimitRTPRIO=99
LimitMEMLOCK=infinity
ExecStart=
ExecStart=/usr/bin/bluealsa -p a2dp-source -p a2dp-sink -p hfp-ag -p hsp-ag -c LDAC -c SBC -S --io-rt-priority=90
```

パッケージ既定は `RestrictRealtime=true` かつ `CapabilityBoundingSet=CAP_NET_RAW`
のみで、`--io-rt-priority=90` が無効になります。

### 12-4. 出力先は SP（PCH）を既定にする

```text
DEFAULT_DEVICE = "plughw:1,0"
VOLUME_DEFAULT = -25.0
```

Bluetooth を既定にすると、BT 切断時に CamillaDSP 自身が playback を開けず
無音が続きます。SP なら BT の有無に依存せず CamillaDSP は生存します。
初回起動時のフォールバック音量は -25dB（可聴域より十分小さい値）にしています。

保存済みの device があればそちらを優先します。BT を使う場合は GUI の
OUTPUT で明示的に選択してください。

### 12-5. 孤児プロセスに注意

`backend/scripts/switch_audio.sh` は CamillaDSP を `nohup` で起動するため、
**systemd 管理外のプロセスが起動**することがあります。この場合：

- `systemctl stop` が効かない
- `CPUSchedulingPolicy` / `LimitRTPRIO` が適用されない
- `Restart=always` が競合して再起動ループになる

CamillaDSP の状態を確認する際は、先に孤児プロセスを確認してください。

```bash
ps -eo pid,ppid,lstart,args | grep camilladsp | grep -v grep
# ppid が 1 で systemctl の MainPID と異なる場合は孤児プロセス
pgrep -x camilladsp | xargs -r kill -TERM
sudo systemctl reset-failed camilladsp
sudo systemctl start camilladsp
```

### 12-6. IRQ 固定（任意）

USB コントローラの割り込みを CPU0 から分離します。

```bash
# xhci_hcd の IRQ 番号を確認
grep -E 'xhci_hcd' /proc/interrupts
echo 4 | sudo tee /proc/irq/125/smp_affinity_list   # CPU2
```

**再起動で失われます。** 永続化する場合は udev ルール
（`/etc/udev/rules.d/`）が必要です。

### 12-7. 設定の検証

```bash
# サービスが RT で動作しているか
chrt -p $(pgrep -x camilladsp)     # SCHED_FIFO / 50 になるはず
grep 'Max realtime priority' /proc/$(pgrep -x camilladsp)/limits   # 95 になるはず
chrt -p $(pgrep -x bluealsa)      # BT 未接続時は SCHED_OTHER（A2DP IO スレッド未生成）

# underrun の監視
journalctl -u camilladsp -f | grep underrun
```

### 12-8. 既に最適化済みで変更不要な項目

本環境（Intel i7-6700HQ / 8スレッド）では以下は実測で良好と判断済みです。

| 項目 | 実測値 |
|---|---|
| CPU governor | 全コア `performance` |
| CPU 周波数 | 3100MHz 固定（±0.1%） |
| `processor.max_cstate=1` | カーネル cmdline に設定済み |
| `vm.swappiness` | 15 |
| `irqbalance` | 未インストール |
| Wi-Fi 省電力 | off |
| NIC EEE | 該当なし |
| swap | 使用 0B |

### 12-9. Bluetooth を使う場合の注意

WiFi が 2.4GHz 帯にある場合、A2DP と干渉して underrun が発生しやすくなります。
可能なら WiFi を 5GHz 帯（channel 36 以上）に変更してください。

CamillaDSP の設定/状態は `/var/lib/camilladsp/`（永続領域）にあります。
`/tmp` を使用するとリブートで消失して CamillaDSP が起動失敗します。

詳細な点検記録と未完了項目は
`docs/V3.0_INSPECTION_AND_FIX_REPORT.md` を参照してください。
