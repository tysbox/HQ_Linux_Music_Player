'use client'
import React from 'react'
import { PlaybackStatus } from '@/lib/types'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

interface Props {
  status: PlaybackStatus
  wsState: 'connecting' | 'connected' | 'disconnected'
  artworkUrl: string | null
}

// ── WS Status dot ────────────────────────────────────────────
function WsDot({ state }: { state: Props['wsState'] }) {
  const color =
    state === 'connected'    ? 'var(--color-green)' :
    state === 'connecting'   ? 'var(--color-amber)' :
                               'var(--color-red)'
  const pulse = state === 'connecting'
  return (
    <span style={{
      display: 'inline-block',
      width: 5, height: 5,
      borderRadius: '9999px',
      background: color,
      flexShrink: 0,
    }} className={pulse ? 'pulse-green' : ''} />
  )
}

// ── Progress bar ─────────────────────────────────────────────
function ProgressBar({ position, duration, onSeek }: {
  position: number; duration: number; onSeek: (s: number) => void
}) {
  const pct = duration > 0 ? Math.min((position / duration) * 100, 100) : 0
  return (
    <input
      type="range"
      className="progress-bar"
      min={0} max={duration || 1} value={position}
      onChange={e => onSeek(Number(e.target.value))}
      style={{
        width: '100%',
        height: 3,
        background: `linear-gradient(to right, var(--color-green) ${pct}%, var(--color-border-medium) ${pct}%)`,
        border: 'none',
        outline: 'none',
        cursor: 'pointer',
        flexShrink: 0,
      }}
    />
  )
}

// ── Icon buttons ─────────────────────────────────────────────
function TransportBtn({
  onClick, children, active = false, large = false,
}: {
  onClick: () => void; children: React.ReactNode; active?: boolean; large?: boolean
}) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: large ? '6px' : '4px',
        color: active ? 'var(--color-green)' : 'var(--color-text-tertiary)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderRadius: 'var(--radius-sm)',
        transition: 'color 0.15s',
        fontSize: large ? 20 : 14,
        lineHeight: 1,
        userSelect: 'none',
      }}
      onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-text-primary)')}
      onMouseLeave={e => (e.currentTarget.style.color = active ? 'var(--color-green)' : 'var(--color-text-tertiary)')}
    >
      {children}
    </button>
  )
}

export function NowPlayingBar({ status, wsState, artworkUrl }: Props) {
  const { state, current_track: track, position, duration, random, repeat } = status

  const handlePlayPause = () => {
    state === 'play' ? api.playback.pause() : api.playback.play()
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0,
      zIndex: 100,
      background: 'var(--color-surface-panel)',
      borderBottom: '1px solid var(--color-border-subtle)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Progress bar — full width at top */}
      <ProgressBar
        position={position}
        duration={duration}
        onSeek={s => api.playback.seek(s)}
      />

      {/* Main bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 14px',
        height: 56,
      }}>
        {/* Artwork */}
        <div style={{
          width: 36, height: 36,
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          flexShrink: 0,
          background: 'var(--color-surface-card)',
          border: '1px solid var(--color-border-card)',
        }}>
          {artworkUrl ? (
            <img src={artworkUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <div style={{
              width: '100%', height: '100%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--color-text-disabled)',
              fontSize: 16,
            }}>♪</div>
          )}
        </div>

        {/* Track info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 'var(--fs-base)',
            fontWeight: 'var(--fw-medium)',
            color: 'var(--color-text-primary)',
            letterSpacing: 'var(--ls-title)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {track?.title ?? 'Not Playing'}
          </div>
          <div style={{
            fontSize: 'var(--fs-xs)',
            color: 'var(--color-text-muted)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            marginTop: 1,
          }}>
            {track ? `${track.artist} — ${track.album}` : '—'}
          </div>
        </div>

        {/* Time */}
        <div style={{
          fontSize: 'var(--fs-sm)',
          color: 'var(--color-text-muted)',
          fontVariantNumeric: 'tabular-nums',
          flexShrink: 0,
          display: 'flex',
          gap: 2,
        }}>
          <span style={{ color: 'var(--color-text-tertiary)' }}>{formatDuration(position)}</span>
          <span>/</span>
          <span>{formatDuration(duration)}</span>
        </div>

        {/* Transport controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
          <TransportBtn onClick={() => api.playback.previous()}>⏮</TransportBtn>
          <TransportBtn onClick={handlePlayPause} large>
            {state === 'play' ? '⏸' : '▶'}
          </TransportBtn>
          <TransportBtn onClick={() => api.playback.next()}>⏭</TransportBtn>
        </div>

        {/* Secondary controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <TransportBtn onClick={() => api.playback.toggleRandom()} active={random}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="16 3 21 3 21 8"/>
              <line x1="4" y1="20" x2="21" y2="3"/>
              <polyline points="21 16 21 21 16 21"/>
              <line x1="15" y1="15" x2="21" y2="21"/>
            </svg>
          </TransportBtn>
          <TransportBtn onClick={() => api.playback.toggleRepeat()} active={repeat}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="17 1 21 5 17 9"/>
              <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
              <polyline points="7 23 3 19 7 15"/>
              <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
            </svg>
          </TransportBtn>
          <WsDot state={wsState} />
        </div>
      </div>
    </div>
  )
}
