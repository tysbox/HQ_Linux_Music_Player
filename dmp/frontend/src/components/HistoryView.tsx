'use client'
import { useState, useEffect } from 'react'
import { HistoryEntry } from '@/lib/types'
import { api } from '@/lib/api'
import { formatDuration, formatTime } from '@/lib/utils'

export function HistoryView() {
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const data = await api.history.get(200)
      setEntries(data.history ?? [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const clear = async () => {
    await api.history.clear()
    setEntries([])
  }

  if (loading) return (
    <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-disabled)' }}>Loading…</div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 12px',
        borderBottom: '1px solid var(--color-border-subtle)',
        background: 'var(--color-surface-panel)',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        <span style={{
          fontSize: 'var(--fs-xs)', letterSpacing: 'var(--ls-label)',
          textTransform: 'uppercase', color: 'var(--color-text-disabled)',
        }}>
          History — {entries.length} tracks
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            onClick={load}
            style={{
              background: 'none',
              border: '1px solid var(--color-border-medium)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text-tertiary)',
              fontSize: 'var(--fs-xs)',
              letterSpacing: 'var(--ls-label)',
              textTransform: 'uppercase',
              padding: '4px 8px',
              cursor: 'pointer',
            }}
          >
            Refresh
          </button>
          {entries.length > 0 && (
          <button
            onClick={clear}
            style={{
              background: 'none',
              border: '1px solid var(--color-red-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-red)',
              fontSize: 'var(--fs-xs)',
              letterSpacing: 'var(--ls-label)',
              textTransform: 'uppercase',
              padding: '4px 8px',
              cursor: 'pointer',
            }}
          >
            Clear
          </button>
          )}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {entries.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: '48px 24px', gap: 8, color: 'var(--color-text-disabled)',
            fontSize: 'var(--fs-base)', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28 }}>🕐</div>
            <div>No history yet</div>
          </div>
        ) : (
          entries.map((entry, i) => (
            <HistoryRow key={i} entry={entry} onPlay={async () => {
              await api.queue.add(entry.track.uri, true)
            }} />
          ))
        )}
      </div>
    </div>
  )
}

function HistoryRow({ entry, onPlay }: { entry: HistoryEntry; onPlay: () => void }) {
  const { track, played_at } = entry
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '7px 12px',
        borderBottom: '1px solid var(--color-border-subtle)',
        cursor: 'pointer',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--color-surface-card)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      onDoubleClick={onPlay}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--fs-base)', fontWeight: 'var(--fw-medium)',
          color: 'var(--color-text-primary)',
          letterSpacing: 'var(--ls-title)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{track.title}</div>
        <div style={{
          fontSize: 'var(--fs-xs)', color: 'var(--color-text-muted)', marginTop: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {track.artist} — {track.album}
        </div>
      </div>
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'flex-end',
        gap: 2, flexShrink: 0,
      }}>
        <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)', fontVariantNumeric: 'tabular-nums' }}>
          {formatDuration(track.duration)}
        </span>
        <span style={{ fontSize: 'var(--fs-2xs)', color: 'var(--color-text-hint)' }}>
          {formatTime(played_at)}
        </span>
      </div>
    </div>
  )
}
