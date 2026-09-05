'use client'
import { useState, useEffect } from 'react'
import { HistoryEntry } from '@/lib/types'
import { api } from '@/lib/api'
import { formatDuration, formatTime } from '@/lib/utils'

export function HistoryView() {
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try { const d = await api.history.get(200); setEntries(d.history ?? []) } catch {}
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  if (loading) return <div style={{ padding: 24, textAlign: 'center' }}><span className="engraved">Loading…</span></div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 14px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <span className="engraved">History — {entries.length} tracks</span>
        {entries.length > 0 && (
          <button className="touch-sw" style={{ height: 22, padding: '0 8px', borderRadius: 3 }}
            onClick={async () => { await api.history.clear(); setEntries([]) }}>
            <span style={{ fontSize: 7, letterSpacing: '1px', color: 'rgba(239,68,68,0.60)', textTransform: 'uppercase' }}>CLEAR</span>
          </button>
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {entries.length === 0 ? (
          <div style={{ padding: '40px 24px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <div style={{ fontSize: 24, opacity: 0.2 }}>⏱</div>
            <span className="engraved">No history yet</span>
          </div>
        ) : entries.map((entry, i) => (
          <div key={i} className="track-row" onDoubleClick={() => api.queue.add(entry.track.uri, true, false, {
            title: entry.track.title,
            artist: entry.track.artist,
            album: entry.track.album,
            artwork_url: entry.track.artwork_url,
          })}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 500, letterSpacing: '-0.3px', color: 'rgba(255,255,255,0.88)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.track.title}</div>
              <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.32)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.track.artist} — {entry.track.album}</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, flexShrink: 0 }}>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.25)', fontVariantNumeric: 'tabular-nums' }}>{formatDuration(entry.track.duration)}</span>
              <span style={{ fontSize: 7, color: 'rgba(255,255,255,0.16)' }}>{formatTime(entry.played_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
