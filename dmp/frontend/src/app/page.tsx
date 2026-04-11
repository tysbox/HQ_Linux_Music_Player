'use client'
import { useState, useEffect } from 'react'
import { usePlaybackStatus } from '@/hooks/usePlaybackStatus'
import { NowPlayingBar } from '@/components/NowPlayingBar'
import { LibraryView } from '@/components/LibraryView'
import { QueueView } from '@/components/QueueView'
import { HistoryView } from '@/components/HistoryView'
import { PlaylistsView } from '@/components/PlaylistsView'
import { SoundgenicView } from '@/components/SoundgenicView'
import { AddToPlaylistModal } from '@/components/AddToPlaylistModal'
import { api } from '@/lib/api'
import { Track } from '@/lib/types'

type Tab = 'library' | 'soundgenic' | 'queue' | 'history' | 'playlists'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'library',   label: 'Library',   icon: '🎵' },
  { id: 'soundgenic', label: 'Soundgenic', icon: '📡' },
  { id: 'queue',     label: 'Queue',     icon: '📋' },
  { id: 'history',   label: 'History',   icon: '🕐' },
  { id: 'playlists', label: 'Playlists', icon: '♥' },
]

export default function DmpPage() {
  const { status, wsState } = usePlaybackStatus()
  const [activeTab, setActiveTab] = useState<Tab>('library')
  const [artworkUrl, setArtworkUrl] = useState<string | null>(null)
  const [playlistTarget, setPlaylistTarget] = useState<Track[] | null>(null)

  // Fetch artwork when track changes（fix #2: UPnPトラックのartwork_urlを優先）
  useEffect(() => {
    const track = status.current_track
    if (!track) { setArtworkUrl(null); return }
    if (track.artwork_url) {
      // UPnP（Soundgenic/Asset）のトラックは artwork_url を直接持つ
      setArtworkUrl(track.artwork_url)
    } else {
      // ローカルファイルはMPDのreadpicture経由
      setArtworkUrl(api.library.artworkUrl(track.uri))
    }
  }, [status.current_track])

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100dvh',
      background: 'var(--color-surface-base)',
      overflow: 'hidden',
    }}>
      {/* Fixed Now Playing bar */}
      <NowPlayingBar
        status={status}
        wsState={wsState}
        artworkUrl={artworkUrl}
      />

      {/* Main content area — offset by bar height (56px + 3px progress) */}
      <div style={{
        flex: 1,
        marginTop: 59,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Tab navigation */}
        <nav style={{
          display: 'flex',
          borderBottom: '1px solid var(--color-border-subtle)',
          background: 'var(--color-surface-panel)',
          flexShrink: 0,
        }}>
          {TABS.map(tab => (
            <TabButton
              key={tab.id}
              tab={tab}
              isActive={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
              badge={tab.id === 'queue' ? status.queue_length : undefined}
            />
          ))}
        </nav>

        {/* View content */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          {activeTab === 'library' && (
            <LibraryView
              currentUri={status.current_track?.uri}
              onAddToPlaylist={t => setPlaylistTarget(Array.isArray(t) ? t : [t])}
            />
          )}
          {activeTab === 'soundgenic' && <SoundgenicView currentUri={status.current_track?.uri} onAddToPlaylist={t => setPlaylistTarget(Array.isArray(t) ? t : [t])} />}
          {activeTab === 'queue'     && <QueueView currentUri={status.current_track?.uri} />}
          {activeTab === 'history'   && <HistoryView />}
          {activeTab === 'playlists' && <PlaylistsView />}
        </div>
      </div>

      {/* Add to Playlist modal */}
      {playlistTarget && (
        <AddToPlaylistModal
          tracks={playlistTarget}
          onClose={() => setPlaylistTarget(null)}
        />
      )}
    </div>
  )
}

// ── Tab button ────────────────────────────────────────────────
function TabButton({ tab, isActive, onClick, badge }: {
  tab: { id: Tab; label: string; icon: string }
  isActive: boolean; onClick: () => void; badge?: number
}) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: '9px 4px 8px',
        background: 'none',
        border: 'none',
        borderBottom: isActive
          ? '2px solid var(--color-green)'
          : '2px solid transparent',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 2,
        transition: 'border-color 0.15s',
        position: 'relative',
      }}
    >
      <span style={{ fontSize: 14, lineHeight: 1 }}>{tab.icon}</span>
      <span style={{
        fontSize: 'var(--fs-xs)',
        letterSpacing: 'var(--ls-label)',
        textTransform: 'uppercase',
        color: isActive ? 'var(--color-green)' : 'var(--color-text-inactive)',
        fontWeight: 'var(--fw-medium)',
        transition: 'color 0.15s',
      }}>
        {tab.label}
      </span>
      {badge !== undefined && badge > 0 && (
        <span style={{
          position: 'absolute',
          top: 6, right: '20%',
          background: 'var(--color-green)',
          color: '#000',
          fontSize: 'var(--fs-2xs)',
          fontWeight: 700,
          borderRadius: 'var(--radius-full)',
          minWidth: 14, height: 14,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 3px',
          lineHeight: 1,
        }}>
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </button>
  )
}
