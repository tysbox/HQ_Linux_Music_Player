'use client'
import { useState, useEffect, useCallback } from 'react'
import { Track } from '@/lib/types'
import { upnpApi, ServerId, UPnPServer, UPnPContainer } from '@/lib/upnpApi'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

interface Props {
  currentUri?: string
  onAddToPlaylist?: (tracks: Track | Track[]) => void
}

// ── サーバー選択タブ ──────────────────────────────────────────
function ServerTabs({ servers, active, onChange }: {
  servers: UPnPServer[]
  active: ServerId
  onChange: (id: ServerId) => void
}) {
  return (
    <div style={{
      display: 'flex',
      borderBottom: '1px solid var(--color-border-subtle)',
      background: 'var(--color-surface-panel)',
      flexShrink: 0,
    }}>
      {servers.map(srv => (
        <button
          key={srv.id}
          onClick={() => onChange(srv.id as ServerId)}
          style={{
            flex: 1,
            padding: '8px 4px',
            background: 'none',
            border: 'none',
            borderBottom: active === srv.id
              ? '2px solid var(--color-blue)'
              : '2px solid transparent',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 2,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{
              width: 5, height: 5,
              borderRadius: '9999px',
              background: srv.reachable ? 'var(--color-green)' : 'var(--color-red)',
              flexShrink: 0,
            }} />
            <span style={{
              fontSize: 'var(--fs-sm)',
              color: active === srv.id
                ? 'var(--color-blue-text)'
                : 'var(--color-text-inactive)',
              letterSpacing: 'var(--ls-label)',
            }}>
              {srv.name}
            </span>
          </div>
          <span style={{
            fontSize: 'var(--fs-2xs)',
            color: 'var(--color-text-hint)',
            letterSpacing: 0,
          }}>
            {srv.ip}
          </span>
        </button>
      ))}
    </div>
  )
}

// ── パンくず ──────────────────────────────────────────────────
function Breadcrumb({ crumbs }: { crumbs: { label: string; onClick: () => void }[] }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 4,
      padding: '7px 12px',
      borderBottom: '1px solid var(--color-border-subtle)',
      flexWrap: 'wrap', flexShrink: 0,
    }}>
      {crumbs.map((c, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {i > 0 && (
            <span style={{ color: 'var(--color-text-disabled)', fontSize: 'var(--fs-xs)' }}>›</span>
          )}
          <button onClick={c.onClick} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 'var(--fs-sm)',
            color: i === crumbs.length - 1
              ? 'var(--color-text-tertiary)'
              : 'var(--color-text-muted)',
            padding: '1px 0',
          }}>
            {c.label}
          </button>
        </span>
      ))}
    </div>
  )
}

// ── コンテナ行 ────────────────────────────────────────────────
function ContainerRow({ item, onClick }: { item: UPnPContainer; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      width: '100%', textAlign: 'left',
      padding: '9px 12px', background: 'none', border: 'none',
      borderBottom: '1px solid var(--color-border-subtle)',
      cursor: 'pointer', transition: 'background 0.1s',
    }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--color-surface-card)'}
      onMouseLeave={e => e.currentTarget.style.background = 'none'}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{ fontSize: 11, color: 'var(--color-text-disabled)', flexShrink: 0 }}>📁</span>
        <span style={{
          fontSize: 'var(--fs-base)', color: 'var(--color-text-secondary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {item.title}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        {item.child_count && item.child_count !== '?' && (
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)' }}>
            {item.child_count}
          </span>
        )}
        <span style={{ color: 'var(--color-text-disabled)', fontSize: 'var(--fs-sm)' }}>›</span>
      </div>
    </button>
  )
}

// ── トラック行 ────────────────────────────────────────────────
function UPnPTrackRow({ track, index, isCurrent, onAddToPlaylist }: {
  track: Track; index: number; isCurrent: boolean
  onAddToPlaylist?: (t: Track) => void
}) {
  const [feedback, setFeedback] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  // Pass track metadata so the queue display can show proper titles for HTTP streams
  const meta = { title: track.title, artist: track.artist, album: track.album, artwork_url: track.artwork_url }

  const act = async (action: 'play' | 'next' | 'queue' | 'playlist') => {
    setMenuOpen(false)
    try {
      if (action === 'play')     { await api.queue.add(track.uri, true, false, meta);      setFeedback('▶') }
      if (action === 'next')     { await api.queue.add(track.uri, false, true, meta);      setFeedback('Next') }
      if (action === 'queue')    { await api.queue.add(track.uri, false, false, meta);     setFeedback('+Q') }
      if (action === 'playlist') { onAddToPlaylist?.(track) }
      setTimeout(() => setFeedback(null), 1500)
    } catch {}
  }

  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '7px 12px',
        background: isCurrent ? 'var(--color-green-bg)' : 'transparent',
        borderLeft: isCurrent ? '2px solid var(--color-green)' : '2px solid transparent',
        borderBottom: '1px solid var(--color-border-subtle)',
        cursor: 'pointer', transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (!isCurrent) e.currentTarget.style.background = 'var(--color-surface-card)' }}
      onMouseLeave={e => { if (!isCurrent) e.currentTarget.style.background = 'transparent' }}
      onDoubleClick={() => act('play')}
    >
      <div style={{
        width: 20, textAlign: 'right', flexShrink: 0,
        fontSize: 'var(--fs-xs)',
        color: isCurrent ? 'var(--color-green)' : 'var(--color-text-disabled)',
        fontVariantNumeric: 'tabular-nums',
      }}>
        {isCurrent ? '▶' : (track.track_number ?? index + 1)}
      </div>

      {/* アートワーク（UPnPトラックはartwork_urlを持つ） */}
      {track.artwork_url && (
        <img
          src={track.artwork_url} alt=""
          style={{
            width: 28, height: 28,
            borderRadius: 'var(--radius-sm)',
            objectFit: 'cover', flexShrink: 0,
          }}
        />
      )}

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--fs-base)', fontWeight: 'var(--fw-medium)',
          color: isCurrent ? 'var(--color-green)' : 'var(--color-text-primary)',
          letterSpacing: 'var(--ls-title)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{track.title}</div>
        <div style={{
          fontSize: 'var(--fs-xs)', color: 'var(--color-text-muted)', marginTop: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {[
            track.artist && track.artist !== 'Unknown Artist' ? track.artist : null,
            track.album  && track.album  !== 'Unknown Album'  ? track.album  : null,
          ].filter(Boolean).join(' — ')}
        </div>
      </div>

      <div style={{
        fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)',
        fontVariantNumeric: 'tabular-nums', flexShrink: 0,
      }}>
        {feedback
          ? <span style={{ color: 'var(--color-green)' }}>{feedback}</span>
          : formatDuration(track.duration)
        }
      </div>

      <div style={{ position: 'relative', flexShrink: 0 }}>
        <button
          onClick={e => { e.stopPropagation(); setMenuOpen(o => !o) }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--color-text-disabled)', fontSize: 14, padding: '2px 4px',
          }}
        >⋯</button>
        {menuOpen && (
          <>
            <div style={{ position: 'fixed', inset: 0, zIndex: 200 }} onClick={() => setMenuOpen(false)} />
            <div style={{
              position: 'absolute', right: 0, top: '100%', zIndex: 201,
              background: 'var(--color-surface-bar)',
              border: '1px solid var(--color-border-medium)',
              borderRadius: 'var(--radius-md)', overflow: 'hidden',
              minWidth: 140, boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            }}>
              {[
                { label: 'Play Now',         fn: () => act('play') },
                { label: 'Play Next',        fn: () => act('next') },
                { label: 'Add to Queue',     fn: () => act('queue') },
                { label: 'Add to Playlist…', fn: () => act('playlist') },
              ].map(item => (
                <button key={item.label} onClick={item.fn} style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '8px 12px', background: 'none', border: 'none',
                  borderBottom: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-tertiary)',
                  fontSize: 'var(--fs-base)', cursor: 'pointer',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-surface-card)'; e.currentTarget.style.color = 'var(--color-text-primary)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--color-text-tertiary)' }}
                >{item.label}</button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── メインコンポーネント ──────────────────────────────────────
export function SoundgenicView({ currentUri, onAddToPlaylist }: Props) {
  const [servers, setServers]         = useState<UPnPServer[]>([])
  const [activeServer, setActiveServer] = useState<ServerId>('soundgenic')
  const [containers, setContainers]   = useState<UPnPContainer[]>([])
  const [tracks, setTracks]           = useState<Track[]>([])
  const [loading, setLoading]         = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Track[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [breadcrumbs, setBreadcrumbs] = useState<{ label: string; onClick: () => void }[]>([])

  // サーバー一覧取得
  useEffect(() => {
    upnpApi.servers().then(d => setServers(d.servers)).catch(() => {
      setServers([
        { id: 'soundgenic', name: 'Soundgenic', ip: '192.168.0.116', reachable: false },
        { id: 'asset',      name: 'Asset UPnP', ip: '192.168.0.153', reachable: false },
      ])
    })
  }, [])

  // ルートブラウズ
  const browseRoot = useCallback(async (serverId: ServerId = activeServer) => {
    setLoading(true)
    setIsSearching(false)
    setSearchQuery('')
    const serverName = servers.find(s => s.id === serverId)?.name ?? serverId
    const rootCrumb = { label: serverName, onClick: () => browseRoot(serverId) }
    setBreadcrumbs([rootCrumb])
    try {
      const data = await upnpApi.browse('0', serverId)
      setContainers(data.containers)
      setTracks(data.tracks)
    } catch {
      setContainers([]); setTracks([])
    }
    setLoading(false)
  }, [activeServer])

  useEffect(() => { browseRoot(activeServer) }, [activeServer])

  // コンテナブラウズ
  const browseContainer = async (container: UPnPContainer, parentCrumbs: typeof breadcrumbs) => {
    setLoading(true)
    setIsSearching(false)
    const newCrumbs = [
      ...parentCrumbs,
      { label: container.title, onClick: () => browseContainer(container, parentCrumbs) },
    ]
    setBreadcrumbs(newCrumbs)
    try {
      const data = await upnpApi.browse(container.id, activeServer)
      setContainers(data.containers)
      setTracks(data.tracks)
    } catch {
      setContainers([]); setTracks([])
    }
    setLoading(false)
  }

  // 検索
  useEffect(() => {
    const t = setTimeout(async () => {
      if (!searchQuery.trim()) {
        setIsSearching(false)
        return
      }
      setIsSearching(true)
      setLoading(true)
      try {
        const data = await upnpApi.search(searchQuery, activeServer)
        setSearchResults(data.tracks)
      } catch {
        setSearchResults([])
      }
      setLoading(false)
    }, 400)
    return () => clearTimeout(t)
  }, [searchQuery, activeServer])

  const playAll = async (trackList: Track[]) => {
    await api.queue.clear()
    for (const t of trackList) {
      await api.queue.add(t.uri, false, false, {
        title: t.title, artist: t.artist, album: t.album, artwork_url: t.artwork_url,
      })
    }
    await api.playback.play()
  }

  const activeServerInfo = servers.find(s => s.id === activeServer)
  const isOffline = activeServerInfo ? !activeServerInfo.reachable : false

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* サーバー切り替えタブ */}
      {servers.length > 0 && (
        <ServerTabs
          servers={servers}
          active={activeServer}
          onChange={id => setActiveServer(id)}
        />
      )}

      {/* 検索バー */}
      <div style={{
        padding: '10px 12px',
        borderBottom: '1px solid var(--color-border-subtle)',
        background: 'var(--color-surface-panel)',
        flexShrink: 0,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--color-surface-card)',
          border: '1px solid var(--color-border-input)',
          borderRadius: 'var(--radius-md)', padding: '6px 10px',
        }}>
          <span style={{ color: 'var(--color-text-disabled)', fontSize: 12 }}>🔍</span>
          <input
            type="text"
            placeholder={`Search ${activeServerInfo?.name ?? 'server'}…`}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              fontSize: 'var(--fs-base)', color: 'var(--color-text-input)',
              caretColor: 'var(--color-green)',
            }}
          />
          {searchQuery && (
            <button onClick={() => { setSearchQuery(''); setIsSearching(false) }} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--color-text-disabled)', fontSize: 12,
            }}>✕</button>
          )}
        </div>
      </div>

      {/* パンくず（検索中は非表示） */}
      {!isSearching && breadcrumbs.length > 0 && (
        <Breadcrumb crumbs={breadcrumbs} />
      )}

      {/* コンテンツ */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-disabled)' }}>
            Loading…
          </div>
        )}

        {!loading && isOffline && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: '48px 24px', gap: 8, textAlign: 'center',
          }}>
            <div style={{ fontSize: 28 }}>📡</div>
            <div style={{ fontSize: 'var(--fs-base)', color: 'var(--color-text-tertiary)' }}>
              {activeServerInfo?.name} is offline
            </div>
            <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)' }}>
              {activeServerInfo?.ip} が応答していません
            </div>
          </div>
        )}

        {/* 検索結果 */}
        {!loading && isSearching && (
          <div className="fade-in">
            <div style={{
              padding: '7px 12px', fontSize: 'var(--fs-xs)',
              letterSpacing: 'var(--ls-label)', textTransform: 'uppercase',
              color: 'var(--color-text-disabled)',
              borderBottom: '1px solid var(--color-border-subtle)',
            }}>
              {searchResults.length} results for "{searchQuery}"
            </div>
            {searchResults.map((t, i) => (
              <UPnPTrackRow key={t.id} track={t} index={i}
                isCurrent={t.uri === currentUri} onAddToPlaylist={onAddToPlaylist} />
            ))}
          </div>
        )}

        {/* ブラウズ結果 */}
        {!loading && !isSearching && !isOffline && (
          <div className="fade-in">
            {/* コンテナ（フォルダ）*/}
            {containers.map(c => (
              <ContainerRow key={c.id} item={c}
                onClick={() => browseContainer(c, breadcrumbs)} />
            ))}

            {/* トラック一覧ヘッダー（コンテナと混在する場合） */}
            {containers.length > 0 && tracks.length > 0 && (
              <div style={{
                padding: '6px 12px',
                fontSize: 'var(--fs-xs)', letterSpacing: 'var(--ls-label)',
                textTransform: 'uppercase', color: 'var(--color-text-disabled)',
                borderBottom: '1px solid var(--color-border-subtle)',
                borderTop: '1px solid var(--color-border-subtle)',
              }}>Tracks in this folder</div>
            )}

            {/* トラックのみの場合はPlay Allを表示 */}
            {tracks.length > 0 && containers.length === 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '9px 12px',
                borderBottom: '1px solid var(--color-border-subtle)',
              }}>
                <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)' }}>
                  {tracks.length} tracks
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={() => playAll(tracks)} style={{
                    background: 'var(--color-green-bg)',
                    border: '1px solid var(--color-green-border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--color-green)',
                    fontSize: 'var(--fs-xs)',
                    letterSpacing: 'var(--ls-button)',
                    textTransform: 'uppercase',
                    padding: '4px 10px', cursor: 'pointer',
                  }}>▶ Play All</button>
                  <button onClick={() => onAddToPlaylist?.(tracks)} style={{
                    background: 'none',
                    border: '1px solid var(--color-border-medium)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--color-text-tertiary)',
                    fontSize: 'var(--fs-xs)',
                    letterSpacing: 'var(--ls-button)',
                    textTransform: 'uppercase',
                    padding: '4px 10px', cursor: 'pointer',
                  }}>+ Playlist</button>
                </div>
              </div>
            )}

            {tracks.map((t, i) => (
              <UPnPTrackRow key={t.id} track={t} index={i}
                isCurrent={t.uri === currentUri} onAddToPlaylist={onAddToPlaylist} />
            ))}

            {containers.length === 0 && tracks.length === 0 && (
              <div style={{
                padding: '48px 24px', textAlign: 'center',
                color: 'var(--color-text-disabled)', fontSize: 'var(--fs-base)',
              }}>
                Empty
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
