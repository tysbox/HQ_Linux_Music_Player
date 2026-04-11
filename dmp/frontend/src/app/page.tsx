'use client'
import { useState, useEffect, useRef, useCallback } from 'react'
import { usePlaybackStatus } from '@/hooks/usePlaybackStatus'
import { LibraryView }       from '@/components/LibraryView'
import { QueueView }         from '@/components/QueueView'
import { HistoryView }       from '@/components/HistoryView'
import { PlaylistsView }     from '@/components/PlaylistsView'
import { SoundgenicView }    from '@/components/SoundgenicView'
import { AddToPlaylistModal } from '@/components/AddToPlaylistModal'
import { api }               from '@/lib/api'
import { Track }             from '@/lib/types'
import { formatDuration }    from '@/lib/utils'

type Tab = 'library' | 'soundgenic' | 'queue' | 'history' | 'playlists'

// ─── Sub-components defined OUTSIDE main component ───────────────────────────

// ── WS indicator dot ─────────────────────────────────────────────────────────
function WsDot({ state }: { state: 'connecting' | 'connected' | 'disconnected' }) {
  const cls =
    state === 'connected'    ? 'ind-dot ind-green' :
    state === 'connecting'   ? 'ind-dot ind-amber pulse-led' :
                               'ind-dot ind-red'
  return <span className={cls} />
}

// ── Progress bar (range input styled as slot) ─────────────────────────────────
function ProgressSlot({ position, duration, onSeek }: {
  position: number; duration: number; onSeek: (s: number) => void
}) {
  const pct = duration > 0 ? Math.min((position / duration) * 100, 100) : 0
  return (
    <div style={{ position: 'relative', height: 4 }}>
      <div className="slot-progress">
        <div className="slot-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <input
        type="range" min={0} max={duration || 1} value={position} step={1}
        onChange={e => onSeek(Number(e.target.value))}
        style={{
          position: 'absolute', inset: 0,
          width: '100%', height: '100%',
          opacity: 0, cursor: 'pointer', margin: 0,
        }}
      />
    </div>
  )
}

// ── Transport button (touch switch) ──────────────────────────────────────────
function TBtn({ onClick, children, active = false, large = false }: {
  onClick: () => void; children: React.ReactNode; active?: boolean; large?: boolean
}) {
  const cls = `touch-sw${active ? ' touch-sw-green' : ''}`
  return (
    <button onClick={onClick} className={cls} style={{
      width: large ? 42 : 32,
      height: large ? 34 : 28,
      borderRadius: large ? 6 : 4,
      fontSize: large ? 17 : 12,
    }}>
      {children}
    </button>
  )
}

// ── Machined tab switch ───────────────────────────────────────────────────────
function TabSw({ tab, isActive, onClick, badge }: {
  tab: { id: Tab; label: string; sym: string }
  isActive: boolean; onClick: () => void; badge?: number
}) {
  const cls = `touch-sw${isActive ? (tab.id === 'soundgenic' ? ' touch-sw-blue' : ' touch-sw-green') : ''}`
  return (
    <button onClick={onClick} className={cls} style={{
      flex: 1, height: 36,
      flexDirection: 'column', gap: 2,
      borderRadius: 0,
      position: 'relative',
    }}>
      <span style={{
        fontSize: 11,
        color: isActive
          ? tab.id === 'soundgenic' ? 'var(--color-blue)' : 'var(--color-green)'
          : 'rgba(255,255,255,0.28)',
        lineHeight: 1,
      }}>{tab.sym}</span>
      <span className="engraved" style={{
        fontSize: 6, letterSpacing: '1.2px',
        color: isActive
          ? tab.id === 'soundgenic' ? 'rgba(59,130,246,0.65)' : 'rgba(34,197,94,0.65)'
          : undefined,
      }}>{tab.label}</span>
      {badge !== undefined && badge > 0 && (
        <span style={{
          position: 'absolute', top: 3, right: 4,
          background: 'var(--color-green)', color: '#000',
          fontSize: 6, fontWeight: 700,
          borderRadius: 'var(--radius-full)',
          minWidth: 13, height: 13,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 2px', lineHeight: 1,
        }}>{badge > 99 ? '99+' : badge}</span>
      )}
    </button>
  )
}

// ── Album art bezel ───────────────────────────────────────────────────────────
function ArtBezel({ url }: { url: string | null }) {
  return (
    <div style={{
      width: '100%',
      aspectRatio: '1',
      background: '#fff',
      padding: 4,
      borderRadius: 2,
      boxShadow:
        '0 40px 80px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.4)',
    }}>
      {url ? (
        <img src={url} alt="Album Art"
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
      ) : (
        <div style={{
          width: '100%', height: '100%',
          background: '#111',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <span style={{ fontSize: 48, opacity: 0.12 }}>♪</span>
        </div>
      )}
    </div>
  )
}

// ── LED Status panel (red, matching DAP) ─────────────────────────────────────
function LedStatusPanel({ state, wsState, artist, title, format, position, duration, onSeek }: {
  state: string; wsState: string; artist: string; title: string; format: string
  position: number; duration: number; onSeek: (s: number) => void
}) {
  const connected = wsState === 'connected'
  const connecting = wsState === 'connecting'
  const connLabel = connected ? 'MPD CONNECTED' : connecting ? 'CONNECTING…' : 'DISCONNECTED'

  return (
    <div style={{
      width: '100%',
      background: 'rgba(0,0,0,0.92)',
      border: '2px solid rgba(255,255,255,0.05)',
      borderRadius: 2,
      padding: '10px 14px',
      display: 'flex', flexDirection: 'column', gap: 7,
      boxShadow: 'inset 0 0 24px rgba(0,0,0,1), 0 0 20px rgba(0,0,0,0.5)',
    }}>
      {/* Status row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span className={`ind-dot ${connected ? 'ind-green' : connecting ? 'ind-amber pulse-led' : 'ind-red'}`} />
          <span className={`led-${connected ? 'green' : connecting ? 'amber' : 'red'}`} style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.20em',
            textTransform: 'uppercase', fontFamily: 'var(--font-mono)',
          }}>
            {connLabel}
          </span>
        </div>
        {format && (
          <span className="led-red" style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
            fontFamily: 'var(--font-mono)',
          }}>{format}</span>
        )}
      </div>

      <div style={{ height: 1, background: 'rgba(139,0,0,0.30)' }} />

      {/* Track info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <span className="led-red" style={{
          fontSize: 11, fontWeight: 900, letterSpacing: '0.15em',
          textTransform: 'uppercase', fontFamily: 'var(--font-mono)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          flex: 1,
        }}>
          {artist || title ? `${artist ? `${artist} — ` : ''}${title}` : 'NOT PLAYING'}
        </span>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.10em',
          fontFamily: 'var(--font-mono)', color: 'rgba(220,38,38,0.65)',
          flexShrink: 0,
        }}>
          {formatDuration(position)} / {formatDuration(duration) || '--:--'}
        </span>
      </div>

      {/* Progress */}
      <div style={{ height: 4, background: 'rgba(139,0,0,0.18)', borderRadius: 2, overflow: 'hidden', cursor: 'pointer' }}>
        <div style={{
          height: '100%',
          width: `${duration > 0 ? Math.min((position / duration) * 100, 100) : 0}%`,
          background: 'rgba(220,38,38,0.65)',
          borderRadius: 2,
          transition: 'width 1s linear',
        }} />
      </div>
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function DmpPage() {
  const { status, wsState } = usePlaybackStatus()
  const [activeTab, setActiveTab]       = useState<Tab>('library')
  const [artworkUrl, setArtworkUrl]     = useState<string | null>(null)
  const [playlistTarget, setPlaylistTarget] = useState<Track[] | null>(null)
  const [mounted, setMounted]           = useState(false)

  useEffect(() => { setMounted(true) }, [])

  // Fix 2: artwork priority — UPnP has artwork_url, local uses MPD readpicture
  useEffect(() => {
    const track = status.current_track
    if (!track) { setArtworkUrl(null); return }
    if (track.artwork_url) {
      setArtworkUrl(track.artwork_url)
    } else {
      setArtworkUrl(api.library.artworkUrl(track.uri))
    }
  }, [status.current_track])

  const handlePlayPause = () => {
    status.state === 'play' ? api.playback.pause() : api.playback.play()
  }

  const handleAddToPlaylist = (t: Track | Track[]) => {
    setPlaylistTarget(Array.isArray(t) ? t : [t])
  }

  const track = status.current_track
  const artist = track?.artist ?? ''
  const title  = track?.title  ?? ''
  const trackLabel = artist ? `${artist} — ${title}` : title || 'NOT PLAYING'
  // format badge from source
  const format = track?.source === 'upnp' ? 'STREAM' : ''

  const TABS: { id: Tab; label: string; sym: string }[] = [
    { id: 'library',    label: 'LIB',  sym: '♪'  },
    { id: 'soundgenic', label: 'SRV',  sym: '📡' },
    { id: 'queue',      label: 'QUE',  sym: '≡'  },
    { id: 'history',    label: 'HIS',  sym: '⏱' },
    { id: 'playlists',  label: 'LIST', sym: '♥'  },
  ]

  if (!mounted) return null

  return (
    <div style={{
      minHeight: '100dvh',
      background: '#050505',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'flex-start',
      padding: '32px 16px 48px',
      overflowX: 'hidden',
    }}>
      {/* ── Oak outer console frame ── */}
      <div className="oak-frame" style={{
        width: '100%',
        maxWidth: 520,
        borderRadius: 40,
        padding: 10,
      }}>
        {/* ── Brushed silver + dark aluminum inner ── */}
        <div style={{ borderRadius: 32, overflow: 'hidden' }}>

          {/* ═══ TOP SECTION — Brushed Silver (common with DAP) ═══ */}
          <div className="alum-silver" style={{ padding: '28px 24px 20px' }}>

            {/* LED Status Panel */}
            <LedStatusPanel
              state={status.state}
              wsState={wsState}
              artist={artist}
              title={title}
              format={format}
              position={status.position}
              duration={status.duration}
              onSeek={s => api.playback.seek(s)}
            />

            {/* Album Art */}
            <div style={{ margin: '18px 0 18px' }}>
              <ArtBezel url={artworkUrl} />
            </div>

            {/* Transport controls row */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 4,
            }}>
              {/* Shuffle */}
              <TBtn onClick={() => api.playback.toggleRandom()} active={status.random}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/>
                  <polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/>
                </svg>
              </TBtn>

              <div style={{ width: 6 }} />

              {/* ⏮ ▶/⏸ ⏭ */}
              <div style={{ display: 'flex', gap: 2 }}>
                <TBtn onClick={() => api.playback.previous()}>⏮</TBtn>
                <TBtn onClick={handlePlayPause} active={status.state === 'play'} large>
                  {status.state === 'play'
                    ? <span className="led-green" style={{ fontSize: 17 }}>⏸</span>
                    : <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: 17 }}>▶</span>
                  }
                </TBtn>
                <TBtn onClick={() => api.playback.next()}>⏭</TBtn>
              </div>

              <div style={{ width: 6 }} />

              {/* Repeat */}
              <TBtn onClick={() => api.playback.toggleRepeat()} active={status.repeat}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>
                  <polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>
                </svg>
              </TBtn>

              <div style={{ flex: 1 }} />
              <WsDot state={wsState} />
            </div>
          </div>

          {/* ═══ DIVIDER — oak inlay strip ═══ */}
          <div style={{
            height: 8,
            background:
              'repeating-linear-gradient(45deg, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.15) 1.5%, transparent 1.5%, transparent 10%), ' +
              'linear-gradient(135deg, #a68154 0%, #7a5c35 50%, #6e5233 100%)',
            borderTop: '1px solid rgba(180,120,50,0.30)',
            borderBottom: '1px solid rgba(180,120,50,0.30)',
          }} />

          {/* ═══ BOTTOM SECTION — Dark Aluminum (DMP browser) ═══ */}
          <div style={{ background: 'var(--alum-dark-bg)' }}>

            {/* Tab switch row */}
            <div style={{
              display: 'flex',
              borderBottom: '1px solid rgba(255,255,255,0.05)',
            }}>
              {TABS.map(tab => (
                <TabSw
                  key={tab.id}
                  tab={tab}
                  isActive={activeTab === tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  badge={tab.id === 'queue' ? status.queue_length : undefined}
                />
              ))}
            </div>

            {/* Content area */}
            <div style={{
              height: 480,
              overflowY: 'auto',
              overflowX: 'hidden',
            }}>
              {activeTab === 'library' && (
                <LibraryView
                  currentUri={track?.uri}
                  onAddToPlaylist={handleAddToPlaylist}
                />
              )}
              {activeTab === 'soundgenic' && (
                <SoundgenicView
                  currentUri={track?.uri}
                  onAddToPlaylist={handleAddToPlaylist}
                />
              )}
              {activeTab === 'queue'     && <QueueView />}
              {activeTab === 'history'   && <HistoryView />}
              {activeTab === 'playlists' && <PlaylistsView />}
            </div>
          </div>

        </div>
      </div>

      {/* Playlist modal */}
      {playlistTarget && (
        <AddToPlaylistModal
          tracks={playlistTarget}
          onClose={() => setPlaylistTarget(null)}
        />
      )}
    </div>
  )
}
