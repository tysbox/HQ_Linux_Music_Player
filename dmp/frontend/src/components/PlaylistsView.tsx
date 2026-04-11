'use client'
import { useState, useEffect } from 'react'
import { Playlist, Track } from '@/lib/types'
import { api } from '@/lib/api'
import { TrackRow } from './TrackRow'

export function PlaylistsView() {
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [tracks, setTracks] = useState<Track[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const data = await api.playlists.list()
      setPlaylists(data.playlists ?? [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const selectPlaylist = async (name: string) => {
    setSelected(name)
    try {
      const data = await api.playlists.get(name)
      setTracks(data.tracks ?? [])
    } catch {}
  }

  const loadToQueue = async (name: string) => {
    await api.queue.clear()
    await api.playlists.load(name)
    await api.playback.play()
  }

  const deletePlaylist = async (name: string) => {
    await api.playlists.delete(name)
    if (selected === name) { setSelected(null); setTracks([]) }
    load()
  }

  const removeTrack = async (pos: number) => {
    if (!selected) return
    await api.playlists.remove(selected, pos)
    selectPlaylist(selected)
  }

  if (loading) return (
    <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-disabled)' }}>Loading…</div>
  )

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Sidebar: playlist list */}
      <div style={{
        width: selected ? '160px' : '100%',
        flexShrink: 0,
        borderRight: selected ? '1px solid var(--color-border-subtle)' : 'none',
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.2s',
      }}>
        <div style={{
          padding: '10px 12px',
          borderBottom: '1px solid var(--color-border-subtle)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{
            fontSize: 'var(--fs-xs)', letterSpacing: 'var(--ls-label)',
            textTransform: 'uppercase', color: 'var(--color-text-disabled)',
          }}>
            Playlists
          </span>

        </div>



        <div style={{ flex: 1, overflowY: 'auto' }}>
          {playlists.length === 0 ? (
            <div style={{ padding: '32px 12px', textAlign: 'center', color: 'var(--color-text-disabled)', fontSize: 'var(--fs-xs)' }}>
              No playlists yet
            </div>
          ) : (
            playlists.map(p => (
              <PlaylistRow
                key={p.name}
                name={p.name}
                isSelected={selected === p.name}
                onClick={() => selectPlaylist(p.name)}
                onPlay={() => loadToQueue(p.name)}
                onDelete={() => deletePlaylist(p.name)}
              />
            ))
          )}
        </div>
      </div>

      {/* Track list */}
      {selected && (
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 12px',
            borderBottom: '1px solid var(--color-border-subtle)',
          }}>
            <div>
              <div style={{ fontSize: 'var(--fs-base)', fontWeight: 'var(--fw-medium)', color: 'var(--color-text-primary)' }}>
                {selected}
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)', marginTop: 1 }}>
                {tracks.length} tracks
              </div>
            </div>
            <button
              onClick={() => loadToQueue(selected)}
              style={{
                background: 'var(--color-green-bg)',
                border: '1px solid var(--color-green-border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-green)',
                fontSize: 'var(--fs-xs)',
                letterSpacing: 'var(--ls-button)',
                textTransform: 'uppercase',
                padding: '5px 10px',
                cursor: 'pointer',
              }}
            >
              ▶ Play All
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {tracks.map((t, i) => (
              <div key={t.id} style={{ position: 'relative' }}>
                <TrackRow track={t} index={i} showArtist showAlbum />
                <button
                  onClick={() => removeTrack(i)}
                  style={{
                    position: 'absolute', right: 36, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--color-text-disabled)', fontSize: 11,
                  }}
                  onMouseEnter={e => e.currentTarget.style.color = 'var(--color-red)'}
                  onMouseLeave={e => e.currentTarget.style.color = 'var(--color-text-disabled)'}
                >✕</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function PlaylistRow({ name, isSelected, onClick, onPlay, onDelete }: {
  name: string; isSelected: boolean
  onClick: () => void; onPlay: () => void; onDelete: () => void
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '8px 12px',
        background: isSelected ? 'var(--color-green-bg)' : 'transparent',
        borderLeft: isSelected ? '2px solid var(--color-green)' : '2px solid transparent',
        borderBottom: '1px solid var(--color-border-subtle)',
        cursor: 'pointer', transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'var(--color-surface-card)' }}
      onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
    >
      <span style={{
        flex: 1, fontSize: 'var(--fs-sm)',
        color: isSelected ? 'var(--color-green)' : 'var(--color-text-tertiary)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {name}
      </span>
      <button
        onClick={e => { e.stopPropagation(); onPlay() }}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-disabled)', fontSize: 10 }}
        onMouseEnter={e => e.currentTarget.style.color = 'var(--color-green)'}
        onMouseLeave={e => e.currentTarget.style.color = 'var(--color-text-disabled)'}
      >▶</button>
      <button
        onClick={e => { e.stopPropagation(); onDelete() }}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-disabled)', fontSize: 10 }}
        onMouseEnter={e => e.currentTarget.style.color = 'var(--color-red)'}
        onMouseLeave={e => e.currentTarget.style.color = 'var(--color-text-disabled)'}
      >✕</button>
    </div>
  )
}
