'use client'
import { useState, useEffect } from 'react'
import { Playlist, Track } from '@/lib/types'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

export function PlaylistsView() {
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [selected, setSelected]   = useState<string | null>(null)
  const [tracks, setTracks]       = useState<Track[]>([])
  const [loading, setLoading]     = useState(true)

  const load = async () => {
    try { const d = await api.playlists.list(); setPlaylists(d.playlists ?? []) } catch {}
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const pick = async (name: string) => {
    setSelected(name)
    try { const d = await api.playlists.get(name); setTracks(d.tracks ?? []) } catch {}
  }

  if (loading) return <div style={{ padding: 24, textAlign: 'center' }}><span className="engraved">Loading…</span></div>

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Sidebar */}
      <div style={{ width: 150, flexShrink: 0, borderRight: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '8px 14px 6px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="engraved">Playlists</span>
          <span className="engraved" style={{ fontSize: 7, color: 'rgba(255,255,255,0.15)' }}>Add via ⋯ menu</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {playlists.length === 0 ? (
            <div style={{ padding: '24px 14px', textAlign: 'center' }}><span className="engraved" style={{ fontSize: 7 }}>No playlists yet</span></div>
          ) : playlists.map(p => (
            <div key={p.name} onClick={() => pick(p.name)} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 14px',
              background: selected === p.name ? 'rgba(34,197,94,0.05)' : 'transparent',
              borderLeft: selected === p.name ? '2px solid var(--color-green)' : '2px solid transparent',
              borderBottom: '1px solid rgba(255,255,255,0.04)',
              cursor: 'pointer',
            }}>
              <span style={{ flex: 1, fontSize: 9, color: selected === p.name ? 'var(--color-green)' : 'rgba(255,255,255,0.55)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {selected === p.name ? <span className="led-green">{p.name}</span> : p.name}
              </span>
              <button onClick={e => { e.stopPropagation(); api.playlists.delete(p.name).then(load) }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.18)', fontSize: 10 }}
                onMouseEnter={e => e.currentTarget.style.color = 'var(--color-red)'}
                onMouseLeave={e => e.currentTarget.style.color = 'rgba(255,255,255,0.18)'}
              >✕</button>
            </div>
          ))}
        </div>
      </div>

      {/* Track list */}
      {selected ? (
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 14px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 500, color: 'rgba(255,255,255,0.88)' }}>{selected}</div>
              <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.28)', marginTop: 1 }}>{tracks.length} tracks</div>
            </div>
            <button className="touch-sw touch-sw-green" style={{ height: 24, padding: '0 10px', gap: 5, borderRadius: 4 }}
              onClick={async () => { await api.queue.clear(); await api.playlists.load(selected); await api.playback.play() }}>
              <span className="led-green" style={{ fontSize: 9 }}>▶</span>
              <span className="engraved" style={{ fontSize: 7, color: 'rgba(34,197,94,0.65)', letterSpacing: '1px' }}>PLAY ALL</span>
            </button>
          </div>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
            {tracks.map((t, i) => (
              <div key={t.id} className="track-row" onDoubleClick={() => api.queue.add(t.uri, true, false, {
            title: t.title,
            artist: t.artist,
            album: t.album,
            artwork_url: t.artwork_url,
          })}>
                <div style={{ width: 18, textAlign: 'right', flexShrink: 0, fontSize: 8, color: 'rgba(255,255,255,0.22)', fontVariantNumeric: 'tabular-nums' }}>{i + 1}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 10, fontWeight: 500, letterSpacing: '-0.3px', color: 'rgba(255,255,255,0.88)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</div>
                  <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.32)', marginTop: 1 }}>{t.artist}</div>
                </div>
                <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.25)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{formatDuration(t.duration)}</div>
                <button className="touch-sw" style={{ width: 20, height: 20, borderRadius: 3, fontSize: 10, color: 'rgba(239,68,68,0.40)', flexShrink: 0 }}
                  onClick={() => api.playlists.remove(selected, i).then(() => pick(selected))}>✕</button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span className="engraved">Select a playlist</span>
        </div>
      )}
    </div>
  )
}
