'use client'
import { useState, useEffect } from 'react'
import { Track, Playlist } from '@/lib/types'
import { api } from '@/lib/api'

interface Props {
  tracks: Track[]
  onClose: () => void
}

export function AddToPlaylistModal({ tracks, onClose }: Props) {
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [newName, setNewName]     = useState('')
  const [feedback, setFeedback]   = useState<string | null>(null)

  useEffect(() => {
    api.playlists.list().then(d => setPlaylists(d.playlists ?? [])).catch(() => {})
  }, [])

  const addTo = async (name: string) => {
    for (const t of tracks) await api.playlists.add(name, t.uri)
    setFeedback(`Added ${tracks.length > 1 ? `${tracks.length} tracks` : `"${tracks[0].title}"`} to "${name}"`)
    setTimeout(onClose, 1400)
  }

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 400,
      background: 'rgba(0,0,0,0.85)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 20,
    }}>
      <div onClick={e => e.stopPropagation()} className="fade-in" style={{
        width: '100%', maxWidth: 280,
        background: 'var(--alum-panel-bg)',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: 8, overflow: 'hidden',
        boxShadow: '0 24px 60px rgba(0,0,0,0.9)',
      }}>
        {/* Header */}
        <div style={{ padding: '11px 14px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <div className="engraved">Add to Playlist</div>
          <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.40)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {tracks.length > 1 ? `${tracks.length} tracks` : tracks[0]?.title}
          </div>
        </div>

        {feedback ? (
          <div style={{ padding: 20, textAlign: 'center' }}>
            <span className="led-green" style={{ fontSize: 10 }}>✓ {feedback}</span>
          </div>
        ) : (
          <>
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {playlists.map(p => (
                <button key={p.name} onClick={() => addTo(p.name)} style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '9px 14px', background: 'none', border: 'none',
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                  color: 'rgba(255,255,255,0.55)', fontSize: 10, cursor: 'pointer',
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'none'}
                >{p.name}</button>
              ))}
            </div>
            {/* New playlist */}
            <div style={{ padding: '10px 14px', display: 'flex', gap: 8, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="slot" style={{ flex: 1, display: 'flex', alignItems: 'center', borderRadius: 4, padding: '5px 8px' }}>
                <input type="text" placeholder="New playlist…" value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && newName.trim() && addTo(newName.trim())}
                  autoFocus
                  style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 10, color: 'rgba(255,255,255,0.60)', caretColor: 'var(--color-green)' }}
                />
              </div>
              <button className="touch-sw touch-sw-green" style={{ width: 30, height: 30, borderRadius: 4 }}
                onClick={() => newName.trim() && addTo(newName.trim())}>
                <span className="led-green" style={{ fontSize: 14 }}>+</span>
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
