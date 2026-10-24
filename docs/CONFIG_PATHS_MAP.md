# 設定パス配置マップ

生成日: 2026-10-03
対象コミット: Root Fix B 適用後

---

## 1. 現在の配置一覧

| パス | 用途 | 所有モジュール | 永続性 | 権限 | 備考 |
|------|------|---------------|--------|------|------|
| ~/.config/audiophile/last_config.json | DSP設定永続化 (mode/device/volume/EQ等) | backend.dsp.state_manager | ✅ 永続 | user:user | 旧名互換 |
| ~/.config/audiophile/presets.json | DSPプリセット集 | backend.dsp.state_manager | ✅ 永続 | user:user | 旧名互換 |
| ~/.config/audiophile/profiles/*.json | DSPプロファイル (機器補正) | backend.dsp.profiles | ✅ 永続 | user:user | JSON Schema準拠 |
| ~/.config/hqmplayer/meta_cache.json | UPnP HTTPトラック メタデータ永続化 | hqmplayer_core.meta.cache | ✅ 永続 | user:user | 新規 (Phase 1c) |
| ~/.cache/audiophile/art/*.json | iTunesアート リダイレクトURLキャッシュ | hqmplayer_core.art.resolver | ✅ 永続 (TTL 30日) | user:user | TTLベース自動削除 |
| /var/lib/camilladsp/active_dsp.yml | CamillaDSP 実行用 YAML (生成物) | backend.dsp.yaml_generator | ✅ 永続 | user:user | **リブート後必須** |
| /var/lib/camilladsp/state.yml | CamillaDSP 音量・mute 状態 (statefile) | backend.dsp.apply_logic / switch_audio.sh | ✅ 永続 | user:user | **リブート後必須** |
| /var/lib/camilladsp/ir/*.wav | リバーブ用 IR ファイルコピー先 | switch_audio.sh | ✅ 永続 | user:user | 実行時コピー |
| /var/lib/camilladsp/switch_audio.log | switch_audio.sh 実行ログ | switch_audio.sh | ✅ 永続 | user:user | journal併記 |
| /var/lib/camilladsp/pure_passthrough.pid | Pureモード passthrough プロセス PID | switch_audio.sh | ⚠️ 揮発性 | user:user | 再起動で不要 |
| /tmp/hq_api_apply.log | 旧 _restore_last_config ログ (legacy) | backend/main.py (legacy) | ❌ 揮発 | user:user | **廃止予定** |
| /tmp/camilladsp/ | **廃止済み** (旧全ファイル配置先) | - | ❌ 揮発 (tmpfs) | - | **完全移行済み** |

---

## 2. 環境変数による上書き規則

| 環境変数 | 既定値 | 上書き対象 | 備考 |
|----------|--------|------------|------|
| AUDIOPHILE_CONFIG_DIR | ~/.config/audiophile | last_config/presets/profiles ディレクトリ | state_manager._resolve_config_dir() |
| XDG_CONFIG_HOME | ~/.config | 上記の親ディレクトリ | XDG仕様準拠 |
| CAMILLA_STATE_DIR | /var/lib/camilladsp | active_dsp.yml, state.yml, ir/, log, pid | paths.py, switch_audio.sh, systemd template |
| HQ_DSP_YAML | $CAMILLA_STATE_DIR/active_dsp.yml | 生成YAML実効パス | paths.dsp_yaml_path() |
| CAMILLA_STATE_FILE | $CAMILLA_STATE_DIR/state.yml | statefile 実効パス | paths.dsp_state_path() |
| HQ_GUI_ORIGINS | (空) | CORS 追加オリジン (カンマ区切り) | hq_api.main |
| ALLOWED_ORIGINS | (空) | CORS 置換オリジン (カンマ区切り) | hq_api.main |
| HQ_DMP_BACKEND | <repo>/dmp/backend | DMP ルータ import パス | hq_api.routers.dmp, hq_api.ws.status |
| HQ_UPNP_SERVERS_FILE | /etc/hqmplayer/upnp_servers.json | UPnPサーバ定義ファイル | upnp_service.py |

---

## 3. 配置ルール・原則

1. **/var/lib/camilladsp/ は永続・必須**
   - tmpfs (/tmp, /run, /var/tmp) への配置は**禁止** (リブートで消失)
   - install_systemd_units.sh が sudo install -d -o $USER -g $GROUP -m 0755 で事前作成
   - test_dsp_paths_consistency.py が揮発領域不使用をガード

2. **~/.config/audiophile/ は legacy 互換維持**
   - 既存ユーザーの last_config/presets を破壊しない
   - 新規 ~/.config/hqmplayer/ と併存

3. **~/.config/hqmplayer/ は新規統合領域**
   - meta_cache.json のみ現状
   - 将来的に audiophile 配下を統合移行予定

4. **~/.cache/audiophile/ はキャッシュ専用**
   - TTL 付き自動削除 (art: 30日)
   - 再生成可能な派生データのみ

5. **systemd unit は template 経由で環境変数注入**
   - config/systemd/*.template → install_systemd_units.sh → /etc/systemd/system/
   - 実機適用時のみ sudo 必要、dry-run で検証可能

---

## 4. 移行チェックリスト (将来統合時)

| 移行項目 | 現状 | 目標 | 手順 |
|---------|------|------|------|
| ~/.config/audiophile/ → ~/.config/hqmplayer/ | last_config, presets, profiles | 統合 | 1. 新ディレクトリ作成 2. コピー 3. 環境変数 AUDIOPHILE_CONFIG_DIR 更新 4. 旧パス読み取り互換維持 |
| ~/.cache/audiophile/art/ → ~/.config/hqmplayer/art_cache/ | iTunes redirect cache | 統合 (設定寄りに) | 同様 |
| /var/lib/camilladsp/ 権限 | user:user 0755 | 維持 | 変更不要 |
| 実機 /etc/hqmplayer/hqmplayer.env | 手動作成 | template 化 | config/systemd/hqmplayer.env.example をベースに作成 |

---

## 5. 検証コマンド

```bash
# 1. 揮発領域不使用確認 (test_dsp_paths_consistency.py)
./backend/venv/bin/python3 -m unittest tests.unit.test_dsp_paths_consistency -v

# 2. 実効パス確認
CAMILLA_STATE_DIR=/var/lib/camilladsp python3 -c "
from backend.dsp.paths import dsp_yaml_path, dsp_state_path, dsp_state_dir
print('yaml:', dsp_yaml_path())
print('state:', dsp_state_path())
print('dir:', dsp_state_dir())
"

# 3. 権限確認
ls -la /var/lib/camilladsp/
ls -la ~/.config/audiophile/
ls -la ~/.config/hqmplayer/
ls -la ~/.cache/audiophile/

# 4. systemd template 整合確認
./scripts/install_systemd_units.sh --stage=/tmp/stage-$(date +%s)
```

---

*本ドキュメントは CLEANUP_CHECKLIST.md D-2 に基づき作成された参考資料です。*
