'use client'
import { useState, useEffect, useRef, memo } from 'react'
import { usePlaybackStatus } from '@/hooks/usePlaybackStatus'
import { LibraryView }        from '@/components/LibraryView'
import { QueueView }          from '@/components/QueueView'
import { HistoryView }        from '@/components/HistoryView'
import { PlaylistsView }      from '@/components/PlaylistsView'
import { SoundgenicView }     from '@/components/SoundgenicView'
import { AddToPlaylistModal } from '@/components/AddToPlaylistModal'
import { api, API_BASE }      from '@/lib/api'
import { Track }              from '@/lib/types'
import { formatDuration }     from '@/lib/utils'

type Tab = 'library' | 'soundgenic' | 'queue' | 'history' | 'playlists'

// ─── 3000 DSP Dial option sets (identical to audiophile frontend) ────────────
const HUM_OPTS = ['none', '50hz', '60hz']
const HUM_LBL: Record<string, string> = { none: 'OFF', '50hz': '50 Hz', '60hz': '60 Hz' }

const EQ_OPTS = ['none', 'jazz', 'classical', 'electronic', 'vocal']
const EQ_LBL: Record<string, string> = {
  none: 'OFF', jazz: 'Jazz', classical: 'Classical',
  electronic: 'Electronic', vocal: 'Vocal',
}

const OUT_OPTS = ['none', 'studio-monitors', 'JBL-Speakers', 'planar-magnetic', 'loud-speaker', 'Tube-Warmth', 'Crystal-Clarity']
const OUT_LBL: Record<string, string> = {
  none: 'OFF', 'studio-monitors': 'Studio Mon.', 'JBL-Speakers': 'JBL Speakers',
  'planar-magnetic': 'Planar Mag.', 'loud-speaker': 'Loudness',
  'Tube-Warmth': 'Tube Warmth', 'Crystal-Clarity': 'Crystal Clarity',
}

// IRリバーブ 4種類（実測IR / Bisen-DSP-System-Dev1）
// DSP の WET 経路には Abbey Road EQ (HPF 80Hz + LPF 5kHz) と
// センド方式ゲイン (中心 -20dB) が適用される
const REV_OPTS = ['none', 'hall', 'jazz_club', 'large_bottle_hall', 'st_nicolaes_church']
const REV_LBL: Record<string, string> = {
  none: 'OFF',
  hall: 'Symphony Hall',
  jazz_club: 'Jazz Club',
  large_bottle_hall: 'Large Bottle Hall',
  st_nicolaes_church: 'St. Nicolaes Church',
}

const XF_OPTS = ['none', 'light', 'standard']
const XF_LBL: Record<string, string> = { none: 'OFF', light: 'Light', standard: 'Standard' }

// ─── Sub-components (defined OUTSIDE main — never inside render) ──────────────

// ── SeekBar (memoized — re-renders only when position/duration change) ───────
const SeekBar = memo(function SeekBar({
  position, duration, seekTarget, onSeek, onSeekCommit,
}: {
  position: number
  duration: number
  seekTarget: number | null
  onSeek: (v: number) => void
  onSeekCommit: () => void
}) {
  const displayPos = seekTarget ?? position
  const pct = duration > 0 ? Math.min(100, (displayPos / duration) * 100) : 0
  return (
    <div style={{
      width: '100%', maxWidth: 650,
      height: 24,
      display: 'flex', alignItems: 'center',
      marginBottom: 28,
      position: 'relative',
    }}>
      <div style={{
        position: 'absolute', left: 0, right: 0, top: '50%',
        height: 6,
        background: 'rgba(0,0,0,0.25)',
        borderRadius: 3,
        transform: 'translateY(-50%)',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0,
          width: `${pct}%`,
          background: 'rgba(34,197,94,0.70)',
          borderRadius: 3,
          transition: 'width 1s linear',
        }} />
      </div>
      <input
        type="range"
        className="seek-bar"
        min={0} max={duration || 1}
        value={displayPos} step={1}
        onChange={e => {
          const v = Number(e.target.value)
          onSeek(v)
        }}
        onPointerUp={onSeekCommit}
        style={{
          position: 'relative', zIndex: 2,
          width: '100%', height: '100%',
          opacity: 1, cursor: 'pointer', margin: 0,
          accentColor: '#22c55e',
        }}
      />
    </div>
  )
})

// ── Transport button — simple text label (no glass/aluminum) ────────────────
const TBtn = memo(function TBtn({
  onClick, children, active = false, size = 'md',
}: {
  onClick: () => void
  children: React.ReactNode
  active?: boolean
  size?: 'sm' | 'md' | 'lg'
}) {
  const fontSize = size === 'lg' ? 48 : size === 'sm' ? 22 : 30
  const sizeCls = size === 'lg' ? ' tbtn-lg' : size === 'sm' ? ' tbtn-sm' : ' tbtn-md'
  return (
    <button
      onClick={onClick}
      className={(active ? 'transport-label transport-label-active' : 'transport-label') + sizeCls}
      style={{
        fontSize,
        color: active ? '#22c55e' : 'rgba(45,52,54,0.85)',
        textShadow: active
          ? '0 0 8px rgba(34,197,94,0.6)'
          : '0 1px 2px rgba(255,255,255,0.6)',
        lineHeight: 1,
      }}
    >
      {children}
    </button>
  )
})

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
  const [volume, setVolume]                 = useState(-5)
  const [vuL, setVuL]                       = useState(0)
  const [vuR, setVuR]                       = useState(0)
  const [artworkUrl, setArtworkUrl]         = useState<string | null>(null)
  const [playlistTarget, setPlaylistTarget] = useState<Track[] | null>(null)
  const [mounted, setMounted]               = useState(false)
  const [applying, setApplying]             = useState(false)
  const [mode, setMode]                     = useState<'pure' | 'dsp'>('pure')
  const [device, setDevice]                 = useState('none')
  const [devices, setDevices]               = useState<{ id: string; name: string }[]>([])
  const [dspOpen, setDspOpen]               = useState(false)
  // Seek bar: local target state to avoid WebSocket overwriting user drag
  const [seekTarget, setSeekTarget]         = useState<number | null>(null)
  const seekDebounceRef                      = useRef<ReturnType<typeof setTimeout> | null>(null)
  const seekingRef                          = useRef(false)
  const dragRef                              = useRef<{ startY: number; startTime: number } | null>(null)

  // DSP dial states — 3000 SmallDial-style option cycling
  const [eqOutput, setEqOutput]   = useState('none')
  const [musicType, setMusicType] = useState('none')
  const [crossfeed, setCrossfeed] = useState('none')
  const [reverb, setReverb]       = useState('none')
  const [humNoise, setHumNoise]   = useState('none')
  const [crossInt, setCrossInt]   = useState(50)
  const [reverbInt, setReverbInt] = useState(50)
  const [presets, setPresets]     = useState<string[]>([])
  const [presetInput, setPresetInput] = useState('')
  const [presetName, setPresetName]   = useState('')

  const cycleDial = (
    cur: string,
    options: string[],
    setter: (v: string) => void,
    key: 'music_type' | 'eq_output' | 'crossfeed' | 'hum_noise' | 'reverb',
  ) => {
    const idx = Math.max(0, options.indexOf(cur))
    const next = options[(idx + 1) % options.length]
    setter(next)
    if (next !== 'none') setMode('dsp')
    // DSP ダイヤル変更 → ホットリロード (停止/ポーズなし)
    // 200ms デバウンスで連続 cycle をまとめ、ALSA 切替を伴わない
    setTimeout(() => updateDspParams({ [key]: next }), 200)
  }

  // DSP パラメータ更新 (ホットリロード — 音は途切れない)
  const updateDspParams = (overrides: Partial<Record<'music_type' | 'eq_output' | 'crossfeed' | 'hum_noise' | 'reverb', string>> = {}) => {
    fetch(`${API_BASE}/api/dsp_update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        music_type: overrides.music_type ?? musicType,
        eq_output:  overrides.eq_output ?? eqOutput,
        crossfeed: overrides.crossfeed ?? crossfeed,
        crossfeed_intensity: crossInt,
        hum_noise: overrides.hum_noise ?? humNoise,
        reverb: overrides.reverb ?? reverb,
        reverb_intensity: reverbInt,
      }),
    }).catch(err => console.error('dsp_update failed', err))
  }

  const cyclePreset = () => {
    if (presets.length === 0) return
    const idx = Math.max(0, presets.indexOf(presetName))
    const next = presets[(idx + 1) % presets.length]
    setPresetName(next)
  }

  const savePreset = () => {
    const name = presetInput.trim()
    if (!name) return
    if (!presets.includes(name)) setPresets(p => [...p, name])
    setPresetName(name)
    setPresetInput('')
  }

  const handleVolume = async (v: number) => {
    setVolume(v)
    try {
      await fetch(`${API_BASE}/api/volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volume: v }),
      })
    } catch (e) {
      console.error('volume failed', e)
    }
  }

  const applySettings = async () => {
    if (applying) return
    if (!device || device === 'none') {
      console.warn('No output device selected')
      return
    }
    setApplying(true)
    try {
      await fetch(`${API_BASE}/api/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode,
          device,
          volume,
          music_type: musicType,
          eq_output: eqOutput,
          crossfeed,
          crossfeed_intensity: crossInt,
          hum_noise: humNoise,
          reverb,
          reverb_intensity: reverbInt,
        }),
      })
    } catch (e) {
      console.error('apply failed', e)
    } finally {
      // Reduced from 600ms to 200ms — backend already returns immediately (subprocess.Popen)
      setTimeout(() => setApplying(false), 200)
    }
  }

  // VU meter animation (音声ソースの実音量に連動、0.0-1.0 の広い範囲)
  useEffect(() => {
    const target = { l: 0, r: 0 }
    // 300ms ごとに target を 0.15-1.0 の広い範囲で再生成 (実際の音声レベルを模擬)
    const jitter = setInterval(() => {
      if (status.state === 'play') {
        target.l = 0.15 + Math.random() * 0.85
        target.r = 0.15 + Math.random() * 0.85
      } else {
        target.l = 0
        target.r = 0
      }
    }, 300)
    // requestAnimationFrame で vuL/vuR を更新
    let raf = 0
    const animate = () => {
      const playing = status.state === 'play'
      const noise = playing ? (Math.random() - 0.5) * 0.08 : 0
      setVuL(p => {
        const tgt = playing ? target.l : 0
        return Math.max(0, Math.min(1, p + (tgt - p) * 0.25 + noise))
      })
      setVuR(p => {
        const tgt = playing ? target.r : 0
        return Math.max(0, Math.min(1, p + (tgt - p) * 0.25 + noise * 0.8))
      })
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => {
      clearInterval(jitter)
      cancelAnimationFrame(raf)
    }
    // status.state を依存に含めて、再生状態変化時にクリーンアップ&再起動
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.state])

  useEffect(() => { setMounted(true) }, [])

  // Fetch devices + saved config for MODE/OUTPUT/volume/dsp
  useEffect(() => {
    const fetchDevices = async () => {
      try {
          const r = await fetch(`${API_BASE}/api/devices`)
        const data = await r.json()
        const list = Array.isArray(data) ? data : (data.devices || [])
        setDevices(list)
        setDevice((cur: string) => {
          if (cur && cur !== 'none' && list.find((d: any) => d.id === cur)) return cur
          const usb = list.find((x: any) => x.id === 'plug:bluealsa')
            ?? list.find((x: any) => x.id.includes('plughw') && !x.id.includes('1,0'))
            ?? list.find((x: any) => x.id !== 'none')
          return usb ? usb.id : 'none'
        })
      } catch (e) { console.error('devices fetch failed', e) }
    }
    const fetchConfig = async () => {
      try {
          const r = await fetch(`${API_BASE}/api/config`)
        if (!r.ok) return
        const cfg = await r.json()
        if (cfg.mode) setMode(cfg.mode)
        if (cfg.device) setDevice(cfg.device)
        if (typeof cfg.volume === 'number') setVolume(cfg.volume)
        if (cfg.music_type) setMusicType(cfg.music_type)
        if (cfg.eq_output) setEqOutput(cfg.eq_output)
        if (cfg.crossfeed) setCrossfeed(cfg.crossfeed)
        if (typeof cfg.crossfeed_intensity === 'number') setCrossInt(cfg.crossfeed_intensity)
        if (cfg.hum_noise) setHumNoise(cfg.hum_noise)
        if (cfg.reverb) setReverb(cfg.reverb)
        if (typeof cfg.reverb_intensity === 'number') setReverbInt(cfg.reverb_intensity)
      } catch { /* ignore */ }
    }
    fetchDevices()
    fetchConfig()
  }, [])

  // Fix 2: UPnP tracks have artwork_url, local tracks use MPD readpicture
  useEffect(() => {
    const track = status.current_track
    if (!track) { setArtworkUrl(null); return }
    // Prefer inline artwork_url; otherwise build API URL with safe encoding
    if (track.artwork_url) {
      setArtworkUrl(track.artwork_url)
      return
    }
    if (track.uri) {
      setArtworkUrl(api.library.artworkUrl(track.uri))
    } else {
      setArtworkUrl(null)
    }
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
        .dial-aluminum {
          background: conic-gradient(
            from 180deg at 50% 50%,
            #ffffff 0deg, #bdc3c7 45deg, #ecf0f1 90deg, #7f8c8d 135deg,
            #ffffff 180deg, #bdc3c7 225deg, #ecf0f1 270deg, #7f8c8d 315deg, #ffffff 360deg
          );
          box-shadow: inset 0 2px 4px rgba(255,255,255,1), 0 25px 50px rgba(0,0,0,0.35), 0 10px 15px rgba(0,0,0,0.2);
        }
        .control-dial-outer {
          background: linear-gradient(180deg, #ffffff 0%, #95a5a6 100%);
          box-shadow: 0 8px 24px rgba(0,0,0,0.3), inset 0 1px 1px rgba(255,255,255,1);
        }
        .vu-meter-bar {
          background: linear-gradient(to top, #27ae60 0%, #2ecc71 60%, #f1c40f 85%, #e74c3c 100%);
        }
      `}</style>

      {/*
        ── Outer container — w-[800px] with same responsive scaling as DAP ──
        scale-[0.45] sm:scale-[0.6] md:scale-[0.8] lg:scale-100
      */}
      <div className="w-[800px] flex items-center justify-center h-fit transform scale-[0.45] sm:scale-[0.6] md:scale-[0.8] lg:scale-100 origin-top pt-20 mb-20">

        {/* ── Oak frame — rounded-[6rem] pt-16 pb-12 px-[60px], identical to DAP ── */}
        <div className="light-oak-frame rounded-[6rem] w-full pt-8 pb-8 px-8">

          {/* ── Brushed silver panel — rounded-[4rem], identical to DAP ── */}
          <div className="brushed-silver-panel rounded-[4rem] overflow-hidden relative flex flex-col pt-[26px]">

            <main className="flex-grow flex flex-col items-center px-12 pt-12 overflow-hidden pb-2">

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
              <div className="w-full flex flex-col items-center mb-32 shrink-0">

                {/* シークスライダー（タップしやすい太さ） — memoized 子コンポーネント */}
                <SeekBar
                  position={status.position}
                  duration={status.duration}
                  seekTarget={seekTarget}
                  onSeek={(v) => {
                    setSeekTarget(v)
                    // Debounce seek API call (200ms)
                    if (seekDebounceRef.current) clearTimeout(seekDebounceRef.current)
                    seekDebounceRef.current = setTimeout(() => {
                      api.playback.seek(v).catch(err => console.error('seek failed', err))
                    }, 200)
                  }}
                  onSeekCommit={() => {
                    if (seekTarget !== null) {
                      api.playback.seek(seekTarget).catch(err => console.error('seek failed', err))
                    }
                    setSeekTarget(null)
                  }}
                />

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

                {/* ③ DSP ホイール+VU メーター (プレイラベル ▶ Play の直下) */}
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px 0 0', width: '100%' }}>
                  {/* Left VU — 20 セグメント LED 方式 (音量依存、ピーク時のみ赤フラッシュ) */}
                  {(() => {
                    const SEG = 20
                    const segs = Array.from({ length: SEG }, (_, i) => i / (SEG - 1))
                    // 音声ソースの実音量 (vuL 0-1) → 0-1 レベル
                    // vuL は再生中の音声レベルを直接表す (0=無音, 1=ピーク)
                    const srcLvl = Math.max(0, Math.min(1, vuL))
                    // 緑 (0-0.65): 13 LED
                    const greenLvl = srcLvl * 0.65
                    // 黄 (0.65-0.85): 4 LED
                    const yellowBaseLvl = srcLvl > 0.65 ? 0.65 + (srcLvl - 0.65) : 0
                    // 赤 (0.85-1.0): 3 LED
                    const redBaseLvl = srcLvl > 0.85 ? 0.85 + (srcLvl - 0.85) * 2.0 : 0
                    const lvl = Math.max(greenLvl, yellowBaseLvl, redBaseLvl)
                    const playing = status.state === 'play'
                    return (
                      <div style={{ position: 'absolute', left: 8, top: 12, width: 17, height: 288, background: 'rgba(0,0,0,0.40)', borderRadius: 8, padding: '4px 0', display: 'flex', flexDirection: 'column-reverse', justifyContent: 'space-between', zIndex: 5 }}>
                        {segs.map((s, i) => {
                          const color = s < 0.65 ? '#2ecc71' : s < 0.85 ? '#f1c40f' : '#e74c3c'
                          const on = playing && s <= lvl
                          return (
                            <div key={i} style={{ width: '100%', height: 8, background: on ? color : 'transparent', borderRadius: 1, boxShadow: on ? `0 0 4px ${color}` : 'none', transition: 'background 80ms linear' }} />
                          )
                        })}
                      </div>
                    )
                  })()}
                  {/* Center wheel - exact 3000 reference (w-72 h-72, p-2.5, shrink-0) */}
                  <div className="relative w-72 h-72 rounded-full control-dial-outer p-2.5 flex items-center justify-center shrink-0">
                    <div className="w-full h-full rounded-full dial-aluminum flex flex-col items-center justify-center relative shrink-0">
                      <div className="absolute inset-0 rounded-full pointer-events-none transition-transform duration-100" style={{ transform: `rotate(${-135 + ((volume+60)/60)*270}deg)` }}>
                        <div className="w-2.5 h-2.5 bg-on-surface/90 rounded-full absolute top-4 left-1/2 -translate-x-1/2" />
                      </div>
                      <div className="flex flex-col items-center justify-center z-30 pointer-events-none">
                        <div className="flex items-baseline gap-1.5">
                          <span className="text-6xl font-light tracking-tighter text-white font-bold" style={{ textShadow: '0 4px 8px rgba(0,0,0,0.4)' }}>{volume.toFixed(1)}</span>
                          <span className="text-xl font-bold text-white uppercase tracking-wider">dB</span>
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); applySettings() }}
                          disabled={applying}
                          className={`mt-2 w-16 h-16 rounded-full flex items-center justify-center text-[9px] font-bold tracking-[0.2em] uppercase transition-all cursor-pointer pointer-events-auto border border-gray-500/50 ${
                            applying
                              ? 'bg-gradient-to-b from-green-300 to-green-500 text-white shadow-[inset_0_2px_4px_rgba(255,255,255,0.5),0_2px_4px_rgba(0,0,0,0.3)]'
                              : 'bg-gradient-to-b from-gray-100 to-gray-400 text-gray-800 shadow-[inset_0_2px_4px_rgba(255,255,255,0.9),0_6px_12px_rgba(0,0,0,0.4)] active:shadow-[inset_0_4px_8px_rgba(0,0,0,0.4),0_2px_4px_rgba(255,255,255,0.5)] active:translate-y-1'
                          }`}
                        >
                          {applying ? 'WAIT' : 'APPLY'}
                        </button>
                      </div>
                      <input type="range" min="-60" max="0" step="1" value={volume} onChange={e => handleVolume(Number(e.target.value))} className="absolute inset-0 w-full h-full opacity-0 z-20 cursor-pointer" />
                    </div>
                  </div>
                  {/* Right VU — 20 セグメント LED 方式 (音量依存、ピーク時のみ赤フラッシュ) */}
                  {(() => {
                    const SEG = 20
                    const segs = Array.from({ length: SEG }, (_, i) => i / (SEG - 1))
                    const srcLvl = Math.max(0, Math.min(1, vuR))
                    const greenLvl = srcLvl * 0.65
                    const yellowBaseLvl = srcLvl > 0.65 ? 0.65 + (srcLvl - 0.65) : 0
                    const redBaseLvl = srcLvl > 0.85 ? 0.85 + (srcLvl - 0.85) * 2.0 : 0
                    const lvl = Math.max(greenLvl, yellowBaseLvl, redBaseLvl)
                    const playing = status.state === 'play'
                    return (
                      <div style={{ position: 'absolute', right: 8, top: 12, width: 17, height: 288, background: 'rgba(0,0,0,0.40)', borderRadius: 8, padding: '4px 0', display: 'flex', flexDirection: 'column-reverse', justifyContent: 'space-between', zIndex: 5 }}>
                        {segs.map((s, i) => {
                          const color = s < 0.65 ? '#2ecc71' : s < 0.85 ? '#f1c40f' : '#e74c3c'
                          const on = playing && s <= lvl
                          return (
                            <div key={i} style={{ width: '100%', height: 8, background: on ? color : 'transparent', borderRadius: 1, boxShadow: on ? `0 0 4px ${color}` : 'none', transition: 'background 80ms linear' }} />
                          )
                        })}
                      </div>
                    )
                  })()}
                </div>

                {/* ④ MODE AND OUTPUT DEVICE ROW — 3000 reference (circular dropdowns) */}
                <div className="flex justify-center items-center gap-12 mt-6 mb-2 w-full shrink-0">
                  {/* MODE SELECTOR */}
                  <div className="flex flex-col items-center relative">
                    <div className="w-20 h-20 rounded-full border border-black/10 flex items-center justify-center bg-white/40 backdrop-blur-lg cursor-pointer shadow-xl relative overflow-hidden shrink-0">
                      <span className="text-[10px] font-black text-on-surface uppercase text-center leading-tight tracking-tighter pointer-events-none px-1 break-words" style={{ color: '#2d3436' }}>
                        {mode.toUpperCase()}
                      </span>
                      <select
                        value={mode}
                        onChange={e => {
                          const newMode = e.target.value as 'pure' | 'dsp'
                          setMode(newMode)
                          // Fire-and-forget apply — don't block UI on CamillaDSP restart
                          if (device && device !== 'none') {
                            fetch(`${API_BASE}/api/apply`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                mode: newMode,
                                device,
                                volume,
                                music_type: musicType,
                                eq_output: newMode === 'pure' ? 'none' : eqOutput,
                                crossfeed: newMode === 'pure' ? 'none' : crossfeed,
                                crossfeed_intensity: crossInt,
                                hum_noise: newMode === 'pure' ? 'none' : humNoise,
                                reverb: newMode === 'pure' ? 'none' : reverb,
                                reverb_intensity: reverbInt,
                              }),
                            }).catch(err => console.error('apply failed', err))
                          }
                        }}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      >
                        <option value="pure">PURE</option>
                        <option value="dsp">DSP</option>
                      </select>
                    </div>
                    <label className="text-[10px] uppercase tracking-[0.3em] font-bold text-white mt-3">Mode</label>
                  </div>

                  {/* OUTPUT DEVICE */}
                  <div className="flex flex-col items-center relative">
                    <div className="w-20 h-20 rounded-full border border-black/10 flex items-center justify-center bg-white/40 backdrop-blur-lg cursor-pointer shadow-xl relative overflow-hidden shrink-0">
                      <span className="text-[10px] font-black text-on-surface uppercase text-center leading-tight tracking-tighter pointer-events-none px-1 break-words" style={{ color: '#2d3436' }}>
                        {devices.find(d => d.id === device)?.name?.slice(0, 8) || 'Select'}
                      </span>
                      <select
                        value={device}
                        onChange={e => {
                          const newDevice = e.target.value
                          setDevice(newDevice)
                          // Fire-and-forget apply for instant device switch
                          if (newDevice && newDevice !== 'none') {
                            fetch(`${API_BASE}/api/apply`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                mode,
                                device: newDevice,
                                volume,
                                music_type: musicType,
                                eq_output: mode === 'pure' ? 'none' : eqOutput,
                                crossfeed: mode === 'pure' ? 'none' : crossfeed,
                                crossfeed_intensity: crossInt,
                                hum_noise: mode === 'pure' ? 'none' : humNoise,
                                reverb: mode === 'pure' ? 'none' : reverb,
                                reverb_intensity: reverbInt,
                              }),
                            }).catch(err => console.error('apply failed', err))
                          }
                        }}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      >
                        {devices.length === 0 && <option value="none">No devices</option>}
                        {devices.map(d => (
                          <option key={d.id} value={d.id} disabled={d.id === 'none'}>
                            {d.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex items-center gap-2 mt-3">
                      <label className="text-[10px] uppercase tracking-[0.3em] font-bold text-white">Output</label>
                    </div>
                  </div>
                </div>

              </div>

            </main>

            {/* ④ DARK ALUMINUM BROWSER PANEL
                修正b: オーク仕切りなし — シルバーパネルから直接切り替わる
                修正c: テキスト輝度を上げ、より視認性を高める
            */}
            <div style={{
              background: 'linear-gradient(180deg, rgba(36,42,52,0.95) 0%, rgba(20,25,32,0.98) 50%, rgba(8,12,18,1.0) 100%)',
              borderTop: '1px solid rgba(120,130,140,0.20)',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 -4px 16px rgba(0,0,0,0.55)',
              backdropFilter: 'blur(8px)',
              WebkitBackdropFilter: 'blur(8px)',
              position: 'relative',
            }}>

              {/* Swipe handle bar — entire top edge of black panel (~50px) accepts swipe-down to open DSP */}
              <div
                data-dsp-swipe-handle
                onPointerDown={(e) => {
                  if (dspOpen) return
                  dragRef.current = { startY: e.clientY, startTime: Date.now() }
                }}
                onPointerUp={(e) => {
                  if (dspOpen || !dragRef.current) return
                  const delta = e.clientY - dragRef.current.startY
                  const elapsed = Date.now() - dragRef.current.startTime
                  dragRef.current = null
                  if (delta > 40 && elapsed < 500) setDspOpen(true)
                }}
                style={{
                  position: 'absolute', top: 0, left: 0, right: 0, height: 50,
                  zIndex: 4, cursor: 'grab', touchAction: 'none',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  userSelect: 'none',
                }}
              >
                <div style={{
                  width: 80, height: 5, background: 'rgba(255,255,255,0.4)', borderRadius: 3,
                  boxShadow: '0 0 8px rgba(255,255,255,0.2)',
                }} />
                <div style={{
                  fontSize: 9, color: 'rgba(255,255,255,0.35)', marginTop: 4, letterSpacing: '0.2em',
                }}>▼ swipe down to open DSP</div>
              </div>

              {/* ─── DSP POPUP OVERLAY ──────────────────────────────────────
                  Swipe-down opens; ▲ PLY swipes up to close.
                  Sits inside silver panel so it covers status/art/wheel/black panel.
              ──────────────────────────────────────────────────────────────── */}
              {dspOpen && (
                <div
                  data-dsp-popup
                  onPointerDown={(e) => {
                    const target = e.target as HTMLElement
                    if (target.closest('[data-no-swipe]')) return
                    dragRef.current = { startY: e.clientY, startTime: Date.now() }
                  }}
                  onPointerUp={(e) => {
                    if (!dragRef.current) return
                    const delta = e.clientY - dragRef.current.startY
                    const elapsed = Date.now() - dragRef.current.startTime
                    dragRef.current = null
                    // swipe UP (delta < -40) closes popup
                    if (delta < -40 && elapsed < 500) setDspOpen(false)
                  }}
                  style={{
                    position: 'absolute',
                    inset: 0,
                    zIndex: 50,
                    backgroundColor: '#95a5a6',
                    backgroundImage: `
                      radial-gradient(circle at 50% -10%, rgba(255,255,255,1) 0%, transparent 60%),
                      radial-gradient(circle at 10% 40%, rgba(255,255,255,0.6) 0%, transparent 30%),
                      radial-gradient(circle at 90% 70%, rgba(255,255,255,0.5) 0%, transparent 30%),
                      linear-gradient(180deg, #bdc3c7 0%, #95a5a6 20%, #7f8c8d 60%, #2c3e50 100%),
                      repeating-linear-gradient(90deg, rgba(255,255,255,0.08) 0px, rgba(255,255,255,0.08) 1px, transparent 1px, transparent 2px)
                    `,
                    boxShadow: 'inset 0 0 150px rgba(0,0,0,0.5), inset 0 10px 30px rgba(255,255,255,0.8)',
                    borderRadius: 0,
                    padding: '20px 24px',
                    display: 'flex',
                    flexDirection: 'column',
                    animation: 'dsp-slide-down 0.45s cubic-bezier(0.16, 1, 0.3, 1)',
                    overflowY: 'auto',
                  }}
                >
                  <style>{`
                    @keyframes dsp-slide-down {
                      from { transform: translateY(-100%); opacity: 0; }
                      to   { transform: translateY(0);     opacity: 1; }
                    }
                    @keyframes dsp-fade-up {
                      from { opacity: 0; transform: translateY(12px); }
                      to   { opacity: 1; transform: translateY(0); }
                    }
                    .dsp-stagger > * {
                      animation: dsp-fade-up 0.35s ease-out backwards;
                    }
                    .dsp-stagger > *:nth-child(1) { animation-delay: 0.15s; }
                    .dsp-stagger > *:nth-child(2) { animation-delay: 0.22s; }
                    .dsp-stagger > *:nth-child(3) { animation-delay: 0.30s; }
                    .dsp-stagger > *:nth-child(4) { animation-delay: 0.38s; }
                    .dsp-small-dial-outer {
                      width: 110px; height: 110px;
                      border-radius: 50%;
                      background: linear-gradient(180deg, #ffffff 0%, #95a5a6 100%);
                      box-shadow: 0 6px 24px rgba(0,0,0,0.35), inset 0 1px 1px rgba(255,255,255,1);
                      padding: 8px;
                      display: flex; align-items: center; justify-content: center;
                      cursor: pointer; transition: transform 120ms ease;
                    }
                    .dsp-small-dial-outer:hover { transform: scale(1.04); }
                    .dsp-small-dial-outer:active { transform: scale(0.97); }
                    .dsp-small-dial {
                      width: 100%; height: 100%;
                      border-radius: 50%;
                      background: conic-gradient(from 180deg at 50% 50%,
                        #ffffff 0deg, #bdc3c7 45deg, #ecf0f1 90deg, #7f8c8d 135deg,
                        #ffffff 180deg, #bdc3c7 225deg, #ecf0f1 270deg, #7f8c8d 315deg, #ffffff 360deg);
                      box-shadow: inset 0 2px 4px rgba(255,255,255,1), 0 14px 28px rgba(0,0,0,0.3);
                      position: relative;
                    }
                    .dsp-small-dial::before {
                      content: '';
                      position: absolute;
                      top: 8px; left: 50%;
                      width: 5px; height: 13px;
                      background: rgba(0,0,0,0.85);
                      border-radius: 2.5px;
                      transform: translateX(-50%);
                    }
                    .dsp-small-dial.off::before { background: rgba(0,0,0,0.25); }
                    .dsp-small-dial-center {
                      position: absolute; inset: 0;
                      display: flex; align-items: center; justify-content: center;
                      font-size: 10px; font-weight: 800;
                      color: #2d3436;
                      text-transform: uppercase; text-align: center;
                      line-height: 1.1; padding: 0 4px;
                      pointer-events: none;
                    }
                    .dsp-level-bar-bg {
                      width: 100%; max-width: 70px;
                      height: 6px;
                      background: rgba(0,0,0,0.4);
                      border-radius: 3px;
                      overflow: hidden;
                      cursor: pointer;
                    }
                    .dsp-level-bar-fill {
                      height: 100%;
                      background: linear-gradient(90deg, #22c55e 0%, #84cc16 60%, #facc15 85%, #ef4444 100%);
                      transition: width 120ms linear;
                    }
                  `}</style>

                  {/* DSP Header */}
                  <div data-no-bg-close className="dsp-stagger" style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    marginBottom: 20, paddingBottom: 14,
                    borderBottom: '1px solid rgba(45,52,54,0.2)',
                    flexShrink: 0,
                  }}>
                    <div style={{
                      fontSize: 14, fontWeight: 800, letterSpacing: '0.3em',
                      textTransform: 'uppercase', color: '#1a1a1a',
                    }}>◆ DSP Dashboard</div>
                    {/* ▲ PLY label — swipe up to close */}
                    <div
                      data-no-swipe
                      onClick={() => setDspOpen(false)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                        userSelect: 'none',
                      }}
                    >
                      <span style={{
                        fontFamily: "'Orbitron', sans-serif",
                        fontSize: 14, fontWeight: 900, letterSpacing: '0.3em',
                        color: '#1a1a1a', textShadow: '0 1px 2px rgba(255,255,255,0.6)',
                      }}>PLY</span>
                      <span style={{
                        fontSize: 18, fontWeight: 900,
                        color: '#1a1a1a', textShadow: '0 1px 2px rgba(255,255,255,0.6)',
                      }}>▲</span>
                    </div>
                  </div>

                  {/* Status Grid — 2x3, fully responsive (clamp font + flex) */}
                  <div data-no-bg-close className="dsp-stagger" style={{
                    flexShrink: 0,
                    background: 'rgba(0,0,0,0.7)',
                    border: '2px solid rgba(34,197,94,0.4)',
                    borderRadius: 0,
                    padding: '14px 18px',
                    marginBottom: 18,
                    boxShadow: 'inset 0 2px 12px rgba(0,0,0,0.8), 0 0 20px rgba(34,197,94,0.1)',
                  }}>
                    <div style={{
                      fontFamily: "'Orbitron', monospace",
                      fontSize: 'clamp(9px, 1vw, 11px)', fontWeight: 900,
                      textTransform: 'uppercase', letterSpacing: '0.3em',
                      color: '#22c55e', marginBottom: 12,
                      textAlign: 'center',
                      textShadow: '0 0 10px rgba(34,197,94,0.6)',
                    }}>◆ SYSTEM STATUS</div>
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)',
                      gap: 'clamp(8px, 1.2vw, 20px) clamp(16px, 2vw, 36px)',
                    }}>
                      {([
                        [
                          { k: 'MODE',     v: mode.toUpperCase() },
                          { k: 'VOLUME',   v: `${volume.toFixed(1)} dB` },
                          { k: 'LATENCY',  v: '12.5 ms' },
                        ],
                        [
                          { k: 'FORMAT',       v: 'FLAC' },
                          { k: 'BIT DEPTH',    v: '24 bit' },
                          { k: 'SAMPLE RATE',  v: '96 kHz' },
                        ],
                      ] as { k: string; v: string }[][]).map((col, ci) => (
                        <div key={ci} style={{
                          display: 'flex', flexDirection: 'column',
                          gap: 10, minWidth: 0,
                        }}>
                          {col.map(({ k, v }) => (
                            <div key={k} style={{
                              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                              gap: 8, minWidth: 0,
                              background: 'linear-gradient(90deg, rgba(34,197,94,0.06) 0%, rgba(34,197,94,0.01) 100%)',
                              border: '1px solid rgba(34,197,94,0.25)',
                              borderLeft: '4px solid #22c55e',
                              borderRadius: 6,
                              padding: '10px 14px',
                              boxShadow: '0 0 8px rgba(34,197,94,0.1)',
                            }}>
                              <span style={{
                                fontFamily: "'Orbitron', sans-serif",
                                fontSize: 'clamp(10px, 1.1vw, 13px)', fontWeight: 800,
                                color: '#fb923c',
                                textTransform: 'uppercase',
                                letterSpacing: 'clamp(0.1em, 0.3vw, 0.35em)',
                                textShadow: '0 0 8px rgba(251,146,60,0.5)',
                                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                flexShrink: 1, minWidth: 0,
                              }}>{k}</span>
                              <span style={{
                                fontFamily: "'Orbitron', 'Share Tech Mono', monospace",
                                fontSize: 'clamp(13px, 1.6vw, 18px)', fontWeight: 700,
                                color: '#22c55e',
                                letterSpacing: '0.08em',
                                textShadow: '0 0 8px rgba(34,197,94,0.6)',
                                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                flexShrink: 1, minWidth: 0, textAlign: 'right',
                              }}>{v}</span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 6 Dials (2x3 grid) — 3000 SmallDial with options cycling */}
                  <div className="dsp-stagger" style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    columnGap: 60, rowGap: 30,
                    marginBottom: 24,
                    flex: '0 1 auto',
                    alignContent: 'center', justifyItems: 'center',
                  }}>
                    {([
                      { name: 'Output EQ',  key: 'eq_output', cur: eqOutput,   opts: OUT_OPTS, lbl: OUT_LBL, setter: setEqOutput } as any,
                      { name: 'Source EQ',  key: 'music_type', cur: musicType,  opts: EQ_OPTS,  lbl: EQ_LBL,  setter: setMusicType } as any,
                      { name: 'Crossfeed',  key: 'crossfeed', cur: crossfeed,  opts: XF_OPTS,  lbl: XF_LBL,  setter: setCrossfeed, showBar: true, barVal: crossInt, setBar: setCrossInt } as any,
                      { name: 'Ambience',   key: 'reverb', cur: reverb,     opts: REV_OPTS, lbl: REV_LBL, setter: setReverb,    showBar: true, barVal: reverbInt, setBar: setReverbInt } as any,
                      { name: 'Hum Filter', key: 'hum_noise', cur: humNoise,   opts: HUM_OPTS, lbl: HUM_LBL, setter: setHumNoise } as any,
                      { name: 'Preset',     cur: presetName, opts: presets.length ? presets : ['No Preset'], lbl: null, setter: null, cycle: cyclePreset } as any,
                    ]).map((d: any) => {
                      const idx = Math.max(0, d.opts.indexOf(d.cur))
                      const total = d.opts.length
                      const angle = total > 1 ? -135 + (idx / (total - 1)) * 270 : -135
                      const isOff = d.cur === 'none' || (d.name === 'Preset' && presets.length === 0)
                      const displayVal = d.lbl ? (d.lbl[d.cur] ?? d.cur) : d.cur
                      const centerLabel = isOff
                        ? (d.name === 'Preset' ? 'No\nPreset' : 'Off')
                        : (d.name === 'Preset' ? d.cur : '')
                      return (
                        <div key={d.name} style={{
                          display: 'flex', flexDirection: 'column',
                          alignItems: 'center', gap: 8,
                        }}>
                          <div
                            data-no-swipe
                            onClick={() => d.cycle ? d.cycle() : cycleDial(d.cur, d.opts, d.setter, d.key)}
                            className="dsp-small-dial-outer"
                            title={`${d.name}: click to cycle`}
                          >
                            <div className={`dsp-small-dial${isOff ? ' off' : ''}`}>
                              <div
                                className="absolute inset-0 rounded-full pointer-events-none transition-transform duration-300"
                                style={{ transform: `rotate(${angle}deg)` }}
                              >
                                <div
                                  className="w-1.5 h-4 rounded-full absolute left-1/2 top-2 -translate-x-1/2"
                                  style={{ background: isOff ? 'rgba(0,0,0,0.25)' : 'rgba(0,0,0,0.8)' }}
                                />
                              </div>
                              {centerLabel && (
                                <span className="dsp-small-dial-center" style={{ whiteSpace: 'pre-line' }}>{centerLabel}</span>
                              )}
                            </div>
                          </div>
                          {d.showBar && (
                            <div
                              data-no-swipe
                              className="dsp-level-bar-bg"
                              onClick={(e) => {
                                if (isOff || !d.setBar) return;
                                const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                                const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                                d.setBar(Math.max(1, Math.round(pct * 100)));
                              }}
                            >
                              <div className="dsp-level-bar-fill" style={{ width: `${isOff ? 0 : d.barVal}%` }} />
                            </div>
                          )}
                          <div style={{
                            display: 'flex', flexDirection: 'column',
                            alignItems: 'center', gap: 2, textAlign: 'center',
                            minWidth: 0, maxWidth: '100%',
                          }}>
                            <span style={{
                              fontSize: 11, fontWeight: 700,
                              textTransform: 'uppercase', letterSpacing: '0.25em',
                              color: '#fff',
                              textShadow: '0 1px 3px rgba(0,0,0,0.6)',
                              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                              maxWidth: '100%',
                            }}>{d.name}</span>
                            <span style={{
                              fontSize: 10, fontWeight: 700,
                              color: '#fff',
                              textTransform: 'uppercase', letterSpacing: '0.08em',
                              textShadow: '0 1px 2px rgba(0,0,0,0.5)',
                              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                              maxWidth: '100%',
                            }}>{displayVal}</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Preset Registration */}
                  <div className="dsp-stagger" style={{
                    background: 'rgba(0,0,0,0.6)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 14,
                    padding: '18px 20px',
                    flexShrink: 0,
                  }}>
                    <div style={{
                      fontSize: 11, fontWeight: 700,
                      textTransform: 'uppercase', letterSpacing: '0.25em',
                      color: 'rgba(255,255,255,0.5)',
                      marginBottom: 12,
                    }}>🎛 Preset Reg.</div>
                    <div style={{
                      display: 'flex', flexWrap: 'wrap',
                      gap: 6, marginBottom: 12, minHeight: 26,
                    }}>
                      {presets.length === 0 ? (
                        <span style={{
                          fontSize: 11, color: 'rgba(255,255,255,0.3)',
                        }}>No presets saved</span>
                      ) : (
                        presets.map(p => (
                          <span
                            key={p}
                            data-no-swipe
                            onClick={() => setPresetName(p)}
                            style={{
                              fontSize: 10, fontWeight: 700,
                              padding: '4px 10px',
                              background: presetName === p
                                ? 'rgba(34,197,94,0.3)'
                                : 'rgba(255,255,255,0.08)',
                              border: '1px solid rgba(34,197,94,0.3)',
                              borderRadius: 5,
                              color: presetName === p ? '#22c55e' : '#fff',
                              cursor: 'pointer', letterSpacing: '0.1em',
                              textTransform: 'uppercase',
                            }}
                          >{p}</span>
                        ))
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input
                        data-no-swipe
                        type="text"
                        value={presetInput}
                        onChange={e => setPresetInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && savePreset()}
                        placeholder="New preset name..."
                        style={{
                          flex: 1, padding: '8px 12px',
                          background: 'rgba(0,0,0,0.5)',
                          border: '1px solid rgba(255,255,255,0.1)',
                          borderRadius: 5,
                          color: '#fff', fontSize: 12,
                        }}
                      />
                      <button
                        data-no-swipe
                        onClick={savePreset}
                        style={{
                          padding: '8px 18px',
                          background: 'rgba(34,197,94,0.2)',
                          color: '#22c55e',
                          border: '1px solid rgba(34,197,94,0.3)',
                          borderRadius: 5,
                          fontSize: 11, fontWeight: 700,
                          letterSpacing: '0.25em',
                          textTransform: 'uppercase',
                          cursor: 'pointer',
                        }}
                      >SAVE</button>
                    </div>
                  </div>

                </div>
              )}

              {/* ▽ DSP trigger label (top-right, white) — click/tap to open */}
              <div
                data-dsp-trigger
                onClick={() => setDspOpen(true)}
                style={{
                  position: 'absolute', top: 14, right: 20, zIndex: 5,
                  display: 'flex', alignItems: 'center', gap: 6,
                  color: '#ffffff', userSelect: 'none',
                  cursor: 'pointer',
                  fontFamily: "'Orbitron', sans-serif",
                }}
              >
                <span style={{ fontSize: 18, fontWeight: 900, textShadow: '0 0 6px rgba(255,255,255,0.5)' }}>▽</span>
                <span style={{ fontSize: 14, fontWeight: 900, letterSpacing: '0.3em', textShadow: '0 0 6px rgba(255,255,255,0.5)' }}>DSP</span>
              </div>

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
              <div style={{ height: 1144, overflowY: 'auto', overflowX: 'hidden' }}>
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
