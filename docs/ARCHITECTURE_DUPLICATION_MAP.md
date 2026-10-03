# アーキテクチャ二重実装・所有者マップ

生成日: $(date +%Y-%m-%d)
対象コミット: f02d6079

---

## 1. 二重実装マップ

| 機能領域 | 実装箇所 (複数) | 正 (Single Source) | 状態 |
|---------|----------------|-------------------|------|
| **AudioConfig / Pydanticモデル** | `backend/main.py` (legacy), `backend/dsp/models.py` (new) | `backend/dsp/models.py` | ✅ 統合済み |
| **DEFAULT_DEVICE / VOLUME_DEFAULT** | `hq_api/routers/dsp_apply.py`, `backend/dsp/state_manager.py`, `backend/dsp/models.py` | `backend/dsp/models.py` | ✅ 統合済み |
| **_detect_alsa_cards()** | `backend/dsp/yaml_generator.py`, `hq_api/routers/dsp.py`, `backend/main.py` | `backend/dsp/state_manager.py` (委譲化予定 / 今回は yaml_gen/dsp.py/main.py のみ委譲化) | 🟡 一部委譲 |
| **CamillaDSP接続 (CAMILLA_HOST/PORT)** | `backend/dsp/apply_logic.py` (import時凍結), `hq_api/routers/dsp.py`, `hq_api/routers/dsp_write.py`, `hq_api/routers/dsp_apply.py`, `hq_api/main.py` | 都度 `os.getenv()` 取得に統一 | ✅ 統合済み |
| **MPD接続ヘルパー** | `backend/main.py` (legacy), `hqmplayer_core/mpd/client.py` | `hqmplayer_core/mpd/client.py` | ✅ 統合済み |
| **Now Playing 整形** | `backend/main.py` (legacy), `hqmplayer_core/meta/formatting.py` | `hqmplayer_core/meta/formatting.py` | ✅ 統合済み |
| **メタキャッシュ** | `dmp/backend/app/services/meta_cache.py` (re-export), `hqmplayer_core/meta/cache.py` | `hqmplayer_core/meta/cache.py` | ✅ 統合済み |
| **アルバムアート解決** | `backend/main.py` (legacy), `hqmplayer_core/art/resolver.py` | `hqmplayer_core/art/resolver.py` | ✅ 統合済み |
| **WebSocket (now_playing/status/all + dmp/websocket)** | `hq_api/ws/now_playing.py`, `hq_api/ws/status.py`, `hq_api/ws/all.py`, `dmp/backend/app/routers/websocket.py` | 3系統併存 (GUIは now_playing 使用) | 🟡 仕様上併存 |
| **CORS 設定** | `backend/main.py` (legacy, `*`), `dmp/backend/app/main.py` (legacy, `*`), `hq_api/main.py` (正) | `hq_api/main.py` のみ | ✅ 正のみ残存 |
| **FastAPI app エントリーポイント** | `backend/main.py` (port 8000), `dmp/backend/app/main.py` (port 8001), `hq_api/main.py` (port 8002) | `hq_api/main.py` のみ稼働 | ✅ 正のみ稼働 |
| **GUI エントリーポイント** | `New GUI/` (prototype), `new-gui/app/page.tsx` (本番) | `new-gui/` | ✅ 正のみ残存 |
| **systemd unit template** | `config/systemd/*.template` (正), 実機 `/etc/systemd/system/` (適用済み) | template が正 | ✅ |
| **設定パス** | `~/.config/audiophile/`, `~/.config/hqmplayer/`, `~/.cache/audiophile/` | 3系統併存 | 🟡 要統合 |
| **Version 文字列** | `hq_api.__version__` (0.1.0-phase3b), `hqmplayer_core` (0.1.0), `dmp` (0.1.0), `new-gui` (0.1.0) | 各自独立 | 🟡 要統合 |

---

## 2. 所有者・責任モジュール表

| モジュール | 責任範囲 | 主要 export | 依存元 |
|-----------|----------|-------------|--------|
| `hqmplayer_core.mpd.client` | MPD 共有非同期接続・lock・idle分離 | `mpd_connection`, `mpd_idle_connection`, `mpd_probe_connection`, `get_client` | hq_api, dmp/backend |
| `hqmplayer_core.meta.formatting` | Now Playing 整形・URIクエリ抽出 | `format_now_playing`, `_extract_from_url_query`, `_clean_artist` | hq_api (dsp/ws), dmp/backend |
| `hqmplayer_core.meta.enrich` | MPD song dict → Track 変換 | `Track`, `song_to_track`, `_detect_source`, 正規化関数群 | hq_api (via formatting), dmp/backend (via mpd_service) |
| `hqmplayer_core.meta.cache` | UPnP HTTP メタ永続キャッシュ | `store`, `enrich`, `get`, `clear`, `size` | hq_api (via formatting), dmp/backend |
| `hqmplayer_core.art.resolver` | アルバムアート解決 (local→MPD→iTunes→SVG) | `resolve_art`, `get_cached_art`, `save_cached_art`, `ArtResult` | hq_api (dsp_readonly), dmp/backend |
| `backend.dsp.models` | **Pydanticモデル・定数の単一ソース** | `AudioConfig`, `VolumeControl`, `StoredAudioConfig`, `DspParams`, `DEFAULT_DEVICE`, `VOLUME_DEFAULT`, `_default_audio_config` | hq_api (dsp_apply, dsp_write), state_manager, tests |
| `backend.dsp.state_manager` | 設定永続化・正規化・前提チェック・デバイス実在判定 | `load/save_last_config`, `config_requires_restart`, `normalize_config_for_device`, `has_loopback_capture_device`, `bluetooth_sink_available`, `output_device_available`, `device_unavailability_reason`, `ensure_dsp_prerequisites`, `load/save_presets` | hq_api (dsp_apply, dsp_write, dsp_readonly), yaml_generator |
| `backend.dsp.yaml_generator` | CamillaDSP 4.1.3 YAML 生成 | `generate_camilladsp_yaml`, EQ定数, CTC/REV/ Loudness構築 | hq_api (dsp_apply), apply_logic, tests |
| `backend.dsp.apply_logic` | 音量初期化・DSP再起動・適用フロー | `init_vol`, `schedule_init_vol`, `restart_dsp`, `apply_audio` | hq_api (dsp_apply, dsp_write) |
| `backend.dsp.alsa` (予定) | ALSAカード検出の単一実装 | `detect_alsa_cards()` | yaml_generator, dsp router, state_manager |
| `backend.dsp.loudness` | ISO 226 Loudness フィルタ変換 | `spl_to_reference_level`, `build_loudness_filter`, `build_volume_filter` | yaml_generator |
| `backend.dsp.profiles` | JSON Schema プロファイル管理 | `load_profile`, `list_profiles`, `profile_to_biquads` | yaml_generator |
| `hq_api.main` | **本番エントリーポイント (port 8002)** | FastAPI app, DSP_LOCK, CORS, routers, WS, metrics, errors | systemd (hq-api.service) |
| `hq_api.routers.dsp` | DSP 読み取り (devices, now_playing, dsp_status) | GET endpoints | hq_api |
| `hq_api.routers.dsp_readonly` | DSP 読み取り専用 (config, presets, art, profiles) | GET endpoints | hq_api |
| `hq_api.routers.dsp_write` | DSP 書き込み (presets save/delete, volume) | POST/DELETE endpoints | hq_api |
| `hq_api.routers.dsp_apply` | DSP 適用 (restart, apply, dsp_update) | POST endpoints | hq_api |
| `hq_api.routers.dmp` | DMP ルータ re-export (library, playback, queue, history, playlists, upnp) | routers list | hq_api |
| `hq_api.ws.now_playing` | DSP互換 WS (idle駆動) | `/ws/now_playing` | hq_api, new-gui |
| `hq_api.ws.status` | DMP互換 WS (idle駆動+履歴副作用) | `/ws/status` | hq_api |
| `hq_api.ws.all` | 統合 WS (2s polling) | `/ws/all` | hq_api |
| `dmp.backend.app.routers.*` | DMP 機能実体 (library, playback, queue, history, playlists, upnp) | 各router | hq_api (via dmp.py re-import) |
| `new-gui` | **本番フロントエンド (port 3003)** | Next.js standalone | systemd (audiophile-new-gui.service) |
| `backend/scripts/switch_audio.sh` | Pure/DSP切替・CamillaDSP起動 | CLI tool | hq_api (apply_logic), systemd (camilladsp.service via ExecStartPre) |

---

## 3. 残存二重実装の優先度

| 優先度 | 項目 | 理由 | 見込み工数 |
|-------|------|------|----------|
| 高 | `detect_alsa_cards` 完全委譲 (yaml_gen/dsp.py/main.py → state_manager) | yamal_gen と dsp.py で未委譲、main.py は legacy だが警告防止 | 0.5日 |
| 高 | 設定パス統合 (`audiophile` vs `hqmplayer` vs `cache`) | 権限・移行手順が複雑化、バックアップ漏れリスク | 1日 |
| 中 | WebSocket 一本化 (`now_playing` + `status` → `all`) | GUI は now_playing のみ使用、status は履歴副作用のみ | 1日 |
| 中 | Version 統一 (semantic versioning 導入) | リリース管理・互換性確認が困難 | 0.5日 |
| 低 | CTC/CTC_response 等のテスト分離 | 機能拡張時の回帰防止 | 継続 |

---

*本ドキュメントは CLEANUP_CHECKLIST.md D-1 に基づき自動生成された参考資料です。*
