# HQ Linux Music Player

MPD をバックエンドに持つ高音質 Linux 向けミュージックプレイヤーシステムです。  
Web UI（Next.js）から DSP パラメータをリアルタイム調整でき、CamillaDSP による本格的な信号処理と Pure ビットパーフェクト再生を切り替えられます。

---

## 目次

1. [システム概要](#システム概要)
2. [動作確認済み環境](#動作確認済み環境)
3. [ハードウェア要件](#ハードウェア要件)
4. [アーキテクチャ](#アーキテクチャ)
5. [インストール手順](#インストール手順)
   - [1. システムパッケージ](#1-システムパッケージ)
   - [2. ALSA Loopback カード有効化](#2-alsa-loopback-カード有効化)
   - [3. CamillaDSP インストール](#3-camilladsp-インストール)
   - [4. ALSA 設定（asound.conf）](#4-alsa-設定asoundconf)
   - [5. MPD 設定](#5-mpd-設定)
   - [6. IR リバーブファイル配置](#6-ir-リバーブファイル配置)
   - [7. Python バックエンドセットアップ](#7-python-バックエンドセットアップ)
   - [8. Next.js フロントエンドビルド](#8-nextjs-フロントエンドビルド)
   - [9. systemd サービス登録](#9-systemd-サービス登録)
   - [10. デスクトップランチャー（任意）](#10-デスクトップランチャー任意)
6. [設定のカスタマイズ](#設定のカスタマイズ)
7. [使い方](#使い方)
8. [トラブルシューティング](#トラブルシューティング)

---

## システム概要

| 機能 | 説明 |
|------|------|
| **Pure モード** | MPD → USB DAC への直結。ビットパーフェクト再生（リサンプリングなし / DAC ネイティブ形式） |
| **DSP モード** | MPD → ALSA Loopback → CamillaDSP → USB DAC。EQ・クロスフィード・ハム除去・IR リバーブをリアルタイム適用 |
| **Web UI** | ブラウザから操作。楽曲情報・アルバムアート表示・デバイス切替・音量調整 |
| **Bluetooth** | BlueALSA (A2DP) 経由で BT スピーカー/ヘッドフォンへ出力 |

---

## 動作確認済み環境

- **OS**: Debian GNU/Linux 13 (trixie) / antiX ベース
- **カーネル**: Linux x86_64
- **Python**: 3.13
- **Node.js**: 20.x
- **CamillaDSP**: 4.0.0
- **MPD**: 0.23.x

---

## ハードウェア要件

| 種類 | 条件 |
|------|------|
| USB DAC | ALSA で認識されるもの（例: HIFIMAN BLUEMINI R2R） |
| PC サウンドカード | HDA Intel PCH 等（PC スピーカー出力用, card1 相当） |
| Bluetooth | BlueALSA 対応アダプタ（オプション） |
| カーネルモジュール | `snd-aloop`（ALSA Loopback, DSP モード必須） |

> **注意**: ALSA カード番号（card0, card1, card2 など）は環境によって異なります。  
> インストール後に `aplay -l` で確認し、各設定ファイルのカード番号を合わせてください。

---

## アーキテクチャ

```
【Pure モード】
  MPD ──────────────────────────────────→ USB DAC (plughw:X,0)
              mpc enable only "USB DAC"

【DSP モード】
  MPD ──→ ALSA Loopback (hw:Loopback,0,0)
              ↓
         CamillaDSP (capture: hw:Loopback,1,0)
           ├ EQ (音楽ジャンル / 出力機器)
           ├ クロスフィード
           ├ ハム/ハムノイズ除去
           └ IR リバーブ (hall.wav / jazz_club.wav)
              ↓
         USB DAC (plughw:X,0)

【Web UI】
  ブラウザ (port 3000)
       ↕ REST API
  FastAPI バックエンド (port 8000)
       ├ MPD 操作 (python-mpd2)
       ├ CamillaDSP YAML 生成
       └ switch_audio.sh 呼び出し
```

---

## インストール手順

### 1. システムパッケージ

```bash
sudo apt update
sudo apt install -y \
    mpd mpc \
    alsa-utils alsa-tools \
    bluez bluealsa \
    arecord \
    python3 python3-venv python3-pip \
    nodejs npm \
    git
```

> **Bluetooth を使わない場合** は `bluez bluealsa` を省略できます。

---

### 2. ALSA Loopback カード有効化

DSP モードでは ALSA Loopback デバイスが必須です。

```bash
# カーネルモジュールをロード
sudo modprobe snd-aloop

# OS 起動時に自動ロード
sudo install -m 0644 config/modules-load/snd-aloop.conf /etc/modules-load.d/snd-aloop.conf

# Loopback が認識されたか確認（card番号を控える）
aplay -l | grep -i loopback
```

Loopback の card 番号は環境や起動順で変動します。固定値を前提にせず、`aplay -l` の出力を確認してください。

---

### 3. CamillaDSP インストール

CamillaDSP は公式リリースからビルド済みバイナリを取得します。

```bash
# Rust をインストール（ビルドする場合）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# または GitHub Releases からビルド済みバイナリをダウンロード
# https://github.com/HEnquist/camilladsp/releases
# x86_64 Linux の場合:
wget https://github.com/HEnquist/camilladsp/releases/download/v4.0.0/camilladsp-linux-amd64.tar.gz
tar xzf camilladsp-linux-amd64.tar.gz
sudo mv camilladsp /usr/local/bin/
sudo chmod +x /usr/local/bin/camilladsp

# 確認
camilladsp --version
# → CamillaDSP 4.0.0
```

---

### 4. ALSA 設定（asound.conf）

`config/asound.conf` をシステムにコピーします。

```bash
sudo cp config/asound.conf /etc/asound.conf
sudo chmod 644 /etc/asound.conf
```

Bluetooth を使う場合は、固定 MAC や固定アダプタに縛らず、直近に接続されたデバイスを使う設定を推奨します：

```
defaults.bluealsa.profile "a2dp"
defaults.bluealsa.device "00:00:00:00:00:00"
```

`defaults.bluealsa.interface` は指定しません。これにより `hci1` など特定アダプタへの固定を避けられます。

Bluetooth を使わない場合は `/etc/asound.conf` の内容を以下のみにしてください：

```
# /etc/asound.conf (Bluetooth なし)
# 空ファイルでも動作します
```

---

### 5. MPD 設定

#### 5-1. mpd.conf のコピー

```bash
sudo cp config/mpd.conf /etc/mpd.conf
```

#### 5-2. カード番号の確認と編集

`aplay -l` でデバイスのカード番号を確認します。

```
$ aplay -l
**** リストのハードウェアデバイス PLAYBACK ****
カード 0: Loopback [Loopback], デバイス 0: Loopback PCM [Loopback PCM]
カード 1: PCH [HDA Intel PCH], デバイス 0: ALC...
カード 2: BLUEMINI [HIFIMAN BLUEMINI R2R], デバイス 0: ...
```

上記の例では:
| デバイス | カード番号 | MPD 設定値 |
|---------|-----------|-----------|
| ALSA Loopback | 0 | `hw:Loopback,0,0` (名前指定なので変更不要) |
| PC スピーカー | 1 | `plughw:1,0` |
| USB DAC | 2 | `plughw:2,0` |

USB DAC や PC スピーカーのカード番号が異なる場合は `/etc/mpd.conf` を編集してください：

```bash
sudo nano /etc/mpd.conf
```

```
# USB DAC のカード番号を実際の番号に変更
audio_output {
    type            "alsa"
    name            "USB DAC"
    device          "plughw:2,0"    # ← USB DAC のカード番号
    mixer_type      "software"
}

audio_output {
    type            "alsa"
    name            "PC Speakers"
    device          "plughw:1,0"    # ← PC スピーカーのカード番号
    mixer_type      "software"
}
```

#### 5-3. 音楽ディレクトリの設定

```bash
sudo nano /etc/mpd.conf
# music_directory の行を環境に合わせて変更
# 例: music_directory "/media/username/Music"
```

#### 5-4. MPD ユーザーの sudo 権限設定（loopback-drain サービス用）

```bash
sudo install -m 0440 config/sudoers/hq-loopback-drain /etc/sudoers.d/hq-loopback-drain
# 必要ならユーザー名 tysbox を実際のユーザー名に変更してから配置
```

`backend/scripts/switch_audio.sh` は `sudo -n` で `loopback-drain.service` を制御します。  
この sudoers が無いと GUI の Apply は HTTP 200 でも内部の音声切替が実行されません。

#### 5-4a. 再起動用 service 配置

```bash
sudo cp frontend/audiophile-frontend.service /etc/systemd/system/
sudo cp backend/audiophile-backend.service /etc/systemd/system/
sudo cp dmp/backend/dmp-backend.service /etc/systemd/system/hq-dmp-backend.service
sudo cp dmp/frontend/dmp-frontend.service /etc/systemd/system/hq-dmp-frontend.service
sudo systemctl daemon-reload
sudo systemctl enable audiophile-frontend.service audiophile-backend.service hq-dmp-frontend.service hq-dmp-backend.service
```

`audiophile-frontend.service` と `hq-dmp-frontend.service` は起動時に `.next/static` と `public` を `standalone` 配下へ同期します。  
これが無いと再起動後に `/_next/static/...` が 404 になり、GUI が白画面化します。

#### 5-5. MPD の起動

```bash
sudo systemctl enable --now mpd
mpc outputs
# 4つの出力が表示されれば OK
# Output 1 (ALSA Loopback) ...
# Output 2 (USB DAC) ...
# Output 3 (PC Speakers) ...
# Output 4 (Bluetooth) ...
```

---

### 6. IR リバーブファイル配置

IR リバーブ（インパルス応答）ファイルは手動で配置が必要です。

```bash
mkdir -p ~/.config/camilladsp/ir

# リバーブ WAV ファイルをコピー（16bit ステレオ WAV）
# 例: hall.wav, jazz_club.wav
cp /path/to/your/ir/*.wav ~/.config/camilladsp/ir/
```

WAV ファイルは **16bit / ステレオ** 形式である必要があります。  
ファイル名（拡張子なし）が UI のプリセット名として表示されます。

> リバーブを使わない場合はこの手順をスキップできます。

---

### 7. Python バックエンドセットアップ

```bash
cd backend

# 仮想環境を作成
python3 -m venv venv
source venv/bin/activate

# 依存パッケージをインストール
pip install --upgrade pip
pip install \
    fastapi==0.135.2 \
    uvicorn==0.42.0 \
    python-mpd2==3.1.1 \
    PyYAML==6.0.3 \
    pydantic==2.12.5 \
    requests==2.33.0 \
    websocket-client==1.9.0

# pycamilladsp（公式 GitHub から）
pip install git+https://github.com/HEnquist/pycamilladsp.git

# 確認
pip list | grep -E "fastapi|uvicorn|mpd|camilla"
```

#### バックエンドの接続先を環境に合わせて確認

`main.py` の先頭付近にある USB DAC 検出ロジックは `aplay -l` の出力から "USB" キーワードを含む行を自動検出します。  
PC スピーカーのカード番号が `1` でない場合は以下の行を変更してください：

```python
# backend/main.py  約75行目
devices.append({"id": "hw:1,0", "name": "PC Speakers (hw:1,0)"})
#                       ↑ PCスピーカーのカード番号
```

---

### 8. Next.js フロントエンドビルド

```bash
cd frontend

# 依存パッケージをインストール
npm install

# 本番用ビルド
npm run build

# ビルド確認
ls .next/
```

---

### 9. systemd サービス登録

#### 9-1. サービスファイルのインストール

```bash
# ユーザー名を自分の環境に合わせて変更（tysbox → 実際のユーザー名）
sed -i 's/tysbox/実際のユーザー名/g' config/systemd/audiophile-backend.service
sed -i 's/tysbox/実際のユーザー名/g' config/systemd/audiophile-frontend.service

# パスも環境に合わせて変更（/home/tysbox → /home/実際のユーザー名）
sudo cp config/systemd/audiophile-backend.service /etc/systemd/system/
sudo cp config/systemd/audiophile-frontend.service /etc/systemd/system/
sudo cp config/systemd/loopback-drain.service /etc/systemd/system/
```

#### 9-2. サービスの有効化・起動

```bash
sudo systemctl daemon-reload

# 自動起動を有効化
sudo systemctl enable audiophile-backend.service
sudo systemctl enable audiophile-frontend.service
sudo systemctl enable loopback-drain.service

# 起動
sudo systemctl start loopback-drain.service
sudo systemctl start audiophile-backend.service
sudo systemctl start audiophile-frontend.service

# 状態確認
sudo systemctl status audiophile-backend.service
sudo systemctl status audiophile-frontend.service
```

#### 9-3. ログ確認

```bash
# バックエンドのログ
sudo journalctl -u audiophile-backend.service -f

# フロントエンドのログ
sudo journalctl -u audiophile-frontend.service -f
```

#### サービス一覧と役割

| サービス名 | 役割 |
|-----------|------|
| `mpd.service` | Music Player Daemon（音楽再生エンジン） |
| `audiophile-backend.service` | FastAPI バックエンド (port 8000) |
| `audiophile-frontend.service` | Next.js フロントエンド (port 3000) |
| `loopback-drain.service` | ALSA Loopback のドレイン（MPD フリーズ防止） |

---

### 10. デスクトップランチャー（任意）

XFCE / GNOME 等のデスクトップ環境でアイコンから起動したい場合：

```bash
cat > ~/Desktop/HQ-Music-Player.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=HQ Music Player
Name[ja]=HQミュージックプレイヤー
Comment=High Quality Linux Music Player
Exec=firefox --new-window http://localhost:3000
Icon=multimedia-player
Terminal=false
Categories=AudioVideo;Audio;Player;
EOF

chmod +x ~/Desktop/HQ-Music-Player.desktop
```

> `firefox` の部分を `chromium` や `google-chrome` に変えることもできます。

---

## 設定のカスタマイズ

### MPD 出力名と switch_audio.sh の対応

`/etc/mpd.conf` の出力名を変更した場合は `backend/scripts/switch_audio.sh` の以下の部分を合わせて変更してください：

```bash
# switch_audio.sh: Pure モードの出力名マッピング
if [[ "$DEVICE" == *bluealsa* ]]; then
    OUTPUT_NAME="Bluetooth"          # ← mpd.conf の name と一致させる
elif [[ "$DEVICE" == *hw:1* || "$DEVICE" == *plughw:1* ]]; then
    OUTPUT_NAME="PC Speakers"        # ← mpd.conf の name と一致させる
else
    OUTPUT_NAME="USB DAC"            # ← mpd.conf の name と一致させる
fi
```

### EQ プリセットのカスタマイズ

`backend/main.py` の `MUSIC_EQ` / `OUTPUT_EQ` ディクショナリに Band Peaking フィルタ（周波数・Q値・ゲイン）を追加・変更できます。

### CamillaDSP YAML の手動確認

適用後の設定は `/tmp/camilladsp/active_dsp.yml` に生成されます。  
直接確認・編集してデバッグに活用できます。

```bash
cat /tmp/camilladsp/active_dsp.yml
```

---

## 使い方

1. ブラウザで `http://localhost:3000`（または `http://<PC_IP>:3000`）を開く
2. 上部の **Mode** で `Pure` または `DSP` を選択
3. **Device** で出力先を選択（USB DAC / PC Speakers / Bluetooth）
4. DSP モードの場合：音楽ジャンル・出力機器 EQ・クロスフィード・リバーブを設定
5. **Apply** ボタンで設定を反映
6. 音楽は MPD で管理（Cantata、mpc 等のMPDクライアントから操作）

> スマートフォンからも `http://<PC_IP>:3000` でアクセスできます（同一 LAN 内）。

---

## トラブルシューティング

### 音が出ない / Pure モードで無音

```bash
# MPD の出力状態を確認
mpc outputs

# USB DAC が使えているか確認
cat /proc/asound/card2/pcm0p/sub0/status
# → state: RUNNING であれば正常

# MPD のログ
sudo journalctl -u mpd -n 30
```

### DSP モードで音が出ない

```bash
# CamillaDSP が起動しているか
pgrep -a camilladsp

# Loopback デバイスの状態
cat /proc/asound/Loopback/pcm0p/sub0/status   # MPD 書き込み側
cat /proc/asound/Loopback/pcm1c/sub0/status   # CamillaDSP 読み取り側

# ログ
cat /tmp/camilladsp/switch_audio.log | tail -30
```

### CamillaDSP が `YAML parse error` で起動しない

```bash
# 生成された YAML を確認
cat /tmp/camilladsp/active_dsp.yml

# CamillaDSP を手動起動してエラー内容を確認
camilladsp -p 1234 /tmp/camilladsp/active_dsp.yml
```

### USB DAC のカード番号が変わった

USB DAC のカード番号はデバイスの接続順で変わることがあります。

```bash
aplay -l
# → カード番号を確認

# mpd.conf の "USB DAC" device を更新
sudo nano /etc/mpd.conf
sudo systemctl restart mpd

# main.py の USB-DAC 検出は自動（aplay -l からUSBキーワードで検索）
# ただしフロントエンドで選んだデバイスIDが古い場合は再選択してください
```

### `Address already in use` エラー

ポート 8000 または 3000 が他プロセスに使われています。

```bash
# 占有プロセスを確認・終了
fuser -k 8000/tcp
fuser -k 3000/tcp

sudo systemctl restart audiophile-backend.service audiophile-frontend.service
```

### loopback-drain が `failed` になる

DSP モード中は CamillaDSP が Loopback を占有するため loopback-drain は停止が正常です。  
Pure モード中や待機中に `failed` になる場合：

```bash
sudo systemctl restart loopback-drain.service
sudo journalctl -u loopback-drain.service -n 20
```

---

## ディレクトリ構成

```
audiophile-web/
├── backend/
│   ├── main.py                  # FastAPI アプリ本体
│   ├── scripts/
│   │   └── switch_audio.sh      # Pure/DSP モード切替スクリプト
│   └── venv/                    # Python 仮想環境（git 管理外）
├── frontend/
│   ├── src/app/
│   │   ├── page.tsx             # メイン UI
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── package.json
│   └── next.config.ts
└── config/
    ├── mpd.conf                 # MPD 設定（参考用）
    ├── asound.conf              # ALSA 設定（参考用）
    └── systemd/
        ├── audiophile-backend.service
        ├── audiophile-frontend.service
        └── loopback-drain.service
```

---

## ライセンス

このプロジェクトは個人使用を目的としています。
## 重要事項: WebSocket と DSP 追加設定

### WebSocket ステータスインジケーター
- 🟢 緑（点灯）: WebSocket 接続成功 / `GET /ws/now_playing` が 101 接続
- 🟡 黄（点滅）: 接続試行中 / `websockets` 未インストール、または接続失敗のリトライ
- 🔴 赤: 接続不可、リトライ待機

### WebSocket 設定確認
1. 仮想環境を有効化
```bash
cd backend && source venv/bin/activate
```
2. パッケージインストール
```bash
pip install websockets
```
3. FastAPI バックエンド再起動
```bash
sudo systemctl restart audiophile-backend.service
```
4. ログ確認
```bash
sudo journalctl -u audiophile-backend.service -n 30 --no-pager
```

### CamillaDSP リサンプラー設定
`backend/main.py` で `generate_camilladsp_yaml` 関数の `resampler` を調整できます:
- `AsyncPoly`: `interpolation` は `Linear`, `Cubic`, `Quintic`, `Septic` のいずれか
- `Synchronous`: 変換不要時に推奨

今回の修正では `Septic` を動作確認済み。

### 追加デバッグ方法
- `mpc outputs` / `mpc status`
- `curl -s http://localhost:8000/api/now_playing`
- `curl -s http://localhost:3000/ws/now_playing` でWebSocket接続状態を確認（ブラウザ側からも確認）
