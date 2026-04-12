'use client'
import { Track } from '@/lib/types'
import { formatDuration } from '@/lib/utils'
import { api } from '@/lib/api'
import { useState } from 'react'

interface Props {
  track: Track
  index?: number
  showAlbum?: boolean
  showArtist?: boolean
  isCurrent?: boolean
  onPlay?: () => void
  onAddToPlaylist?: (track: Track) => void
}

export function TrackRow({
  track, index, showAlbum = false, showArtist = false,
  isCurrent = false, onPlay, onAddToPlaylist,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  const handleAction = async (action: 'play' | 'next' | 'queue' | 'playlist') => {
    setMenuOpen(false)
    try {
      const meta = {
        title: track.title,
        artist: track.artist,
        album: track.album,
        artwork_url: track.artwork_url,
      }

      if (action === 'play') {
        await api.queue.add(track.uri, true, false, meta)
        if (onPlay) onPlay()
      } else if (action === 'next') {
        await api.queue.add(track.uri, false, true, meta)
        setFeedback('Next')
      } else if (action === 'queue') {
        await api.queue.add(track.uri, false, false, meta)
        setFeedback('+Queue')
      } else if (action === 'playlist') {
        if (onAddToPlaylist) onAddToPlaylist(track)
      }
      setTimeout(() => setFeedback(null), 1500)
    } catch {}
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '7px 12px',
        background: isCurrent ? 'var(--color-green-bg)' : 'transparent',
        borderLeft: isCurrent ? '2px solid var(--color-green)' : '2px solid transparent',
        borderBottom: '1px solid var(--color-border-subtle)',
        cursor: 'pointer',
        position: 'relative',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => {
        if (!isCurrent) e.currentTarget.style.background = 'var(--color-surface-card)'
      }}
      onMouseLeave={e => {
        if (!isCurrent) e.currentTarget.style.background = 'transparent'
      }}
      onDoubleClick={() => handleAction('play')}
    >
      {/* Track number / index */}
      <div style={{
        width: 20, flexShrink: 0, textAlign: 'right',
        fontSize: 'var(--fs-xs)',
        color: isCurrent ? 'var(--color-green)' : 'var(--color-text-disabled)',
        fontVariantNumeric: 'tabular-nums',
      }}>
        {isCurrent ? '▶' : (index !== undefined ? index + 1 : track.track_number ?? '')}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--fs-base)',
          fontWeight: 'var(--fw-medium)',
          color: isCurrent ? 'var(--color-green)' : 'var(--color-text-primary)',
          letterSpacing: 'var(--ls-title)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {track.title}
        </div>
        {(showArtist || showAlbum) && (
          <div style={{
            fontSize: 'var(--fs-xs)',
            color: 'var(--color-text-muted)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            marginTop: 1,
          }}>
            {showArtist && track.artist}
            {showArtist && showAlbum && ' — '}
            {showAlbum && track.album}
          </div>
        )}
      </div>

      {/* Duration */}
      <div style={{
        fontSize: 'var(--fs-xs)',
        color: 'var(--color-text-disabled)',
        fontVariantNumeric: 'tabular-nums',
        flexShrink: 0,
      }}>
        {feedback
          ? <span style={{ color: 'var(--color-green)', fontSize: 'var(--fs-xs)' }}>{feedback}</span>
          : formatDuration(track.duration)
        }
      </div>

      {/* Context menu button */}
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <button
          onClick={e => { e.stopPropagation(); setMenuOpen(o => !o) }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--color-text-disabled)',
            fontSize: 14, padding: '2px 4px',
            borderRadius: 'var(--radius-sm)',
            lineHeight: 1,
          }}
        >
          ⋯
        </button>
        {menuOpen && (
          <ContextMenu
            onPlay={() => handleAction('play')}
            onPlayNext={() => handleAction('next')}
            onAddToQueue={() => handleAction('queue')}
            onAddToPlaylist={() => handleAction('playlist')}
            onClose={() => setMenuOpen(false)}
          />
        )}
      </div>
    </div>
  )
}

// ── Context Menu ─────────────────────────────────────────────
function ContextMenu({ onPlay, onPlayNext, onAddToQueue, onAddToPlaylist, onClose }: {
  onPlay: () => void; onPlayNext: () => void
  onAddToQueue: () => void; onAddToPlaylist: () => void; onClose: () => void
}) {
  const items = [
    { label: 'Play Now',         action: onPlay },
    { label: 'Play Next',        action: onPlayNext },
    { label: 'Add to Queue',     action: onAddToQueue },
    { label: 'Add to Playlist…', action: onAddToPlaylist },
  ]
  return (
    <>
      {/* Backdrop */}
      <div
        style={{ position: 'fixed', inset: 0, zIndex: 200 }}
        onClick={onClose}
      />
      <div style={{
        position: 'absolute', right: 0, top: '100%',
        zIndex: 201,
        background: 'var(--color-surface-bar)',
        border: '1px solid var(--color-border-medium)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        minWidth: 140,
        boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
      }}>
        {items.map(item => (
          <button
            key={item.label}
            onClick={item.action}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '8px 12px',
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 'var(--fs-base)',
              color: 'var(--color-text-tertiary)',
              borderBottom: '1px solid var(--color-border-subtle)',
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
            {item.label}
          </button>
        ))}
      </div>
    </>
  )
}
