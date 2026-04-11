const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

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
    artworkUrl:   (uri: string) => `${BASE}/api/library/artwork?uri=${encodeURIComponent(uri)}`,
  },

  // ── Playback ─────────────────────────────────────────────────
  playback: {
    status:   () => req<any>('/api/playback/status'),
    play:     () => req<any>('/api/playback/play',     { method: 'POST' }),
    pause:    () => req<any>('/api/playback/pause',    { method: 'POST' }),
    next:     () => req<any>('/api/playback/next',     { method: 'POST' }),
    previous: () => req<any>('/api/playback/previous', { method: 'POST' }),
    seek:     (position: number) =>
      req<any>('/api/playback/seek', { method: 'POST', body: JSON.stringify({ position }) }),
    toggleRandom: () => req<any>('/api/playback/random', { method: 'POST' }),
    toggleRepeat: () => req<any>('/api/playback/repeat', { method: 'POST' }),
  },

  // ── Queue ────────────────────────────────────────────────────
  queue: {
    get:      ()             => req<any>('/api/queue/'),
    add:      (uri: string, playNow = false, insertNext = false, meta?: { title?: string; artist?: string; album?: string; artwork_url?: string }) =>
      req<any>('/api/queue/add', {
        method: 'POST',
        body: JSON.stringify({ uri, play_now: playNow, insert_next: insertNext, ...meta }),
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
    addMultiple: (name: string, uris: string[]) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}/add-multiple`, {
        method: 'POST', body: JSON.stringify({ uris }),
      }),
    load:    (name: string) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}/load`, { method: 'POST' }),
    remove:  (name: string, pos: number) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}/tracks/${pos}`, { method: 'DELETE' }),
    delete:  (name: string) =>
      req<any>(`/api/playlists/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  },
}

export const WS_URL =
  (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001')
    .replace(/^http/, 'ws') + '/ws/status'
