'use client'
import { useState, useEffect } from 'react'
import { usePlaybackStatus } from '@/hooks/usePlaybackStatus'
import { LibraryView }        from '@/components/LibraryView'
import { QueueView }          from '@/components/QueueView'
import { HistoryView }        from '@/components/HistoryView'
import { PlaylistsView }      from '@/components/PlaylistsView'
import { SoundgenicView }     from '@/components/SoundgenicView'
import { AddToPlaylistModal } from '@/components/AddToPlaylistModal'
import { api }                from '@/lib/api'
import { Track }              from '@/lib/types'
import { formatDuration }     from '@/lib/utils'

type Tab = 'library' | 'soundgenic' | 'queue' | 'history' | 'playlists'

// ─── Sub-components (defined OUTSIDE main — never inside render) ──────────────

// ── Transport button — glass/aluminum round, same as DAP MODE/OUTPUT ──────────
function TBtn({
  onClick, children, active = false,
  size = 'md',
}: {
  onClick: () => void
  children: React.ReactNode
  active?: boolean
  size?: 'sm' | 'md' | 'lg'
}) {
  const dim = size === 'lg' ? 80 : size === 'sm' ? 52 : 64
  return (
    <button
      onClick={onClick}
      className={`transport-btn${active ? ' transport-btn-active' : ''}`}
      style={{ width: dim, height: dim }}
    >
      {children}
    </button>
  )
}

// ── Tab switch button ─────────────────────────────────────────────────────────
function TabSw({
  tab, isActive, onClick, badge,
}: {
  tab: { id: Tab; label: string; sym: string }
  isActive: boolean
  onClick: () => void
  badge?: number
}) {
  const cls = `touch-sw${isActive
    ? tab.id === 'soundgenic' ? ' touch-sw-blue' : ' touch-sw-green'
    : ''}`
  return (
    <button onClick={onClick} className={cls} style={{
      flex: 1, height: 40,
      flexDirection: 'column', gap: 3,
      borderRadius: 0,
      position: 'relative',
    }}>
      <span style={{
        fontSize: 13,
        color: isActive
          ? tab.id === 'soundgenic' ? 'var(--color-blue)' : 'var(--color-green)'
          : 'rgba(255,255,255,0.30)',
        lineHeight: 1,
      }}>{tab.sym}</span>
      <span className="engraved" style={{
        fontSize: 7, letterSpacing: '1.5px',
        color: isActive
          ? tab.id === 'soundgenic' ? 'rgba(59,130,246,0.70)' : 'rgba(34,197,94,0.70)'
          : undefined,
      }}>{tab.label}</span>
      {badge !== undefined && badge > 0 && (
        <span style={{
          position: 'absolute', top: 4, right: 5,
          background: 'var(--color-green)', color: '#000',
          fontSize: 7, fontWeight: 700,
          borderRadius: '9999px',
          minWidth: 14, height: 14,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 2px', lineHeight: 1,
        }}>{badge > 99 ? '99+' : badge}</span>
      )}
    </button>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function DmpPage() {
  const { status, wsState } = usePlaybackStatus()
  const [activeTab, setActiveTab]           = useState<Tab>('library')
  const [artworkUrl, setArtworkUrl]         = useState<string | null>(null)
  const [playlistTarget, setPlaylistTarget] = useState<Track[] | null>(null)
  const [mounted, setMounted]               = useState(false)

  useEffect(() => { setMounted(true) }, [])

  // Fix 2: UPnP tracks have artwork_url, local tracks use MPD readpicture
  useEffect(() => {
    const track = status.current_track
    if (!track) { setArtworkUrl(null); return }
    setArtworkUrl(track.artwork_url ?? api.library.artworkUrl(track.uri))
  }, [status.current_track])

  const handlePlayPause = () =>
    status.state === 'play' ? api.playback.pause() : api.playback.play()

  const handleAddToPlaylist = (t: Track | Track[]) =>
    setPlaylistTarget(Array.isArray(t) ? t : [t])

  const track    = status.current_track
  const artist   = track?.artist ?? ''
  const title    = track?.title  ?? ''
  const format   = track?.source === 'upnp' ? 'STREAM' : ''
  const pct      = status.duration > 0
    ? Math.min(100, (status.position / status.duration) * 100) : 0

  // WS status label (matches DAP exactly)
  const wsLabel =
    wsState === 'connected'    ? 'MPD CONNECTED' :
    wsState === 'connecting'   ? 'CONNECTING…'   :
                                 'DISCONNECTED — RETRYING'
  const wsColor =
    wsState === 'connected'    ? 'text-emerald-500' :
    wsState === 'connecting'   ? 'text-yellow-500'  :
                                 'text-gray-500'
  const wsDotCls =
    wsState === 'connected'    ? 'bg-emerald-500 shadow-[0_0_8px_rgba(52,211,153,0.8)]' :
    wsState === 'connecting'   ? 'bg-yellow-500'  :
                                 'bg-gray-600'

  const TABS: { id: Tab; label: string; sym: string }[] = [
    { id: 'library',    label: 'LIB',  sym: '♪'  },
    { id: 'soundgenic', label: 'SRV',  sym: '📡' },
    { id: 'queue',      label: 'QUE',  sym: '≡'  },
    { id: 'history',    label: 'HIS',  sym: '⏱' },
    { id: 'playlists',  label: 'LIST', sym: '♥'  },
  ]

  if (!mounted) return null

  return (
    // ── Outer wrapper — exact same dimensions/scaling as DAP ────────────────
    <div className="font-body bg-[#050505] flex justify-center items-start min-h-screen m-0 overflow-x-hidden py-10">

      {/* CSS for on-surface colors (same as DAP inline style) */}
      <style>{`
        :root {
          --color-on-surface: #2d3436;
          --color-on-surface-variant: #636e72;
          --color-surface: #f5f6fa;
        }
        .album-art-container {
          box-shadow: 0 40px 80px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.4);
          background: #ffffff;
        }
      `}</style>

      {/*
        ── Outer container — w-[800px] with same responsive scaling as DAP ──
        scale-[0.45] sm:scale-[0.6] md:scale-[0.8] lg:scale-100
      */}
      <div className="w-[800px] flex items-center justify-center h-fit transform scale-[0.45] sm:scale-[0.6] md:scale-[0.8] lg:scale-100 origin-top pt-20 mb-20">

        {/* ── Oak frame — rounded-[6rem] pt-16 pb-12 px-12, identical to DAP ── */}
        <div className="light-oak-frame rounded-[6rem] w-full pt-16 pb-12 px-12">

          {/* ── Brushed silver panel — rounded-[4rem], identical to DAP ── */}
          <div className="brushed-silver-panel rounded-[4rem] overflow-hidden relative flex flex-col pt-8">

            <main className="flex-grow flex flex-col items-center px-12 pt-12 overflow-hidden pb-12">

              {/* ① MPD STATUS PANEL — pixel-perfect copy of DAP */}
              <div className="w-full flex flex-col items-center gap-6 mb-6 shrink-0">
                <div className="w-full max-w-[650px] bg-black/90 rounded-sm border-2 border-white/5 p-4 flex flex-col gap-2 shadow-[inset_0_0_20px_rgba(0,0,0,1),0_0_15px_rgba(0,0,0,0.5)] mb-2">

                  {/* Status row */}
                  <div className="flex justify-between items-center px-2">
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-1.5 h-1.5 rounded-full ${wsDotCls}`}
                        style={{ animation: wsState === 'connecting' ? 'pulse 1s infinite' : 'none' }}
                      />
                      <span
                        className={`text-[11px] font-bold tracking-[0.2em] uppercase font-mono ${wsColor}`}
                        style={{ textShadow: wsState === 'connected' ? '0 0 10px rgba(52,211,153,0.8)' : 'none' }}
                      >
                        {wsLabel}
                      </span>
                    </div>
                    <span
                      className="text-[11px] font-bold text-red-600/90 tracking-[0.1em] uppercase font-mono"
                      style={{ textShadow: '0 0 8px rgba(220,38,38,0.6)' }}
                    >
                      {format || '---'}
                    </span>
                  </div>

                  <div className="h-px w-full bg-red-900/30" />

                  {/* Track info row */}
                  <div className="px-2 flex justify-between items-center gap-4">
                    <span
                      className="text-[13px] font-black text-red-600 tracking-[0.15em] uppercase font-mono truncate"
                      style={{ textShadow: '0 0 12px rgba(220,38,38,0.9)' }}
                    >
                      {artist ? `${artist} — ${title}` : 'Not Playing'}
                    </span>
                    <span className="text-[11px] font-bold text-red-600/70 tracking-[0.1em] uppercase font-mono shrink-0">
                      {formatDuration(status.position)} / {formatDuration(status.duration) || '--:--'}
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div className="px-2">
                    <div className="h-1 w-full bg-red-900/20 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-red-600/70 rounded-full transition-all duration-1000 linear"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* ② ALBUM ART — pixel-perfect copy of DAP */}
                <div className="w-full max-w-[650px] aspect-square album-art-container p-1 rounded-sm bg-white shrink-0">
                  {artworkUrl ? (
                    <img
                      alt="Album Art"
                      className="w-full h-full object-cover shadow-2xl"
                      src={artworkUrl}
                    />
                  ) : (
                    <div className="w-full h-full bg-gray-900 flex items-center justify-center shadow-2xl">
                      <span style={{ fontSize: 64, color: 'rgba(255,255,255,0.12)' }}>♪</span>
                    </div>
                  )}
                </div>
              </div>

              {/* ③ TRANSPORT CONTROLS
                  修正a: 2倍サイズ、アルミ/ガラス質感、DAP MODE/OUTPUTと同等
                  修正b: オーク色の仕切りを削除、シルバーパネル上に直接配置
              */}
              <div className="w-full flex flex-col items-center mb-10 shrink-0">

                {/* シークスライダー（細いスロット） */}
                <div style={{
                  width: '100%', maxWidth: 650,
                  height: 4,
                  background: 'rgba(0,0,0,0.25)',
                  borderRadius: 2,
                  overflow: 'hidden',
                  marginBottom: 28,
                  position: 'relative',
                }}>
                  <div style={{
                    position: 'absolute', left: 0, top: 0, bottom: 0,
                    width: `${pct}%`,
                    background: 'rgba(34,197,94,0.70)',
                    borderRadius: 2,
                    transition: 'width 1s linear',
                  }} />
                  <input
                    type="range" min={0} max={status.duration || 1}
                    value={status.position} step={1}
                    onChange={e => api.playback.seek(Number(e.target.value))}
                    style={{
                      position: 'absolute', inset: 0,
                      width: '100%', height: '100%',
                      opacity: 0, cursor: 'pointer', margin: 0,
                    }}
                  />
                </div>

                {/* ボタン群 — 中央揃え、2倍サイズのglass/aluminumラウンドボタン */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 20,
                }}>
                  {/* Shuffle */}
                  <TBtn onClick={() => api.playback.toggleRandom()} active={status.random} size="sm">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                      stroke={status.random ? '#22c55e' : 'rgba(45,52,54,0.85)'}
                      strokeWidth="2.5">
                      <polyline points="16 3 21 3 21 8"/>
                      <line x1="4" y1="20" x2="21" y2="3"/>
                      <polyline points="21 16 21 21 16 21"/>
                      <line x1="15" y1="15" x2="21" y2="21"/>
                    </svg>
                  </TBtn>

                  {/* Previous */}
                  <TBtn onClick={() => api.playback.previous()} size="md">
                    <span style={{ fontSize: 24, color: 'rgba(45,52,54,0.85)', lineHeight: 1 }}>⏮</span>
                  </TBtn>

                  {/* Play / Pause — largest button */}
                  <TBtn onClick={handlePlayPause} active={status.state === 'play'} size="lg">
                    <span style={{
                      fontSize: 34,
                      lineHeight: 1,
                      color: status.state === 'play' ? '#22c55e' : 'rgba(45,52,54,0.85)',
                      textShadow: status.state === 'play'
                        ? '0 0 12px rgba(34,197,94,0.6), 0 0 24px rgba(34,197,94,0.3)'
                        : 'none',
                    }}>
                      {status.state === 'play' ? '⏸' : '▶'}
                    </span>
                  </TBtn>

                  {/* Next */}
                  <TBtn onClick={() => api.playback.next()} size="md">
                    <span style={{ fontSize: 24, color: 'rgba(45,52,54,0.85)', lineHeight: 1 }}>⏭</span>
                  </TBtn>

                  {/* Repeat */}
                  <TBtn onClick={() => api.playback.toggleRepeat()} active={status.repeat} size="sm">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                      stroke={status.repeat ? '#22c55e' : 'rgba(45,52,54,0.85)'}
                      strokeWidth="2.5">
                      <polyline points="17 1 21 5 17 9"/>
                      <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
                      <polyline points="7 23 3 19 7 15"/>
                      <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
                    </svg>
                  </TBtn>
                </div>

                {/* 時刻表示 */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  width: '100%',
                  maxWidth: 650,
                  marginTop: 14,
                }}>
                  <span style={{
                    fontSize: 11, fontWeight: 700,
                    letterSpacing: '0.12em',
                    color: 'rgba(45,52,54,0.55)',
                    fontFamily: 'var(--font-mono)',
                    textTransform: 'uppercase',
                  }}>{formatDuration(status.position)}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 700,
                    letterSpacing: '0.12em',
                    color: 'rgba(45,52,54,0.55)',
                    fontFamily: 'var(--font-mono)',
                    textTransform: 'uppercase',
                  }}>{formatDuration(status.duration) || '--:--'}</span>
                </div>
              </div>

            </main>

            {/* ④ DARK ALUMINUM BROWSER PANEL
                修正b: オーク仕切りなし — シルバーパネルから直接切り替わる
                修正c: テキスト輝度を上げ、より視認性を高める
            */}
            <div className="alum-dark" style={{ borderTop: '1px solid rgba(0,0,0,0.6)' }}>

              {/* Tab switch row */}
              <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
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

              {/*
                修正d: 縦スペース拡大 (480→600px)
                        フォントサイズ・パディングを統一して余裕を持たせる
              */}
              <div style={{ height: 700, overflowY: 'auto', overflowX: 'hidden' }}>
                {activeTab === 'library'    && <LibraryView     currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
                {activeTab === 'soundgenic' && <SoundgenicView  currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
                {activeTab === 'queue'      && <QueueView />}
                {activeTab === 'history'    && <HistoryView />}
                {activeTab === 'playlists'  && <PlaylistsView />}
              </div>

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
