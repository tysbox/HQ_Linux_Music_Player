'use client'
import { useState, useEffect, useCallback } from 'react'
import { Track } from '@/lib/types'
import { upnpApi, ServerId, UPnPServer, UPnPContainer } from '@/lib/upnpApi'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

interface Props {
  currentUri?: string
  onAddToPlaylist?: (t: Track | Track[]) => void
}

export function SoundgenicView({ currentUri, onAddToPlaylist }: Props) {
  const [servers, setServers]         = useState<UPnPServer[]>([])
  const [activeServer, setActiveServer] = useState<ServerId>('soundgenic')
  const [containers, setContainers]   = useState<UPnPContainer[]>([])
  const [tracks, setTracks]           = useState<Track[]>([])
  const [loading, setLoading]         = useState(false)
  const [q, setQ]                     = useState('')
  const [searchRes, setSearchRes]     = useState<Track[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [breadcrumbs, setBreadcrumbs] = useState<{ label: string; onClick: () => void }[]>([])
  const [menu, setMenu]               = useState<string | null>(null)

  useEffect(() => {
    upnpApi.servers().then(d => setServers(d.servers)).catch(() => {
      setServers([
        { id: 'soundgenic', name: 'Soundgenic', ip: '192.168.0.116', reachable: false },
        { id: 'asset',      name: 'Asset UPnP', ip: '192.168.0.153', reachable: false },
      ])
    })
  }, [])

  const browseRoot = useCallback(async (sid: ServerId = activeServer) => {
    setLoading(true); setIsSearching(false); setQ('')
    const rootCrumb = { label: sid === 'soundgenic' ? 'Soundgenic' : 'Asset UPnP', onClick: () => browseRoot(sid) }
    setBreadcrumbs([rootCrumb])
    try { const d = await upnpApi.browse('0', sid); setContainers(d.containers); setTracks(d.tracks) }
    catch { setContainers([]); setTracks([]) }
    setLoading(false)
  }, [activeServer])

  useEffect(() => { browseRoot(activeServer) }, [activeServer])

  const browseContainer = async (c: UPnPContainer, parentCrumbs: typeof breadcrumbs) => {
    setLoading(true); setIsSearching(false)
    const newCrumbs = [...parentCrumbs, { label: c.title, onClick: () => browseContainer(c, parentCrumbs) }]
    setBreadcrumbs(newCrumbs)
    try { const d = await upnpApi.browse(c.id, activeServer); setContainers(d.containers); setTracks(d.tracks) }
    catch { setContainers([]); setTracks([]) }
    setLoading(false)
  }

  useEffect(() => {
    const t = setTimeout(async () => {
      if (!q.trim()) { setIsSearching(false); return }
      setIsSearching(true); setLoading(true)
      try { const d = await upnpApi.search(q, activeServer); setSearchRes(d.tracks) }
      catch { setSearchRes([]) }
      setLoading(false)
    }, 400)
    return () => clearTimeout(t)
  }, [q, activeServer])

  const playAll = async (tl: Track[]) => {
    await api.queue.clear()
    for (const t of tl) await api.queue.add(t.uri, false, false, {
      title: t.title,
      artist: t.artist,
      album: t.album,
      artwork_url: t.artwork_url,
    })
    await api.playback.play()
  }

  const activeInfo = servers.find(s => s.id === activeServer)
  const isOffline  = activeInfo ? !activeInfo.reachable : false

  const TrackRow = ({ track, index }: { track: Track; index: number }) => {
    const playing = track.uri === currentUri
    return (
      <div className={`track-row${playing ? ' track-row-playing' : ''}`}
        onDoubleClick={() => api.queue.add(track.uri, true, false, {
        title: track.title,
        artist: track.artist,
        album: track.album,
        artwork_url: track.artwork_url,
      })}>
        <div style={{ width: 18, textAlign: 'right', flexShrink: 0, fontSize: 8, color: playing ? 'var(--color-green)' : 'rgba(255,255,255,0.22)', fontVariantNumeric: 'tabular-nums' }}>
          {playing ? <span className="led-green">▶</span> : (track.track_number ?? index + 1)}
        </div>
        {track.artwork_url && (
          <img src={track.artwork_url} alt="" style={{ width: 26, height: 26, borderRadius: 3, objectFit: 'cover', flexShrink: 0, border: '1px solid rgba(255,255,255,0.07)' }} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 10, fontWeight: 500, letterSpacing: '-0.3px', color: playing ? 'var(--color-green)' : 'rgba(255,255,255,0.88)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {playing ? <span className="led-green">{track.title}</span> : track.title}
          </div>
          <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.32)', marginTop: 1 }}>{track.artist}</div>
        </div>
        <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.25)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{formatDuration(track.duration)}</div>
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <button className="touch-sw" style={{ width: 20, height: 20, borderRadius: 3, fontSize: 11, color: 'rgba(255,255,255,0.22)' }}
            onClick={e => { e.stopPropagation(); setMenu(menu === track.id ? null : track.id) }}>⋯</button>
          {menu === track.id && (
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
                  { l: 'Play Now',     f: () => { api.queue.add(track.uri, true, false, {
                        title: track.title,
                        artist: track.artist,
                        album: track.album,
                        artwork_url: track.artwork_url,
                      }); setMenu(null) } },
                  { l: 'Play Next',    f: () => { api.queue.add(track.uri, false, true, {
                        title: track.title,
                        artist: track.artist,
                        album: track.album,
                        artwork_url: track.artwork_url,
                      }); setMenu(null) } },
                  { l: 'Add to Queue', f: () => { api.queue.add(track.uri, false, false, {
                        title: track.title,
                        artist: track.artist,
                        album: track.album,
                        artwork_url: track.artwork_url,
                      }); setMenu(null) } },
                  { l: 'Add to Playlist…', f: () => { onAddToPlaylist?.(track); setMenu(null) } },
                ].map(item => (
                  <button key={item.l} onClick={item.f} style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '10px 12px', background: 'none', border: 'none',
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
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* Server toggle switches */}
      {servers.length > 0 && (
        <div className="alum-panel" style={{
          display: 'flex', flexDirection: 'column', gap: 8,
          padding: '11px 14px',
          border: 'none', borderBottom: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 0, boxShadow: 'none',
        }}>
          <span className="engraved">UPnP Servers</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {servers.map(srv => (
              <div key={srv.id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}
                onClick={() => setActiveServer(srv.id as ServerId)}>
                <div className={`toggle-sw${activeServer === srv.id ? ' toggle-on' : ''}`} style={{ cursor: 'pointer' }}>
                  <div className="toggle-sw-thumb" />
                </div>
                <span className={`ind-dot ${srv.reachable ? 'ind-green' : ''}`} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 9, fontWeight: 500,
                    ...(activeServer === srv.id && srv.reachable
                      ? {} : { color: srv.reachable ? 'rgba(255,255,255,0.65)' : 'rgba(255,255,255,0.28)' }),
                  }}>
                    {activeServer === srv.id && srv.reachable
                      ? <span className="led-green">{srv.name}</span>
                      : srv.name
                    }
                  </div>
                  <div style={{ fontSize: 7, color: 'rgba(255,255,255,0.20)' }}>{srv.ip}{!srv.reachable ? ' — Offline' : ''}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Search slot */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div className="slot" style={{ display: 'flex', alignItems: 'center', gap: 8, borderRadius: 4, padding: '7px 10px' }}>
          <span style={{ color: 'rgba(255,255,255,0.18)', fontSize: 10 }}>🔍</span>
          <input type="text" placeholder={`Search ${activeInfo?.name ?? 'server'}…`} value={q}
            onChange={e => setQ(e.target.value)}
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 10, color: 'rgba(255,255,255,0.60)', caretColor: 'var(--color-green)' }}
          />
          {q && <button onClick={() => { setQ(''); setIsSearching(false) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.22)', fontSize: 11, lineHeight: 1 }}>✕</button>}
        </div>
      </div>

      {/* Breadcrumb */}
      {!isSearching && breadcrumbs.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)', flexWrap: 'wrap' }}>
          {breadcrumbs.map((c, i) => (
            <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {i > 0 && <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 8 }}>›</span>}
              <button onClick={c.onClick} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 9, color: i === breadcrumbs.length - 1 ? 'rgba(255,255,255,0.55)' : 'rgba(255,255,255,0.28)', padding: '1px 0' }}>{c.label}</button>
            </span>
          ))}
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && <div style={{ padding: 24, textAlign: 'center' }}><span className="engraved">Loading…</span></div>}

        {!loading && isOffline && (
          <div style={{ padding: '40px 24px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <div style={{ fontSize: 24, opacity: 0.2 }}>📡</div>
            <span className="engraved">{activeInfo?.name} is offline</span>
          </div>
        )}

        {/* Search results */}
        {!loading && isSearching && (
          <div className="fade-in">
            <div style={{ padding: '9px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <span className="engraved">{searchRes.length} results for "{q}"</span>
            </div>
            {searchRes.map((t, i) => <TrackRow key={t.id} track={t} index={i} />)}
          </div>
        )}

        {/* Browse results */}
        {!loading && !isSearching && !isOffline && (
          <div className="fade-in">
            {/* Containers */}
            {containers.map(c => (
              <button key={c.id} onClick={() => browseContainer(c, breadcrumbs)} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                width: '100%', textAlign: 'left',
                padding: '11px 14px', background: 'none', border: 'none',
                borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'pointer',
              }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.18)', flexShrink: 0 }}>📁</span>
                  <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.75)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  {c.child_count && c.child_count !== '?' && <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.22)' }}>{c.child_count}</span>}
                  <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.18)' }}>›</span>
                </div>
              </button>
            ))}

            {/* Track section header */}
            {tracks.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.05)', borderTop: containers.length > 0 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                <span className="engraved">{tracks.length} tracks</span>
                {containers.length === 0 && (
                  <button className="touch-sw touch-sw-green" style={{ height: 22, padding: '0 10px', gap: 5, borderRadius: 4 }}
                    onClick={() => playAll(tracks)}>
                    <span className="led-green" style={{ fontSize: 9 }}>▶</span>
                    <span className="engraved" style={{ fontSize: 7, color: 'rgba(34,197,94,0.65)', letterSpacing: '1px' }}>PLAY ALL</span>
                  </button>
                )}
              </div>
            )}

            {tracks.map((t, i) => <TrackRow key={t.id} track={t} index={i} />)}

            {containers.length === 0 && tracks.length === 0 && (
              <div style={{ padding: '40px 24px', textAlign: 'center' }}><span className="engraved">Empty</span></div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
