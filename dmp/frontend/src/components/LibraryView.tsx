'use client'
import { useState, useEffect, useCallback } from 'react'
import { Track, AlbumInfo } from '@/lib/types'
import { api } from '@/lib/api'
import { TrackRow } from './TrackRow'

type Mode = 'artists' | 'albums' | 'tracks' | 'search'

interface Props {
  currentUri?: string
  onAddToPlaylist?: (tracks: Track | Track[]) => void
}

// ── Section label ─────────────────────────────────────────────
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      padding: '10px 12px 6px',
      fontSize: 'var(--fs-xs)',
      letterSpacing: 'var(--ls-label)',
      textTransform: 'uppercase',
      color: 'var(--color-text-disabled)',
      fontWeight: 'var(--fw-medium)',
      borderBottom: '1px solid var(--color-border-subtle)',
    }}>
      {children}
    </div>
  )
}

// ── Breadcrumb ────────────────────────────────────────────────
function Breadcrumb({ crumbs, onNav }: {
  crumbs: { label: string; onClick: () => void }[],
  onNav?: () => void
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 4,
      padding: '8px 12px',
      borderBottom: '1px solid var(--color-border-subtle)',
      flexWrap: 'wrap',
    }}>
      {crumbs.map((c, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {i > 0 && <span style={{ color: 'var(--color-text-disabled)', fontSize: 'var(--fs-xs)' }}>›</span>}
          <button
            onClick={c.onClick}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 'var(--fs-sm)',
              color: i === crumbs.length - 1
                ? 'var(--color-text-tertiary)'
                : 'var(--color-text-muted)',
              padding: '2px 0',
            }}
          >
            {c.label}
          </button>
        </span>
      ))}
    </div>
  )
}

// ── Artist row ────────────────────────────────────────────────
function ArtistRow({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        width: '100%', textAlign: 'left',
        padding: '9px 12px',
        background: 'none', border: 'none',
        borderBottom: '1px solid var(--color-border-subtle)',
        cursor: 'pointer',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--color-surface-card)'}
      onMouseLeave={e => e.currentTarget.style.background = 'none'}
    >
      <span style={{
        fontSize: 'var(--fs-base)',
        color: 'var(--color-text-secondary)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {name}
      </span>
      <span style={{ color: 'var(--color-text-disabled)', fontSize: 'var(--fs-sm)', flexShrink: 0 }}>›</span>
    </button>
  )
}

// ── Album card ────────────────────────────────────────────────
function AlbumCard({ album, artistName, onClick }: {
  album: AlbumInfo; artistName: string; onClick: () => void
}) {
  const artUrl = album.artwork_url
  return (
    <button
      onClick={onClick}
      style={{
        background: 'var(--color-surface-card)',
        border: '1px solid var(--color-border-card)',
        borderRadius: 'var(--radius-lg)',
        cursor: 'pointer',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        textAlign: 'left',
        transition: 'border-color 0.15s, background 0.15s',
        padding: 0,
        width: '100%',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--color-border-medium)'
        e.currentTarget.style.background = 'var(--color-surface-bar)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--color-border-card)'
        e.currentTarget.style.background = 'var(--color-surface-card)'
      }}
    >
      {/* Artwork */}
      <div style={{
        width: '100%', paddingBottom: '100%',
        position: 'relative',
        background: 'var(--color-surface-bar)',
        overflow: 'hidden',
      }}>
        {artUrl ? (
          <img
            src={artUrl} alt=""
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 28, color: 'var(--color-text-disabled)',
          }}>
            ♪
          </div>
        )}
      </div>
      {/* Info */}
      <div style={{ padding: '8px 10px 10px' }}>
        <div style={{
          fontSize: 'var(--fs-sm)',
          fontWeight: 'var(--fw-medium)',
          color: 'var(--color-text-primary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          letterSpacing: 'var(--ls-title)',
        }}>
          {album.name}
        </div>
        {album.date && (
          <div style={{
            fontSize: 'var(--fs-xs)',
            color: 'var(--color-text-disabled)',
            marginTop: 2,
          }}>
            {album.date.slice(0, 4)}
          </div>
        )}
      </div>
    </button>
  )
}

// ── Main LibraryView ──────────────────────────────────────────
export function LibraryView({ currentUri, onAddToPlaylist }: Props) {
  const [mode, setMode] = useState<Mode>('artists')
  const [artists, setArtists] = useState<string[]>([])
  const [albums, setAlbums] = useState<AlbumInfo[]>([])
  const [tracks, setTracks] = useState<Track[]>([])
  const [selectedArtist, setSelectedArtist] = useState<string | null>(null)
  const [selectedAlbum, setSelectedAlbum] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Track[]>([])
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<{ artists: number; albums: number; songs: number } | null>(null)

  // Load initial data
  useEffect(() => {
    api.library.stats().then(setStats).catch(() => {})
    loadArtists()
  }, [])

  const loadArtists = async () => {
    setLoading(true)
    try {
      const data = await api.library.artists()
      setArtists(data.artists ?? [])
    } catch {}
    setLoading(false)
  }

  const selectArtist = async (name: string) => {
    setSelectedArtist(name)
    setMode('albums')
    setLoading(true)
    try {
      const data = await api.library.albumsByArtist(name)
      setAlbums(data.albums ?? [])
    } catch {}
    setLoading(false)
  }

  const selectAlbum = async (album: AlbumInfo) => {
    setSelectedAlbum(album.name)
    setMode('tracks')
    setLoading(true)
    try {
      const data = await api.library.tracksByAlbum(album.name, selectedArtist ?? undefined)
      setTracks(data.tracks ?? [])
    } catch {}
    setLoading(false)
  }

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setMode('artists'); return }
    setMode('search')
    setLoading(true)
    try {
      const data = await api.library.search(q)
      setSearchResults(data.tracks ?? [])
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => {
    const t = setTimeout(() => {
      if (searchQuery) doSearch(searchQuery)
      else if (mode === 'search') setMode('artists')
    }, 300)
    return () => clearTimeout(t)
  }, [searchQuery, doSearch])

  // Breadcrumbs
  const crumbs = [
    { label: 'Artists', onClick: () => { setMode('artists'); setSelectedArtist(null); setSelectedAlbum(null) } },
    ...(selectedArtist ? [{ label: selectedArtist, onClick: () => { setMode('albums'); setSelectedAlbum(null) } }] : []),
    ...(selectedAlbum ? [{ label: selectedAlbum, onClick: () => {} }] : []),
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Search bar */}
      <div style={{
        padding: '10px 12px',
        borderBottom: '1px solid var(--color-border-subtle)',
        background: 'var(--color-surface-panel)',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--color-surface-card)',
          border: '1px solid var(--color-border-input)',
          borderRadius: 'var(--radius-md)',
          padding: '6px 10px',
        }}>
          <span style={{ color: 'var(--color-text-disabled)', fontSize: 12 }}>🔍</span>
          <input
            type="text"
            placeholder="Search library…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              fontSize: 'var(--fs-base)',
              color: 'var(--color-text-input)',
              caretColor: 'var(--color-green)',
            }}
          />
          {searchQuery && (
            <button
              onClick={() => { setSearchQuery(''); setMode('artists') }}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--color-text-disabled)', fontSize: 12, lineHeight: 1,
              }}
            >✕</button>
          )}
        </div>
      </div>

      {/* Stats bar */}
      {stats && mode === 'artists' && !searchQuery && (
        <div style={{
          padding: '5px 12px',
          borderBottom: '1px solid var(--color-border-subtle)',
          display: 'flex', gap: 16,
        }}>
          {[
            { label: 'ARTISTS', val: stats.artists },
            { label: 'ALBUMS',  val: stats.albums },
            { label: 'TRACKS',  val: stats.songs },
          ].map(s => (
            <div key={s.label} style={{ display: 'flex', gap: 4, alignItems: 'baseline' }}>
              <span style={{ fontSize: 'var(--fs-xs)', letterSpacing: 'var(--ls-label)', color: 'var(--color-text-disabled)' }}>
                {s.label}
              </span>
              <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--color-text-tertiary)', fontVariantNumeric: 'tabular-nums' }}>
                {s.val.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Breadcrumb (when not at root) */}
      {mode !== 'artists' && mode !== 'search' && (
        <Breadcrumb crumbs={crumbs} onNav={() => {}} />
      )}

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-disabled)', fontSize: 'var(--fs-base)' }}>
            Loading…
          </div>
        )}

        {/* Artists */}
        {!loading && mode === 'artists' && (
          <div className="fade-in">
            {artists.length === 0 ? (
              <EmptyState
                icon="🎵"
                title="Library Empty"
                message="Mount your music drive and run mpc update to scan files."
              />
            ) : (
              artists.map(a => (
                <ArtistRow key={a} name={a} onClick={() => selectArtist(a)} />
              ))
            )}
          </div>
        )}

        {/* Albums grid */}
        {!loading && mode === 'albums' && (
          <div className="fade-in" style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
            gap: 10,
            padding: 12,
          }}>
            {albums.map(a => (
              <AlbumCard
                key={a.name}
                album={a}
                artistName={selectedArtist ?? ''}
                onClick={() => selectAlbum(a)}
              />
            ))}
          </div>
        )}

        {/* Tracks */}
        {!loading && mode === 'tracks' && (
          <div className="fade-in">
            {/* Album header */}
            {selectedAlbum && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '12px 12px 10px',
                borderBottom: '1px solid var(--color-border-subtle)',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 'var(--fs-lg)',
                    fontWeight: 'var(--fw-medium)',
                    color: 'var(--color-text-primary)',
                    letterSpacing: 'var(--ls-title)',
                  }}>{selectedAlbum}</div>
                  <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-text-muted)', marginTop: 2 }}>
                    {selectedArtist} · {tracks.length} tracks
                  </div>
                </div>
                {/* Play all button */}
                <button
                  onClick={async () => {
                    await api.queue.clear()
                    for (const t of tracks) await api.queue.add(t.uri)
                    await api.playback.play()
                  }}
                  style={{
                    background: 'var(--color-green-bg)',
                    border: '1px solid var(--color-green-border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--color-green)',
                    fontSize: 'var(--fs-sm)',
                    letterSpacing: 'var(--ls-button)',
                    textTransform: 'uppercase',
                    padding: '5px 10px',
                    cursor: 'pointer',
                    flexShrink: 0,
                  }}
                >
                  ▶ Play All
                </button>
                {/* Add all to playlist button */}
                <button
                  onClick={() => onAddToPlaylist?.(tracks)}
                  style={{
                    background: 'none',
                    border: '1px solid var(--color-border-medium)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--color-text-tertiary)',
                    fontSize: 'var(--fs-sm)',
                    letterSpacing: 'var(--ls-button)',
                    textTransform: 'uppercase',
                    padding: '5px 10px',
                    cursor: 'pointer',
                    flexShrink: 0,
                  }}
                >
                  + Playlist
                </button>
              </div>
            )}
            {tracks.map((t, i) => (
              <TrackRow
                key={t.id}
                track={t}
                index={i}
                isCurrent={t.uri === currentUri}
                onAddToPlaylist={onAddToPlaylist}
              />
            ))}
          </div>
        )}

        {/* Search results */}
        {!loading && mode === 'search' && (
          <div className="fade-in">
            <SectionLabel>
              {searchResults.length} results for "{searchQuery}"
            </SectionLabel>
            {searchResults.length === 0 ? (
              <EmptyState icon="🔍" title="No results" message="Try a different search term." />
            ) : (
              searchResults.map((t, i) => (
                <TrackRow
                  key={t.id}
                  track={t}
                  index={i}
                  showArtist
                  showAlbum
                  isCurrent={t.uri === currentUri}
                  onAddToPlaylist={onAddToPlaylist}
                />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function EmptyState({ icon, title, message }: { icon: string; title: string; message: string }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '48px 24px', gap: 8, textAlign: 'center',
    }}>
      <div style={{ fontSize: 32 }}>{icon}</div>
      <div style={{ fontSize: 'var(--fs-base)', fontWeight: 'var(--fw-medium)', color: 'var(--color-text-tertiary)' }}>
        {title}
      </div>
      <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)', maxWidth: 240 }}>
        {message}
      </div>
    </div>
  )
}
