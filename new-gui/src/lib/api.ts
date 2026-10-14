import { API_BASE, WS_URL, request as req } from './http'

export { WS_URL }

// ── Library ───────────────────────────────────────────────────
export const api = {
  library: {
    stats:        ()             => req<any>('/api/library/stats'),
    artists:      ()             => req<any>('/api/library/artists'),
    albumsByArtist: (artist: string) =>
      req<any>(`/api/library/artists/${encodeURIComponent(artist)}/albums`),
    tracksByAlbum: (album: string, artist?: string) => {
      const q = artist ? `?artist=${encodeURIComponent(artist)}` : ''
      return req<any>(`/api/library/albums/${encodeURIComponent(album)}/tracks${q}`)
    },
    search:       (q: string)   => req<any>(`/api/library/search?q=${encodeURIComponent(q)}`),
    artworkUrl:   (uri: string) => `${API_BASE}/api/library/artwork?uri=${encodeURIComponent(uri)}`,
  },

  // ── Playback ─────────────────────────────────────────────────
  playback: {
    status:   () => req<any>('/api/playback/status'),
    play:     () => req<any>('/api/playback/play',     { method: 'POST' }),
    pause:    () => req<any>('/api/playback/pause',    { method: 'POST' }),
    toggle:   () => req<any>('/api/playback/toggle',   { method: 'POST' }),
    next:     () => req<any>('/api/playback/next',     { method: 'POST' }),
    previous: () => req<any>('/api/playback/previous', { method: 'POST' }),
    seek:     async (position: number) => {
      const res = await req<any>('/api/playback/seek', { method: 'POST', body: JSON.stringify({ position }) })
      return res
    },
    toggleRandom: () => req<any>('/api/playback/random', { method: 'POST' }),
    toggleRepeat: () => req<any>('/api/playback/repeat', { method: 'POST' }),
  },

  // ── Queue ────────────────────────────────────────────────────
  queue: {
    get:      ()             => req<any>('/api/queue/'),
    add:      (
      uri: string,
      playNow = false,
      insertNext = false,
      meta?: { title?: string; artist?: string; album?: string; artwork_url?: string }
    ) => req<any>('/api/queue/add', {
      method: 'POST',
      body: JSON.stringify({
        uri,
        play_now: playNow,
        insert_next: insertNext,
        ...(meta || {}),
      }),
    }),
    playAt:   (pos: number) => req<any>(`/api/queue/play/${pos}`, { method: 'POST' }),
    remove:   (pos: number) => req<any>(`/api/queue/${pos}`,      { method: 'DELETE' }),
    clear:    ()            => req<any>('/api/queue/clear',        { method: 'POST' }),
    shuffle:  ()            => req<any>('/api/queue/shuffle',      { method: 'POST' }),
    move:     (from: number, to: number) =>
      req<any>('/api/queue/move', { method: 'POST', body: JSON.stringify({ from_pos: from, to_pos: to }) }),
  },

  // ── History ──────────────────────────────────────────────────
  history: {
    get:   (limit = 100) => req<any>(`/api/history/?limit=${limit}`),
    clear: ()            => req<any>('/api/history/', { method: 'DELETE' }),
  },

  // ── Playlists ─────────────────────────────────────────────────
  playlists: {
    list:    ()             => req<any>('/api/playlists/'),
    get:     (name: string) => req<any>(`/api/playlists/${encodeURIComponent(name)}`),
    add:     (name: string, uri: string) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}/add`, {
        method: 'POST', body: JSON.stringify({ uri }),
      }),
    load:    (name: string) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}/load`, { method: 'POST' }),
    remove:  (name: string, pos: number) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}/tracks/${pos}`, { method: 'DELETE' }),
    delete:  (name: string) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  },

  // ── DSP (8002) ─────────────────────────────────────────────────────────
  // 2026-09-06 課題4: page.tsx の localhost:8002 直書きを撤廃し、
  // ホスト名/IP アクセス時にも BASE が追従するように統一。
  dsp: {
    /** GET /api/devices — ALSA デバイス一覧 (USB DAC / PC スピーカー等) */
    devices: () => req<any>('/api/devices'),

    /** GET /api/config — 永続化 DSP 設定 (mode/device/volume/dsp/etc.) */
    config:  () => req<any>('/api/config'),

    /** GET /api/dsp/profiles — インストール済みヘッドホン/スピーカープロファイル一覧 */
    profiles: () => req<any>('/api/dsp/profiles'),

    /** GET /api/dsp/profiles/{id} — プロファイル詳細 (preamp/bands 込み) */
    profile:  (id: string) => req<any>(`/api/dsp/profiles/${encodeURIComponent(id)}`),

    /** GET /api/dsp/headphones/catalog — 同梱 AutoEq 測定カタログ検索 (2,810 機種) */
    headphoneCatalog: (q: string, limit = 8) =>
      req<any>(`/api/dsp/headphones/catalog?q=${encodeURIComponent(q)}&limit=${limit}`),

    /** POST /api/dsp/headphones/catalog/{id}/import — カタログからプロファイル取込み */
    importHeadphone: (entryId: string) =>
      req<any>(`/api/dsp/headphones/catalog/${encodeURIComponent(entryId)}/import`, { method: 'POST' }),

    /** POST /api/volume — 音量のみ即時変更 (CamillaDSP ホットリロード) */
    setVolume: (volume: number) =>
      req<any>('/api/volume', {
        method: 'POST',
        body: JSON.stringify({ volume }),
      }),

    /** POST /api/dsp_update — DSP パラメータのみ更新 (ホットリロード、停止なし) */
    updateDspParams: (params: {
      music_type?: string
      eq_output?: string
      crossfeed?: string
      crossfeed_intensity?: number
      hum_noise?: string
      reverb?: string
      reverb_intensity?: number
      // Stage 7: CTC（クロストークキャンセレーション）
      ctc?: string
      ctc_intensity?: number
      // 絶対位相 (Absolute Phase) ON/OFF
      absolute_phase?: boolean
      // ISO 226 ラウドネス補正 ON/OFF
      loudness_enabled?: boolean
      // Stage 8 (Bisen移植 Phase 1): ホンキャリブレーション
      headphone_profile?: string
      headphone_intensity?: number
      // リキャリブレーション先 (harman既定 / flat / bypass / 機種プロファイルID)
      headphone_target?: string
      // Phase 3 (Bisen移植): Tube / Restore (bisen-dspd C++ デーモン経由)
      tube?: string                  // none / triode (300B) / pentode (KT88)
      tube_bias?: number             // 0-100
      restore?: string               // none / lossy_standard / lossy_high / cd
    }) => req<any>('/api/dsp_update', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

    /** POST /api/apply — DSP 全体適用 (CamillaDSP 再起動 + ALSA 切替を伴い得る) */
    apply: (config: {
      mode: 'pure' | 'dsp'
      device: string
      volume: number
      music_type?: string
      eq_output?: string
      crossfeed?: string
      crossfeed_intensity?: number
      hum_noise?: string
      reverb?: string
      reverb_intensity?: number
      // Stage 7: CTC（クロストークキャンセレーション）
      ctc?: string
      ctc_intensity?: number
      // 絶対位相 / ラウドネス
      absolute_phase?: boolean
      loudness_enabled?: boolean
      // Stage 8 (Bisen移植 Phase 1): ホンキャリブレーション
      headphone_profile?: string
      headphone_intensity?: number
      headphone_target?: string
      // Phase 3 (Bisen移植): Tube / Restore (bisen-dspd 経由)
      tube?: string
      tube_bias?: number
      restore?: string
    }) => req<any>('/api/apply', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  },

  // ── Presets（プリセット管理: name → ダイヤルスナップショット） ──
  presets: {
    /** GET /api/presets — プリセット一覧 (name → config 辞書) */
    list: () => req<any>('/api/presets'),
    /** POST /api/presets/save — プリセット保存 */
    save: (name: string, config: any) =>
      req<any>('/api/presets/save', { method: 'POST', body: JSON.stringify({ name, config }) }),
    /** DELETE /api/presets/{name} — プリセット削除 */
    remove: (name: string) =>
      req<any>(`/api/presets/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  },

  // ── Info（Phase 2: Bisen移植 — MusicBrainz 制作クレジット）─────
  info: {
    /** GET /api/info/credits — LISTENING WIKI 用クレジット (MB + Discogs + Wikipedia 統合) */
    credits: (artist: string, title: string, album = '') =>
      req<any>(`/api/info/credits?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}&album=${encodeURIComponent(album)}`),
  },
}
