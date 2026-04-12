SoX DSP Controller — README

概要
- `run_sox_fifo.sh` と `sox_gui.py` による SoX ベースのリアルタイム DSP パイプライン。MPD / BlueALSA 等と連携してフィルタ（FIR/EQ）やエフェクト（クロスフィード/bs2b）を適用します。

主な依存パッケージ（必須）
- sox
- ecasound  (crossfeed 挿入に使用)
- bs2b (LADSPA プラグイン: crossfeed)
- ladspa ライブラリパス (/usr/lib/ladspa または /usr/lib/x86_64-linux-gnu/ladspa)
- bluealsa / bluez（Bluetooth 出力を使う場合）
- alsa-utils (aplay など)
- mpd（オプション：MPD 連携用）

Python（GUI）依存
- Python 3
- tkinter (`python3-tk`)
- Pillow (`Pillow` / `python3-pil`)
- requests (`requests`)
- python-mpd2 (`python3-mpd2`)

インストール例（Debian/Ubuntu）
```
sudo apt update
sudo apt install -y sox ecasound bs2b ladspa-sdk bluez bluealsa alsa-utils mpd \
  python3 python3-tk python3-pil python3-requests python3-mpd2
# Python パッケージを pip で入れる場合
pip3 install --user Pillow requests python-mpd2
```

重要な設定点 / 概要（本リポジトリでの変更・留意点）
- Crossfeed: `run_sox_fifo.sh` は `ecasound` + `bs2b`（LADSPA）を介して crossfeed を挿入できます。クロスフィードは GUI の Effects タブで有効化します。
- LADSPA_PATH: 複数ディストリ間のパスを検出するロジックを追加（`/usr/lib/ladspa`, `/usr/lib/x86_64-linux-gnu/ladspa`, `/usr/local/lib/ladspa` を検索）。
- デフォルト出力: `sox_gui.py` と `run_sox_fifo.sh` はデフォルトで `BlueALSA`/`bluealsa` を優先します（`/etc/asound.conf` の設定に注意）。
- FIR/補正: 倍音/ノイズ用 FIR の `off` オプションを追加、複数 FIR 適用時の音量補正（FIR_COMPENSATION）を実装。
- Systemd ユニット: `run_sox_fifo.service` は `stdbuf -oL` を使いバッファ問題を回避、RT 優先度／CPUAffinity を設定して安定性を向上。
- SoX → BlueALSA: BlueALSA 出力時は LDAC 等を想定して特定条件で 96kHz にリサンプルする処理を含みます。
- GUI 機能: `sox_gui.py` は `run_sox_fifo.sh` のテンプレート更新／サービス再起動機能を持ちます（`--user` と system 両対応の試行あり）。

サービス（systemd）
- ユニットファイル：`/etc/systemd/system/run_sox_fifo.service`
- 有効化／起動例：
  - `sudo systemctl daemon-reload`
  - `sudo systemctl enable --now run_sox_fifo.service`
  - 状態確認：`systemctl status run_sox_fifo.service`

重要な設定ファイル
- `/etc/asound.conf` — BlueALSA をデフォルト PCM にする設定例あり。接続先 MAC アドレスや buffer_size / period_size は環境に合わせて編集してください。

動作確認コマンド
- `sox --version`
- `ecasound --version`
- `ls /usr/lib/ladspa | grep bs2b`
- `aplay -L | grep -i bluealsa`
- `systemctl status run_sox_fifo.service` (または `systemctl --user status run_sox_fifo.service`)

トラブルシュート（早見）
- SoX パイプラインが落ちる: `journalctl -u run_sox_fifo.service -b` を確認
- bs2b プラグインが見つからない: `ls /usr/lib*/ladspa/bs2b.so`
- GUI ランタイムエラー: Pillow / tkinter / python-mpd2 のインストールを確認

変更点（オリジナルとの差分まとめ）
1. `ecasound` + `bs2b` を使ったクロスフィード追加（`run_sox_fifo.sh`）。
2. LADSPA パス自動検出、`bs2b` 利用時の ecasound 挿入処理を実装。
3. `BlueALSA` を優先する出力ロジックを導入、`/etc/asound.conf` の調整を要する場合あり。
4. FIR の `off` オプション追加、FIR 適用時のゲイン補正を導入。
5. systemd ユニットに `stdbuf -oL` と RT 設定を追加して再生安定性を改善。
6. `sox_gui.py` に GUI からの設定保存／`run_sox_fifo.sh` 更新／サービス再起動機能を追加。

追加の質問や、特定ディストリ向けのインストール手順を希望される場合は教えてください。