'use client'
// ─────────────────────────────────────────────────────────────────────────────
// InfoPanel — Bisen WikiModal (src/components/WikiModal.tsx) の忠実移植.
//
// Listening Wiki: 3 タブ (People / Album / Signal) の制作クレジット Popup。
// データは hq_api /api/info/credits (MusicBrainz + Discogs + Wikipedia 統合) から取得。
// 未収録行は "Not catalogued" (italic)、実在行はタップで Google 検索。
// ─────────────────────────────────────────────────────────────────────────────
import React, { useEffect, useState } from 'react'
import { X, Globe, Mic, Disc3, Waves } from 'lucide-react'
import { api } from '@/lib/api'

const NOT_IN_DB = 'Not catalogued'

interface Props {
  open: boolean
  onClose: () => void
  currentTrack?: { artist?: string; title?: string; album?: string; uri?: string }
  // SIGNAL タブ用 (page.tsx の信号真理ヘルパから供給)
  format?: string
  srcRate?: number
  srcBits?: number
}

export const InfoPanel: React.FC<Props> = ({
  open, onClose, currentTrack, format, srcRate, srcBits,
}) => {
  const [activeTab, setActiveTab] = useState(0)
  const [wikiData, setWikiData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  // Phase 4 (Step 4-2): bisen-dspd デーモン状態 (出力真理表示用)
  const [bisen, setBisen] = useState<any>(null)

  useEffect(() => {
    if (!open || !currentTrack?.artist || !currentTrack?.title) return
    setLoading(true)
    setWikiData(null)
    api.info.credits(currentTrack.artist, currentTrack.title, currentTrack.album || '')
      .then((d) => setWikiData(d))
      .catch((e) => console.error('info credits failed', e))
      .finally(() => setLoading(false))
  }, [open, currentTrack?.artist, currentTrack?.title, currentTrack?.album])

  // Phase 4 (Step 4-2): パネルを開くたびにデーモン状態を取得
  useEffect(() => {
    if (!open) return
    api.dsp.bisenStatus()
      .then((d) => setBisen(d))
      .catch((e) => console.error('bisen status failed', e))
  }, [open])

  if (!open) return null

  // Bisen WikiModal V4.5.6 FIX 相当: credits 到着形式を正規化
  const rawCredits = wikiData?.credits || {}

  // Discogs 単数キー → 行表示キーへの正規化 (Bisen catch-all `...rawCredits` が
  // 拾う範囲を明示的に行へ結び付ける。不足行は Not catalogued 表示)
  const c = {
    artistName: rawCredits.artistName || rawCredits.artist || currentTrack?.artist || '',
    artistDisambiguation: rawCredits.artistDisambiguation || '',
    artistBio: rawCredits.artistBio || '',
    artistCountry: rawCredits.country || rawCredits.artistCountry || '',
    trackTitle: rawCredits.trackTitle || currentTrack?.title || '',
    trackLengthMs: rawCredits.trackLengthMs || 0,
    albumTitle: rawCredits.albumTitle || currentTrack?.album || '',
    releaseDate: rawCredits.releaseDate || '',
    releaseCountry: rawCredits.releaseCountry || '',
    producers: rawCredits.producers || rawCredits.producer || '',
    engineers: rawCredits.engineers || rawCredits.engineer
      || rawCredits.mixing_engineer || rawCredits.mastering_engineer
      || rawCredits.recording_engineer || '',
    composers: rawCredits.composers || rawCredits.composer || '',
    performers: rawCredits.performers || rawCredits.vocals || '',
    label: rawCredits.label || '',
    studios: rawCredits.studios || '',
    recordedAt: rawCredits.recordedAt || rawCredits.recorded || '',
    discogsReleaseId: rawCredits.discogs_release_id || '',
    discogsUri: rawCredits.discogs_uri || '',
    format: rawCredits.format || '',
    genre: rawCredits.genre || '',
    year: rawCredits.year || '',
    keyboards: rawCredits.keyboards || '',
    trumpet: rawCredits.trumpet || '',
    bass: rawCredits.bass || '',
    drums: rawCredits.drums || '',
    guitar: rawCredits.guitar || '',
    saxophone: rawCredits.saxophone || '',
    violin: rawCredits.violin || '',
    cello: rawCredits.cello || '',
    wikiSummary: rawCredits.wikiSummary || '',
    ...rawCredits,
  }

  const formatTime = (ms?: number) => {
    if (!ms || ms <= 0) return null
    const total = Math.round(ms / 1000)
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
  }

  const openExternal = (query: string) => {
    if (!query.trim()) return
    window.open(
      `https://www.google.com/search?q=${encodeURIComponent(query)}`, '_blank')
  }

  // Bisen handleTap 相当: 実在値は値自身を検索、未収録は曲情報+制作で検索
  const handleTap = (value: string, isReal: boolean) => {
    const artist = c.artistName || currentTrack?.artist || ''
    const album = c.albumTitle || currentTrack?.album || ''
    const track = c.trackTitle || currentTrack?.title || ''
    if (isReal && value && value !== NOT_IN_DB && !value.startsWith('Not ')) {
      openExternal(value)
    } else {
      openExternal(`${artist} ${album || track} producer studio recording`)
    }
  }

  const artistLine = c.artistName
    ? (c.artistDisambiguation
        ? `${c.artistName} — ${c.artistDisambiguation}`
        : c.artistName)
    : (currentTrack?.artist || 'Unknown')

  // Bisen sections 配列 (People / Album / Signal) — 行構成は完全同一
  const sections = [
    {
      short: 'People',
      icon: <Mic className="w-3 h-3" />,
      items: [
        { label: 'Artist', value: artistLine, isReal: true, search: c.artistName || artistLine },
        { label: 'About the Artist', value: c.artistBio || NOT_IN_DB, isReal: !!c.artistBio, search: c.artistName || '' },
        { label: 'Producers', value: c.producers || NOT_IN_DB, isReal: !!c.producers, search: c.producers || '' },
        { label: 'Engineers', value: c.engineers || NOT_IN_DB, isReal: !!c.engineers, search: c.engineers || '' },
        { label: 'Composers', value: c.composers || NOT_IN_DB, isReal: !!c.composers, search: c.composers || '' },
        { label: 'Performers', value: c.performers || NOT_IN_DB, isReal: !!c.performers, search: c.performers || '' },
        { label: 'Keyboards', value: c.keyboards || NOT_IN_DB, isReal: !!c.keyboards, search: c.keyboards || '' },
        { label: 'Trumpet', value: c.trumpet || NOT_IN_DB, isReal: !!c.trumpet, search: c.trumpet || '' },
        { label: 'Bass', value: c.bass || NOT_IN_DB, isReal: !!c.bass, search: c.bass || '' },
        { label: 'Drums', value: c.drums || NOT_IN_DB, isReal: !!c.drums, search: c.drums || '' },
        { label: 'Guitar', value: c.guitar || NOT_IN_DB, isReal: !!c.guitar, search: c.guitar || '' },
        { label: 'Saxophone', value: c.saxophone || NOT_IN_DB, isReal: !!c.saxophone, search: c.saxophone || '' },
        { label: 'Violin', value: c.violin || NOT_IN_DB, isReal: !!c.violin, search: c.violin || '' },
        { label: 'Cello', value: c.cello || NOT_IN_DB, isReal: !!c.cello, search: c.cello || '' },
      ],
    },
    {
      short: 'Album',
      icon: <Disc3 className="w-3 h-3" />,
      items: [
        { label: 'Album', value: c.albumTitle || currentTrack?.album || NOT_IN_DB, isReal: !!c.albumTitle, search: `${c.albumTitle || ''} ${c.artistName || ''}` },
        { label: 'Release Date', value: c.releaseDate || NOT_IN_DB, isReal: !!c.releaseDate, search: `${c.albumTitle || currentTrack?.album || ''} ${c.releaseDate || ''}` },
        { label: 'Recorded', value: c.studios || c.recordedAt || NOT_IN_DB, isReal: !!(c.studios || c.recordedAt), search: c.studios || c.recordedAt || '' },
        { label: 'Label', value: c.label || NOT_IN_DB, isReal: !!c.label, search: c.label || '' },
        { label: 'Country', value: c.releaseCountry || c.artistCountry || NOT_IN_DB, isReal: !!(c.releaseCountry || c.artistCountry), search: '' },
        { label: 'Duration', value: formatTime(c.trackLengthMs) || '—', isReal: !!c.trackLengthMs, search: '' },
        { label: 'Format', value: c.format || NOT_IN_DB, isReal: !!c.format, search: c.format || '' },
        { label: 'Genre', value: c.genre || NOT_IN_DB, isReal: !!c.genre, search: c.genre || '' },
        { label: 'Year', value: c.year || NOT_IN_DB, isReal: !!c.year, search: c.year || '' },
        { label: 'Discogs ID', value: c.discogsReleaseId || NOT_IN_DB, isReal: !!c.discogsReleaseId, search: c.discogsReleaseId || '' },
        { label: 'Discogs URI', value: c.discogsUri || NOT_IN_DB, isReal: !!c.discogsUri, search: '' },
      ],
    },
    {
      short: 'Signal',
      icon: <Waves className="w-3 h-3" />,
      items: [
        { label: 'Source Format', value: (format || 'PCM').toUpperCase(), isReal: true, search: '' },
        { label: 'Native Resolution', value: (() => {
            const bd = srcBits ?? 16
            if ((format || '').toUpperCase().includes('DSD') || bd === 1) return '1-bit DSD Bitstream'
            return srcRate && srcRate > 0 ? `${(srcRate / 1000).toFixed(1)}kHz / ${bd}-bit` : 'Detecting...'
          })(), isReal: true, search: '' },
        { label: 'Internal Path', value: '192kHz / 32-bit CamillaDSP Chain', isReal: true, search: '' },
        // Phase 4 (Step 4-2): 出力真理 — bisen-dspd デーモン状態
        { label: 'Output Stage', value: (() => {
            if (!bisen) return 'Detecting...'
            if (!bisen.alive) return 'bisen-dspd Offline (Direct)'
            if (!bisen.routing) return 'Direct (CamillaDSP → DAC)'
            if (bisen.bypass) return 'Daemon Bypass (Bitwise Pass)'
            const parts: string[] = []
            if (bisen.tube_enabled) parts.push(`Tube ${bisen.tube_type === 'PENTODE' ? 'KT88' : '300B'} ${Math.round(bisen.tube_bias)}%`)
            if (bisen.restore_enabled) parts.push(`Restore ${String(bisen.restore_mode).toUpperCase()}`)
            return parts.length ? parts.join(' + ') : 'Daemon Active (No DSP)'
          })(), isReal: !!bisen, search: '' },
        { label: 'VU Source', value: (() => {
            if (!bisen) return 'Detecting...'
            if (!bisen.alive || !bisen.routing) return 'CamillaDSP Playback Peak'
            return 'bisen-dspd True Peak (4x OS)'
          })(), isReal: !!bisen, search: '' },
      ],
    },
  ]

  const longTextRows = new Set(['About the Artist'])
  const summaryRow = c.wikiSummary
    ? { label: 'Album Notes', value: c.wikiSummary, isReal: true, search: `${c.albumTitle || ''} ${c.artistName || ''}` }
    : null

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="w-full max-w-md bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl overflow-hidden flex flex-col h-[540px]">

        {/* Header (Bisen: W icon + LISTENING WIKI) */}
        <div className="flex items-center justify-between px-4 py-3 bg-neutral-800 border-b border-neutral-700 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-gradient-to-br from-neutral-200 to-neutral-400 rounded flex items-center justify-center shadow-sm">
              <span className="text-[10px] font-black text-neutral-900">W</span>
            </div>
            <h2 className="text-sm font-bold tracking-tighter text-white uppercase">Listening Wiki</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-full transition-colors text-neutral-400 hover:text-white cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Switcher (People / Album / Signal) */}
        <div className="flex border-b border-white/5 bg-black/20 shrink-0">
          {sections.map((section, idx) => (
            <button
              key={idx}
              onClick={() => setActiveTab(idx)}
              className={`flex-1 flex items-center justify-center gap-2 py-3 transition-all ${
                activeTab === idx
                  ? 'bg-white/5 border-b-2 border-cyan-500 text-cyan-400'
                  : 'text-neutral-500 hover:text-neutral-300'
              }`}
            >
              {section.icon}
              <span className="text-[10px] font-black uppercase tracking-widest">{section.short}</span>
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <div className="flex items-center justify-center h-full">
              <span className="text-[11px] font-mono text-cyan-400 animate-pulse tracking-widest">
                SEARCHING MUSICBRAINZ · DISCOGS · WIKIPEDIA…
              </span>
            </div>
          )}
          {!loading && (
            <div className="space-y-4">
              {sections[activeTab].items.map((item, i) => {
                const isLong = longTextRows.has(item.label)
                return (
                  <div
                    key={i}
                    className="flex flex-col group cursor-pointer active:opacity-60 transition-opacity"
                    onClick={() => handleTap(item.search, item.isReal)}
                  >
                    <span className="text-[8px] font-bold text-neutral-600 uppercase mb-1">{item.label}</span>
                    <div className="flex items-start justify-between group-hover:bg-white/5 p-2 -mx-2 rounded transition-all border-b border-transparent group-hover:border-cyan-500/30">
                      <span className={`group-hover:text-cyan-300 transition-colors ${
                        isLong ? 'text-[11px] leading-snug' : 'text-sm'
                      } font-medium ${item.isReal ? 'text-neutral-200' : 'text-neutral-600 italic'}`}>
                        {item.value}
                      </span>
                      {item.isReal && (
                        <div className="flex items-center gap-1.5 opacity-20 group-hover:opacity-100 transition-opacity shrink-0 ml-2">
                          <Globe className="w-3.5 h-3.5 text-cyan-500" />
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
              {activeTab === 1 && summaryRow && (
                <div
                  className="flex flex-col group cursor-pointer active:opacity-60 transition-opacity"
                  onClick={() => handleTap(summaryRow.search, true)}
                >
                  <span className="text-[8px] font-bold text-neutral-600 uppercase mb-1">{summaryRow.label} · Wikipedia</span>
                  <div className="group-hover:bg-white/5 p-2 -mx-2 rounded transition-all border-b border-transparent group-hover:border-cyan-500/30">
                    <span className="text-[11px] leading-snug font-medium text-neutral-300 group-hover:text-cyan-300 transition-colors">
                      {summaryRow.value}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 bg-neutral-800/50 border-t border-neutral-700 flex flex-col items-center gap-2 shrink-0">
          <p className="text-[7px] text-neutral-600 uppercase tracking-widest italic">
            Live: MusicBrainz + Discogs + Wikipedia · Tap any row to explore
          </p>
          <button
            onClick={onClose}
            className="w-full py-2 bg-neutral-200 hover:bg-white text-neutral-900 rounded font-bold text-xs uppercase transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

