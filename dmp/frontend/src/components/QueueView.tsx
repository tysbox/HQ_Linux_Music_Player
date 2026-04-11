'use client'
import { useState, useEffect } from 'react'
import { QueueItem } from '@/lib/types'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

export function QueueView({ currentUri }: { currentUri?: string }) {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const data = await api.queue.get()
      setQueue(data.queue ?? [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  // 曲が変わったらキューを再取得（▶マーク更新）
  useEffect(() => { load() }, [currentUri])

  const remove = async (pos: number) => {
    await api.queue.remove(pos)
    load()
  }

  const playAt = async (pos: number) => {
    await api.queue.playAt(pos)
  }

  const clearQueue = async () => {
    await api.queue.clear()
    setQueue([])
  }

  const shuffle = async () => {
    await api.queue.shuffle()
    load()
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
        <span style={{ fontSize: 'var(--fs-xs)', letterSpacing: 'var(--ls-label)', textTransform: 'uppercase', color: 'var(--color-text-disabled)' }}>
          Queue — {queue.length} tracks
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          <ActionBtn onClick={load} label="Refresh" />
          <ActionBtn onClick={shuffle} label="Shuffle" />
          <ActionBtn onClick={clearQueue} label="Clear" danger />
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {queue.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: '48px 24px', gap: 8, color: 'var(--color-text-disabled)',
            fontSize: 'var(--fs-base)', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28 }}>📋</div>
            <div>Queue is empty</div>
            <div style={{ fontSize: 'var(--fs-xs)' }}>Add tracks from the Library</div>
          </div>
        ) : (
          queue.map(item => (
            <QueueItemRow
              key={item.position}
              item={item}
              onPlay={() => { playAt(item.position); load() }}
              onRemove={() => remove(item.position)}
            />
          ))
        )}
      </div>
    </div>
  )
}

function QueueItemRow({ item, onPlay, onRemove }: {
  item: QueueItem; onPlay: () => void; onRemove: () => void
}) {
  const { track, is_current, position } = item
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '7px 12px',
        background: is_current ? 'var(--color-green-bg)' : 'transparent',
        borderLeft: is_current ? '2px solid var(--color-green)' : '2px solid transparent',
        borderBottom: '1px solid var(--color-border-subtle)',
        cursor: 'pointer',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (!is_current) e.currentTarget.style.background = 'var(--color-surface-card)' }}
      onMouseLeave={e => { if (!is_current) e.currentTarget.style.background = 'transparent' }}
      onDoubleClick={onPlay}
    >
      <div style={{
        width: 20, textAlign: 'right', flexShrink: 0,
        fontSize: 'var(--fs-xs)',
        color: is_current ? 'var(--color-green)' : 'var(--color-text-disabled)',
        fontVariantNumeric: 'tabular-nums',
      }}>
        {is_current ? '▶' : position + 1}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--fs-base)', fontWeight: 'var(--fw-medium)',
          color: is_current ? 'var(--color-green)' : 'var(--color-text-primary)',
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
        fontSize: 'var(--fs-xs)', color: 'var(--color-text-disabled)',
        fontVariantNumeric: 'tabular-nums', flexShrink: 0,
      }}>
        {formatDuration(track.duration)}
      </div>
      <button
        title="Remove from queue"
        onClick={e => { e.stopPropagation(); onRemove() }}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--color-text-muted)', fontSize: 14, lineHeight: 1,
          padding: '4px 6px', borderRadius: 'var(--radius-sm)',
          flexShrink: 0, transition: 'color 0.1s',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.color = 'var(--color-red)'
          e.currentTarget.style.background = 'rgba(255,80,80,0.08)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.color = 'var(--color-text-muted)'
          e.currentTarget.style.background = 'none'
        }}
      >🗑</button>
    </div>
  )
}

function ActionBtn({ onClick, label, danger }: { onClick: () => void; label: string; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none',
        border: `1px solid ${danger ? 'var(--color-red-border)' : 'var(--color-border-medium)'}`,
        borderRadius: 'var(--radius-sm)',
        color: danger ? 'var(--color-red)' : 'var(--color-text-tertiary)',
        fontSize: 'var(--fs-xs)',
        letterSpacing: 'var(--ls-label)',
        textTransform: 'uppercase',
        padding: '4px 8px',
        cursor: 'pointer',
        transition: 'background 0.1s',
      }}
    >
      {label}
    </button>
  )
}
