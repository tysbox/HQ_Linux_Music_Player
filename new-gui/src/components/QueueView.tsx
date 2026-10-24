'use client'
import { useState, useEffect } from 'react'
import { QueueItem } from '@/lib/types'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

export function QueueView() {
  const [queue, setQueue]   = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try { const d = await api.queue.get(); setQueue(d.queue ?? []) } catch {}
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  if (loading) return <div style={{ padding: 24, textAlign: 'center' }}><span className="engraved">Loading…</span></div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 14px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <span className="engraved">Queue — {queue.length} tracks</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="touch-sw" style={{ height: 30, padding: '0 14px', borderRadius: 4, fontSize: 0, cursor: 'pointer' }}
            onClick={async () => { await api.queue.shuffle(); load() }}>
            <span className="engraved" style={{ fontSize: 10, letterSpacing: '1px' }}>SHUFFLE</span>
          </button>
          <button className="touch-sw" style={{ height: 30, padding: '0 14px', borderRadius: 4, fontSize: 0, borderColor: 'rgba(239,68,68,0.30)', cursor: 'pointer' }}
            onClick={async () => { await api.queue.clear(); setQueue([]) }}>
            <span style={{ fontSize: 10, letterSpacing: '1px', color: 'rgba(239,68,68,0.60)', textTransform: 'uppercase' }}>CLEAR</span>
          </button>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {queue.length === 0 ? (
          <div style={{ padding: '40px 24px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <div style={{ fontSize: 24, opacity: 0.2 }}>≡</div>
            <span className="engraved">Queue is empty</span>
          </div>
        ) : queue.map(item => (
          <div key={item.position}
            className={`track-row${item.is_current ? ' track-row-playing' : ''}`}
            style={{ minHeight: 44, cursor: 'pointer' }}
            onClick={() => { api.queue.playAt(item.position); load() }}
          >
            <div style={{ width: 18, textAlign: 'center', flexShrink: 0, fontSize: 12, color: item.is_current ? 'var(--color-green)' : 'rgba(255,255,255,0.22)' }}>
              {item.is_current ? <span className="led-green">▶</span> : ''}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 500, letterSpacing: '-0.3px', color: item.is_current ? 'var(--color-green)' : '#fbbf24', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.track.artist} — {item.track.title}
              </div>
              <div style={{ fontSize: 10, color: 'rgba(251,191,36,0.55)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.track.album}
              </div>
            </div>
            <div style={{ fontSize: 10, color: 'rgba(251,191,36,0.45)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{formatDuration(item.track.duration)}</div>
            <button className="touch-sw" style={{ width: 28, height: 28, borderRadius: 4, fontSize: 13, color: 'rgba(239,68,68,0.45)', flexShrink: 0, cursor: 'pointer' }}
              onClick={e => { e.stopPropagation(); api.queue.remove(item.position).then(load) }}>✕</button>
          </div>
        ))}
      </div>
    </div>
  )
}
