INSTALL — SoX DSP Controller (簡易手順)

前提
- 本手順は Debian/Ubuntu 系を想定しています。別ディストリの場合はパッケージ名が異なることがあります。

1) 必須パッケージのインストール（Debian/Ubuntu）
```
sudo apt update
sudo apt install -y sox ecasound bs2b ladspa-sdk bluez bluealsa alsa-utils mpd \
  python3 python3-tk python3-pil python3-requests python3-mpd2
```
必要に応じて `pip3 install --user Pillow requests python-mpd2` を実行してください。

2) `run_sox_fifo.service` の配置と有効化
```
sudo cp run_sox_fifo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now run_sox_fifo.service
sudo systemctl status run_sox_fifo.service
```
- GUI を使う場合、`sox_gui.py` は `--user` の systemd ユニットを優先して操作しますが、システムユニットを使う構成（上記）が確実です。

3) ALSA / BlueALSA 設定
- `/etc/asound.conf` に `bluealsa` をデフォルトにする設定がある場合、`defaults.bluealsa.device` の MAC を環境に合わせるか削除して自動選択にしてください。
- `aplay -L` で `bluealsa` が見えることを確認。

4) LADSPA (bs2b) と ecasound の確認
- `ls /usr/lib*/ladspa/bs2b.so`
- `ecasound --version`
- クロスフィードを有効にするには `ecasound` と `bs2b`（LADSPA）が必要です。

5) Python GUI の起動（X 環境必要）
```
python3 /home/tysbox/bin/sox_gui.py
```
- 依存不足のエラーが出たら `python3-pil`, `python3-requests`, `python3-mpd2` のインストールを確認してください。

6) MPD / BT 連携
- MPD を使う場合は `mpd` を再起動：`sudo systemctl restart mpd`
- `bt_connect_watcher.sh` は BlueZ の接続イベントに応じて `run_sox_fifo.service` を再起動します（必要なら systemd で timer/service を設定）。

7) よくある問題と対処
- underrun/音飛び: `/etc/asound.conf` の `buffer_size` / `period_size` を調整、また `run_sox_fifo.service` の CPUAffinity/RT 優先度を検討。
- bs2b が効かない: `LADSPA_PATH` に `bs2b.so` が含まれているか確認。

差分（本インストールで注意すべき点）
- Crossfeed は `ecasound` を SoX の stdout と再生コマンドの間に挿入する実装です（追加のプロセスが入ります）。
- BlueALSA を前提にしたデフォルト動作があります。システムで PulseAudio/PipeWire を使う場合は出力デバイス指定を変更してください。

完了後の確認コマンド
```
sox --version
ecasound --version
ls /usr/lib*/ladspa/bs2b.so
systemctl status run_sox_fifo.service
aplay -L | grep -i bluealsa
```

サポート
- 追加で README に追記してほしい項目（例：Arch 手順、systemd user ユニット配置例など）があれば指示してください。