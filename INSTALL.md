# 修正版セットアップ手順

## 1. ブランチ作成 & ファイル配置

```bash
# 既存リポジトリのクローンがあれば
cd ~/HQ_Linux_Music_Player
git checkout -b redesign/stable

# 修正ファイルを上書きコピー（ZIP展開後のパスに合わせて）
cp redesign/config/mpd.conf                          config/mpd.conf
cp redesign/config/asound.conf                       config/asound.conf
cp redesign/config/snd-aloop.conf                    config/snd-aloop.conf
cp redesign/config/systemd/*.service                 config/systemd/
cp redesign/backend/main.py                          backend/main.py
cp redesign/backend/scripts/switch_audio.sh          backend/scripts/switch_audio.sh
cp redesign/frontend/src/app/page.tsx                frontend/src/app/page.tsx

chmod +x backend/scripts/switch_audio.sh
```

---

## 2. システム側への適用

### snd-aloop 自動ロード
```bash
sudo cp config/snd-aloop.conf /etc/modules-load.d/snd-aloop.conf
sudo modprobe snd-aloop   # 今すぐ有効化（再起動不要）
```

### asound.conf
```bash
sudo cp config/asound.conf /etc/asound.conf
# Bluetooth を使う場合: MAC アドレスを実機に合わせて編集
sudo nano /etc/asound.conf
```

### mpd.conf
```bash
sudo cp config/mpd.conf /etc/mpd.conf
# カード番号を aplay -l で確認し必要なら編集
aplay -l
sudo nano /etc/mpd.conf
sudo systemctl restart mpd
```

### systemd サービス
```bash
# ユーザー名を実際の名前に置換（tysbox → 自分のユーザー名）
sed -i 's/tysbox/YOUR_USERNAME/g' config/systemd/audiophile-backend.service
sed -i 's/tysbox/YOUR_USERNAME/g' config/systemd/audiophile-frontend.service

sudo cp config/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 起動順序:
# loopback-drain → audiophile-backend → audiophile-frontend
sudo systemctl enable --now loopback-drain.service
sudo systemctl enable --now audiophile-backend.service
sudo systemctl enable --now audiophile-frontend.service
```

### sudo 権限（switch_audio.sh が loopback-drain を制御するため）
```bash
sudo visudo
# 以下を追記（YOUR_USERNAME を実際の名前に）:
YOUR_USERNAME ALL=(ALL) NOPASSWD: /bin/systemctl start loopback-drain.service
YOUR_USERNAME ALL=(ALL) NOPASSWD: /bin/systemctl stop loopback-drain.service
```

---

## 3. 動作確認

```bash
# MPD 出力を確認（Loopback / USB DAC / PC Speaker / Bluetooth が表示されればOK）
mpc outputs

# バックエンド起動確認
curl http://localhost:8000/api/devices

# ログ監視
tail -f /tmp/camilladsp/switch_audio.log
```

---

## 4. GitHub へ push

```bash
git add -A
git commit -m "redesign: stable mode switching, BT fallback, PC Speaker, state machine"
git push origin redesign/stable
```

---

## 主な変更点サマリー

| ファイル | 変更内容 |
|---------|---------|
| `config/mpd.conf` | 4出力定義（Loopback/USB DAC/PC Speaker/BT） |
| `config/asound.conf` | BTをデフォルト出力から外す |
| `config/snd-aloop.conf` | 新規: OS起動時にsnd-aloop自動ロード |
| `config/systemd/*.service` | 起動依存順序を正確に定義 |
| `backend/scripts/switch_audio.sh` | 状態機械として完全再設計 |
| `backend/main.py` | リバーブ2重登録バグ修正・BT自動FB・mpd_connect競合修正 |
| `frontend/src/app/page.tsx` | PC Speaker追加・BT警告UI・APIホスト動的化 |
