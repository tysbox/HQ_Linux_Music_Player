'use client'
import { useState, useEffect } from 'react'
import { Track, Playlist } from '@/lib/types'
import { api } from '@/lib/api'

interface Props {
  tracks: Track[]   // supports single or multiple tracks
  onClose: () => void
}

export function AddToPlaylistModal({ tracks, onClose }: Props) {
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [newName, setNewName] = useState('')
  const [feedback, setFeedback] = useState<string | null>(null)
  const isBatch = tracks.length > 1

  useEffect(() => {
    api.playlists.list().then(d => setPlaylists(d.playlists ?? [])).catch(() => {})
  }, [])

  const addTo = async (name: string) => {
    if (isBatch) {
      await api.playlists.addMultiple(name, tracks.map(t => t.uri))
    } else {
      await api.playlists.add(name, tracks[0].uri)
    }
    setFeedback(`${isBatch ? `${tracks.length} tracks` : `"${tracks[0].title}"`} → "${name}"`)
    setTimeout(onClose, 1400)
  }

  const createAndAdd = async () => {
    if (!newName.trim()) return
    await addTo(newName.trim())
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 300,
        background: 'rgba(0,0,0,0.8)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--color-surface-bar)',
          border: '1px solid var(--color-border-medium)',
          borderRadius: 'var(--radius-lg)',
          width: '100%', maxWidth: 300,
          overflow: 'hidden',
        }}
        className="fade-in"
      >
        {/* Header */}
        <div style={{
          padding: '12px 14px',
          borderBottom: '1px solid var(--color-border-subtle)',
        }}>
          <div style={{ fontSize: 'var(--fs-xs)', letterSpacing: 'var(--ls-label)', textTransform: 'uppercase', color: 'var(--color-text-disabled)' }}>
            Add to Playlist
          </div>
          <div style={{
            fontSize: 'var(--fs-sm)', color: 'var(--color-text-tertiary)', marginTop: 4,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {isBatch ? `${tracks.length} tracks` : tracks[0]?.title}
          </div>
        </div>

        {feedback ? (
          <div style={{
            padding: '20px', textAlign: 'center',
            color: 'var(--color-green)', fontSize: 'var(--fs-base)',
          }}>
            ✓ {feedback}
          </div>
        ) : (
          <>
            {/* Existing playlists */}
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {playlists.map(p => (
                <button
                  key={p.name}
                  onClick={() => addTo(p.name)}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '9px 14px',
                    background: 'none', border: 'none',
                    borderBottom: '1px solid var(--color-border-subtle)',
                    color: 'var(--color-text-tertiary)',
                    fontSize: 'var(--fs-base)', cursor: 'pointer',
                    transition: 'background 0.1s, color 0.1s',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--color-surface-card)'
                    e.currentTarget.style.color = 'var(--color-text-primary)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'none'
                    e.currentTarget.style.color = 'var(--color-text-tertiary)'
                  }}
                >
                  {p.name}
                </button>
              ))}
            </div>

            {/* New playlist input */}
            <div style={{ padding: '10px 14px', display: 'flex', gap: 8 }}>
              <input
                type="text"
                placeholder="New playlist…"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && createAndAdd()}
                style={{
                  flex: 1, background: 'var(--color-surface-card)',
                  border: '1px solid var(--color-border-input)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-text-input)',
                  fontSize: 'var(--fs-sm)', padding: '5px 8px',
                  outline: 'none', caretColor: 'var(--color-green)',
                }}
              />
              <button
                onClick={createAndAdd}
                style={{
                  background: 'var(--color-green-bg)',
                  border: '1px solid var(--color-green-border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-green)',
                  fontSize: 'var(--fs-sm)', padding: '5px 10px',
                  cursor: 'pointer',
                }}
              >
                +
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
