'use client'
import { useState, useEffect, useCallback } from 'react'
import { Track, AlbumInfo } from '@/lib/types'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

interface Props {
  currentUri?: string
  onAddToPlaylist?: (t: Track | Track[]) => void
}

function SectionHdr({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      padding: '8px 14px 6px',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
    }}>
      <span className="engraved">{children}</span>
    </div>
  )
}

function Breadcrumb({ crumbs }: { crumbs: { label: string; onClick: () => void }[] }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      padding: '6px 14px',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
      flexWrap: 'wrap',
    }}>
      {crumbs.map((c, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {i > 0 && <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 8 }}>›</span>}
          <button onClick={c.onClick} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 9,
            color: i === crumbs.length - 1 ? 'rgba(255,255,255,0.55)' : 'rgba(255,255,255,0.30)',
            padding: '1px 0',
          }}>{c.label}</button>
        </span>
      ))}
    </div>
  )
}

function ArtistRow({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      width: '100%', textAlign: 'left',
      padding: '9px 14px', background: 'none', border: 'none',
      borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'pointer',
    }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
      onMouseLeave={e => e.currentTarget.style.background = 'none'}
    >
      <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.78)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {name}
      </span>
      <span style={{ color: 'rgba(255,255,255,0.18)', fontSize: 9, flexShrink: 0 }}>›</span>
    </button>
  )
}

function AlbumGrid({ albums, onSelect }: { albums: AlbumInfo[]; onSelect: (a: AlbumInfo) => void }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
      gap: 8, padding: 12,
    }}>
      {albums.map(a => (
        <button key={a.name} onClick={() => onSelect(a)} style={{
          background: 'var(--alum-panel-bg)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 6, overflow: 'hidden', cursor: 'pointer',
          textAlign: 'left', padding: 0,
          transition: 'border-color 0.12s',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 2px 6px rgba(0,0,0,0.4)',
        }}
          onMouseEnter={e => (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.16)'}
          onMouseLeave={e => (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.08)'}
        >
          {/* Art placeholder */}
          <div style={{
            width: '100%', paddingBottom: '100%', position: 'relative',
            background: '#111',
          }}>
            {a.artwork_url ? (
              <img src={a.artwork_url} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: 'rgba(255,255,255,0.08)' }}>♪</div>
            )}
          </div>
          <div style={{ padding: '7px 8px 9px' }}>
            <div style={{ fontSize: 9, fontWeight: 500, color: 'rgba(255,255,255,0.82)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', letterSpacing: '-0.2px' }}>{a.name}</div>
            {a.date && <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.28)', marginTop: 2 }}>{String(a.date).slice(0, 4)}</div>}
          </div>
        </button>
      ))}
    </div>
  )
}

function TrackList({ tracks, currentUri, onAddToPlaylist, headerInfo }: {
  tracks: Track[]; currentUri?: string
  onAddToPlaylist?: (t: Track | Track[]) => void
  headerInfo?: { album: string; artist: string }
}) {
  const [menu, setMenu] = useState<string | null>(null)

  return (
    <div className="fade-in">
      {headerInfo && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 500, color: 'rgba(255,255,255,0.90)', letterSpacing: '-0.3px' }}>{headerInfo.album}</div>
            <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>{headerInfo.artist} · {tracks.length} tracks</div>
          </div>
          <button className="touch-sw touch-sw-green" style={{ height: 24, padding: '0 10px', gap: 5, borderRadius: 4, fontSize: 0 }}
            onClick={async () => {
              await api.queue.clear()
              for (const t of tracks) await api.queue.add(t.uri, false, false, {
                title: t.title,
                artist: t.artist,
                album: t.album,
                artwork_url: t.artwork_url,
              })
              await api.playback.play()
            }}>
            <span className="led-green" style={{ fontSize: 9 }}>▶</span>
            <span className="engraved" style={{ fontSize: 7, color: 'rgba(34,197,94,0.65)', letterSpacing: '1px' }}>PLAY ALL</span>
          </button>
        </div>
      )}
      {tracks.map((t, i) => {
        const playing = t.uri === currentUri
        return (
          <div key={t.id} className={`track-row${playing ? ' track-row-playing' : ''}`}
            onDoubleClick={() => api.queue.add(t.uri, true, false, {
              title: t.title,
              artist: t.artist,
              album: t.album,
              artwork_url: t.artwork_url,
            })}
          >
            <div style={{ width: 18, textAlign: 'right', flexShrink: 0, fontSize: 8, color: playing ? 'var(--color-green)' : 'rgba(255,255,255,0.22)', fontVariantNumeric: 'tabular-nums' }}>
              {playing ? <span className="led-green">▶</span> : (t.track_number ?? i + 1)}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 500, letterSpacing: '-0.3px', color: playing ? 'var(--color-green)' : 'rgba(255,255,255,0.88)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {playing ? <span className="led-green">{t.title}</span> : t.title}
              </div>
              <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.32)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.artist}</div>
            </div>
            <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.25)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{formatDuration(t.duration)}</div>
            <div style={{ position: 'relative', flexShrink: 0 }}>
              <button className="touch-sw" style={{ width: 20, height: 20, borderRadius: 3, fontSize: 11, color: 'rgba(255,255,255,0.22)' }}
                onClick={e => { e.stopPropagation(); setMenu(menu === t.id ? null : t.id) }}>⋯</button>
              {menu === t.id && (
                <>
                  <div style={{ position: 'fixed', inset: 0, zIndex: 200 }} onClick={() => setMenu(null)} />
                  <div style={{
                    position: 'absolute', right: 0, top: '100%', zIndex: 201,
                    background: 'var(--alum-panel-bg)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: 5, overflow: 'hidden', minWidth: 130,
                    boxShadow: '0 8px 24px rgba(0,0,0,0.8)',
                  }}>
                    {[
                      { l: 'Play Now',     f: () => { api.queue.add(t.uri, true, false, {
                        title: t.title,
                        artist: t.artist,
                        album: t.album,
                        artwork_url: t.artwork_url,
                      }); setMenu(null) } },
                      { l: 'Play Next',    f: () => { api.queue.add(t.uri, false, true, {
                        title: t.title,
                        artist: t.artist,
                        album: t.album,
                        artwork_url: t.artwork_url,
                      }); setMenu(null) } },
                      { l: 'Add to Queue', f: () => { api.queue.add(t.uri, false, false, {
                        title: t.title,
                        artist: t.artist,
                        album: t.album,
                        artwork_url: t.artwork_url,
                      }); setMenu(null) } },
                      { l: 'Add to Playlist…', f: () => { onAddToPlaylist?.(t); setMenu(null) } },
                    ].map(item => (
                      <button key={item.l} onClick={item.f} style={{
                        display: 'block', width: '100%', textAlign: 'left',
                        padding: '8px 12px', background: 'none', border: 'none',
                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                        color: 'rgba(255,255,255,0.55)', fontSize: 9, cursor: 'pointer',
                      }}
                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'none'}
                      >{item.l}</button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Empty({ icon, msg }: { icon: string; msg: string }) {
  return (
    <div style={{ padding: '40px 24px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div style={{ fontSize: 26, opacity: 0.3 }}>{icon}</div>
      <div className="engraved">{msg}</div>
    </div>
  )
}

export function LibraryView({ currentUri, onAddToPlaylist }: Props) {
  type Mode = 'artists' | 'albums' | 'tracks' | 'search'
  const [mode, setMode]       = useState<Mode>('artists')
  const [artists, setArtists] = useState<string[]>([])
  const [albums, setAlbums]   = useState<AlbumInfo[]>([])
  const [tracks, setTracks]   = useState<Track[]>([])
  const [selArtist, setSelArtist] = useState<string | null>(null)
  const [selAlbum, setSelAlbum]   = useState<AlbumInfo | null>(null)
  const [q, setQ]             = useState('')
  const [searchRes, setSearchRes] = useState<Track[]>([])
  const [loading, setLoading] = useState(false)
  const [stats, setStats]     = useState<{ artists: number; albums: number; songs: number } | null>(null)

  useEffect(() => {
    api.library.stats().then(setStats).catch(() => {})
    loadArtists()
  }, [])

  const loadArtists = async () => {
    setLoading(true)
    try { const d = await api.library.artists(); setArtists(d.artists ?? []) } catch {}
    setLoading(false)
  }

  const pickArtist = async (name: string) => {
    setSelArtist(name); setMode('albums'); setLoading(true)
    try { const d = await api.library.albumsByArtist(name); setAlbums(d.albums ?? []) } catch {}
    setLoading(false)
  }

  const pickAlbum = async (a: AlbumInfo) => {
    setSelAlbum(a); setMode('tracks'); setLoading(true)
    try { const d = await api.library.tracksByAlbum(a.name, selArtist ?? undefined); setTracks(d.tracks ?? []) } catch {}
    setLoading(false)
  }

  const doSearch = useCallback(async (sq: string) => {
    if (!sq.trim()) { setMode('artists'); return }
    setMode('search'); setLoading(true)
    try { const d = await api.library.search(sq); setSearchRes(d.tracks ?? []) } catch {}
    setLoading(false)
  }, [])

  useEffect(() => {
    const t = setTimeout(() => { if (q) doSearch(q); else if (mode === 'search') setMode('artists') }, 320)
    return () => clearTimeout(t)
  }, [q, doSearch])

  const crumbs = [
    { label: 'Library', onClick: () => { setMode('artists'); setSelArtist(null); setSelAlbum(null) } },
    ...(selArtist ? [{ label: selArtist, onClick: () => { setMode('albums'); setSelAlbum(null) } }] : []),
    ...(selAlbum ? [{ label: selAlbum.name, onClick: () => {} }] : []),
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Search slot */}
      <div style={{ padding: '9px 12px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div className="slot" style={{
          display: 'flex', alignItems: 'center', gap: 8,
          borderRadius: 4, padding: '5px 10px',
        }}>
          <span style={{ color: 'rgba(255,255,255,0.18)', fontSize: 10 }}>🔍</span>
          <input type="text" placeholder="Search library…" value={q} onChange={e => setQ(e.target.value)}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              fontSize: 10, color: 'rgba(255,255,255,0.60)', caretColor: 'var(--color-green)',
            }}
          />
          {q && <button onClick={() => { setQ(''); setMode('artists') }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.22)', fontSize: 11, lineHeight: 1 }}>✕</button>}
        </div>
      </div>

      {/* Stats */}
      {stats && mode === 'artists' && !q && (
        <div style={{ display: 'flex', gap: 14, padding: '5px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
          {[['ARTISTS', stats.artists], ['ALBUMS', stats.albums], ['TRACKS', stats.songs]].map(([l, v]) => (
            <div key={l as string} style={{ display: 'flex', gap: 4, alignItems: 'baseline' }}>
              <span className="engraved">{l}</span>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.40)', fontVariantNumeric: 'tabular-nums' }}>{(v as number).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}

      {/* Breadcrumb */}
      {mode !== 'artists' && mode !== 'search' && <Breadcrumb crumbs={crumbs} />}

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && <div style={{ padding: 24, textAlign: 'center' }}><span className="engraved">Loading…</span></div>}

        {!loading && mode === 'artists' && (
          <div className="fade-in">
            {artists.length === 0
              ? <Empty icon="♪" msg="Library empty — mount drive and run mpc update" />
              : artists.map(a => <ArtistRow key={a} name={a} onClick={() => pickArtist(a)} />)
            }
          </div>
        )}

        {!loading && mode === 'albums' && (
          <AlbumGrid albums={albums} onSelect={pickAlbum} />
        )}

        {!loading && mode === 'tracks' && (
          <TrackList
            tracks={tracks} currentUri={currentUri} onAddToPlaylist={onAddToPlaylist}
            headerInfo={selAlbum && selArtist ? { album: selAlbum.name, artist: selArtist } : undefined}
          />
        )}

        {!loading && mode === 'search' && (
          <div className="fade-in">
            <SectionHdr>{searchRes.length} results for "{q}"</SectionHdr>
            {searchRes.length === 0
              ? <Empty icon="🔍" msg="No results" />
              : <TrackList tracks={searchRes} currentUri={currentUri} onAddToPlaylist={onAddToPlaylist} />
            }
          </div>
        )}
      </div>
    </div>
  )
}
