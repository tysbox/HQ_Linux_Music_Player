'use client'
import React, { useState, useEffect, useRef, memo } from 'react'
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

type Tab = 'queue' | 'library' | 'soundgenic' | 'history' | 'playlists'

// ─── Option sets ─────────────────────────────────────────────────────────────
const HUM_OPTS = ['none', '50hz', '60hz']
const HUM_LBL: Record<string, string> = { none: 'OFF', '50hz': '50 Hz', '60hz': '60 Hz' }

const EQ_SRC_OPTS = ['none', 'jazz', 'classical', 'electronic', 'vocal']
const EQ_SRC_LBL: Record<string, string> = {
  none: 'OFF', jazz: 'Jazz', classical: 'Classical',
  electronic: 'Electronic', vocal: 'Vocal',
}

const EQ_OUT_OPTS = ['none', 'studio-monitors', 'JBL-Speakers', 'planar-magnetic', 'loud-speaker', 'Tube-Warmth', 'Crystal-Clarity']
const EQ_OUT_LBL: Record<string, string> = {
  none: 'OFF', 'studio-monitors': 'Studio Mon.', 'JBL-Speakers': 'JBL Speakers',
  'planar-magnetic': 'Planar Mag.', 'loud-speaker': 'Loudness',
  'Tube-Warmth': 'Tube Warmth', 'Crystal-Clarity': 'Crystal Clarity',
}

const REV_OPTS = ['none', 'hall', 'jazz_club', 'large_bottle_hall', 'st_nicolaes_church']
const REV_LBL: Record<string, string> = {
  none: 'OFF', hall: 'Symphony Hall', jazz_club: 'Jazz Club',
  large_bottle_hall: 'Large Bottle Hall', st_nicolaes_church: 'St. Nicolaes Church',
}

const XF_OPTS = ['none', 'light', 'standard']
const XF_LBL: Record<string, string> = { none: 'OFF', light: 'Light', standard: 'Standard' }

// ─── SeekBar Subcomponent (Memoized) ──────────────────────────────────────────
const SeekBar = memo(function SeekBar({
  position,
  duration,
  seekTarget,
  onSeek,
  onSeekCommit,
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
    <div className="w-full space-y-1 my-1">
      <div className="relative w-full h-2 bg-black/60 rounded-full overflow-hidden border border-white/10 flex items-center">
        <div className="h-full bg-emerald-500 rounded-full transition-all duration-200" style={{ width: `${pct}%` }} />
        <input
          type="range"
          min={0}
          max={duration || 1}
          value={displayPos}
          step={1}
          onChange={(e) => onSeek(Number(e.target.value))}
          onPointerUp={onSeekCommit}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
        />
      </div>
      <div className="flex justify-between text-[10px] font-mono text-white/50 px-0.5">
        <span>{formatDuration(displayPos)}</span>
        <span>{formatDuration(duration) || '--:--'}</span>
      </div>
    </div>
  )
})

export default function page() {
  const { status, wsState } = usePlaybackStatus()
  const [mounted, setMounted] = useState(false)

  // Navigation & Modal State
  const [activeTab, setActiveTab] = useState<Tab>('queue')
  const [playlistTarget, setPlaylistTarget] = useState<Track[] | null>(null)
  const [dspOpen, setDspOpen] = useState(false)

  // Output & Hardware State
  const [device, setDevice] = useState('none')
  const [devices, setDevices] = useState<{ id: string; name: string }[]>([])
  const [mode, setMode] = useState<'pure' | 'dsp'>('dsp')
  const [volume, setVolume] = useState(-5.0)
  const [applying, setApplying] = useState(false)
  const [artworkUrl, setArtworkUrl] = useState<string | null>(null)

  // Seek Debounce Ref
  const [seekTarget, setSeekTarget] = useState<number | null>(null)
  const seekDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // DSP Controls State
  const [eqOutput, setEqOutput] = useState('none')
  const [musicType, setMusicType] = useState('none')
  const [humFilter, setHumFilter] = useState('none')
  const [ambience, setAmbience] = useState('none')
  const [ambienceIntensity, setAmbienceIntensity] = useState(50)
  const [crossfeed, setCrossfeed] = useState('none')
  const [crossfeedIntensity, setCrossfeedIntensity] = useState(50)
  const [presetName, setPresetName] = useState('LateNight')
  const [presetInput, setPresetInput] = useState('')
  const [presets, setPresets] = useState<string[]>(['LateNight', 'Studio Ref', 'Triode Warmth'])

  // VU Levels
  const [vuL, setVuL] = useState(0)
  const [vuR, setVuR] = useState(0)

  useEffect(() => {
    setMounted(true)
  }, [])

  // Dynamic Ballistic VU jitter
  useEffect(() => {
    const target = { l: 0, r: 0 }
    const jitter = setInterval(() => {
      if (status.state === 'play') {
        target.l = 0.2 + Math.random() * 0.75
        target.r = 0.2 + Math.random() * 0.75
      } else {
        target.l = 0
        target.r = 0
      }
    }, 180)

    let raf = 0
    const animate = () => {
      const playing = status.state === 'play'
      const noise = playing ? (Math.random() - 0.5) * 0.05 : 0
      setVuL((p) => {
        const tgt = playing ? target.l : 0
        return Math.max(0, Math.min(1, p + (tgt - p) * 0.22 + noise))
      })
      setVuR((p) => {
        const tgt = playing ? target.r : 0
        return Math.max(0, Math.min(1, p + (tgt - p) * 0.22 + noise * 0.9))
      })
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => {
      clearInterval(jitter)
      cancelAnimationFrame(raf)
    }
  }, [status.state])

  // Fetch audio devices & initial CamillaDSP config
  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const data = await api.dsp.devices()
        const list = Array.isArray(data) ? data : (data as any).devices || []
        setDevices(list)
        setDevice((cur) => {
          if (cur && cur !== 'none' && list.find((d: any) => d.id === cur)) return cur
          const preferred =
            list.find((x: any) => x.id === 'plug:bluealsa') ??
            list.find((x: any) => x.id.includes('plughw') && !x.id.includes('1,0')) ??
            list.find((x: any) => x.id !== 'none')
          return preferred ? preferred.id : 'none'
        })
      } catch (e) {
        console.error('Failed to fetch devices', e)
      }
    }
    const fetchConfig = async () => {
      try {
        const cfg = await api.dsp.config() as any
        if (cfg.mode) setMode(cfg.mode)
        if (cfg.device) setDevice(cfg.device)
        if (typeof cfg.volume === 'number') setVolume(cfg.volume)
        if (cfg.music_type) setMusicType(cfg.music_type)
        if (cfg.eq_output) setEqOutput(cfg.eq_output)
        if (cfg.crossfeed) setCrossfeed(cfg.crossfeed)
        if (typeof cfg.crossfeed_intensity === 'number') setCrossfeedIntensity(cfg.crossfeed_intensity)
        if (cfg.hum_noise) setHumFilter(cfg.hum_noise)
        if (cfg.reverb) setAmbience(cfg.reverb)
        if (typeof cfg.reverb_intensity === 'number') setAmbienceIntensity(cfg.reverb_intensity)
      } catch (e) {
        console.warn('Initial DSP config not loaded yet', e)
      }
    }
    fetchDevices()
    fetchConfig()
  }, [])

  // Resolve artwork
  useEffect(() => {
    const t = status.current_track
    if (!t) {
      setArtworkUrl(null)
      return
    }
    if (t.artwork_url) {
      setArtworkUrl(t.artwork_url)
    } else if (t.uri) {
      setArtworkUrl(api.library.artworkUrl(t.uri))
    } else {
      setArtworkUrl(null)
    }
  }, [status.current_track])

  // Volume handler
  const handleVolume = async (v: number) => {
    setVolume(v)
    try {
      await api.dsp.setVolume(v)
    } catch (e) {
      console.error('Failed to set volume', e)
    }
  }

  // Hot-reload DSP parameter update
  const syncDspParams = (params: {
    music_type?: string
    eq_output?: string
    crossfeed?: string
    crossfeed_intensity?: number
    hum_noise?: string
    reverb?: string
    reverb_intensity?: number
  }) => {
    api.dsp.updateDspParams({
      music_type: params.music_type ?? musicType,
      eq_output: params.eq_output ?? eqOutput,
      crossfeed: params.crossfeed ?? crossfeed,
      crossfeed_intensity: params.crossfeed_intensity ?? crossfeedIntensity,
      hum_noise: params.hum_noise ?? humFilter,
      reverb: params.reverb ?? ambience,
      reverb_intensity: params.reverb_intensity ?? ambienceIntensity,
    }).catch(err => console.error('DSP params update failed', err))
  }

  // Cycle dial and trigger hot-reload
  const cycleDial = (
    cur: string,
    list: string[],
    setter: (v: string) => void,
    key: 'music_type' | 'eq_output' | 'crossfeed' | 'hum_noise' | 'reverb'
  ) => {
    const idx = Math.max(0, list.indexOf(cur))
    const next = list[(idx + 1) % list.length]
    setter(next)
    if (next !== 'none') setMode('dsp')
    syncDspParams({ [key]: next })
  }

  // Master Apply
  const handleApply = async () => {
    if (applying) return
    setApplying(true)
    try {
      await api.dsp.apply({
        mode,
        device,
        volume,
        music_type: musicType,
        eq_output: eqOutput,
        crossfeed,
        crossfeed_intensity: crossfeedIntensity,
        hum_noise: humFilter,
        reverb: ambience,
        reverb_intensity: ambienceIntensity,
      })
    } catch (e) {
      console.error('Apply DSP failed', e)
    } finally {
      setTimeout(() => setApplying(false), 250)
    }
  }

  const handlePlayPause = () => {
    status.state === 'play' ? api.playback.pause() : api.playback.play()
  }

  const handleAddToPlaylist = (t: Track | Track[]) => {
    setPlaylistTarget(Array.isArray(t) ? t : [t])
  }

  const track = status.current_track
  const artist = track?.artist || 'Unknown Artist'
  const title = track?.title || 'No Track Loaded'
  const isPlaying = status.state === 'play'

  if (!mounted) {
    return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center font-mono">INITIALIZING CONSOLE...</div>
  }

  return (
    <div className="min-h-screen bg-[#050505] text-white flex flex-col items-center justify-center p-2 sm:p-4 md:p-6 select-none font-['Space_Grotesk']">
      
      {/* ────────────────────────────────────────────────────────────────────────
          【1】DESKTOP CONSOLE VIEW
      ──────────────────────────────────────────────────────────────────────── */}
      <div className="hidden lg:block w-full max-w-[1380px] light-oak-frame rounded-[24px] p-5 shadow-2xl relative my-6">
        <div className="rounded-[18px] overflow-hidden bg-[#0d0f12] flex flex-col border border-white/5">
          
          {/* Top Metabar */}
          <div className="px-6 py-2.5 bg-black/80 border-b border-white/10 flex items-center justify-between text-[11px] font-mono tracking-widest text-white/70">
            <div className="flex items-center gap-3">
              <span className={`flex items-center gap-1.5 font-bold ${wsState === 'connected' ? 'text-emerald-400' : 'text-amber-400'}`}>
                <span className={`w-2 h-2 rounded-full ${wsState === 'connected' ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : 'bg-amber-400'}`} />
                {wsState === 'connected' ? 'ONLINE' : 'CONNECTING'}
              </span>
              <span className="text-white/40">|</span>
              <span className="text-amber-400/90 font-bold">CAMILLADSP ENGINE</span>
              <span>192kHz / 24-bit BIT-PERFECT</span>
              <span className="text-white/40">•</span>
              <span>CRYSTEK FEMTO CLOCK</span>
            </div>
            <div className="flex items-center gap-6">
              <span className="bg-amber-400/20 text-amber-300 px-2 py-0.5 rounded text-[10px] border border-amber-400/40">
                {mode.toUpperCase()} REFERENCE
              </span>
              <span>OUTPUT: {devices.find(d => d.id === device)?.name?.slice(0, 16) || device}</span>
              <span className="text-emerald-400">ATTN: {volume.toFixed(1)} dB</span>
            </div>
          </div>

          <div className="grid grid-cols-2 divide-x divide-white/10">
            <div className="purplish-glass-panel p-6 flex flex-col gap-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <span className="font-['Orbitron'] font-black tracking-widest text-base text-amber-400">REFERENCE CONSOLE</span>
                </div>
              </div>
              <SeekBar
                position={status.position}
                duration={status.duration}
                seekTarget={seekTarget}
                onSeek={setSeekTarget}
                onSeekCommit={() => {
                  if (seekTarget !== null) api.playback.seek(seekTarget)
                  setSeekTarget(null)
                }}
              />
            </div>

            <div className="purplish-glass-panel p-6 flex flex-col gap-4">
              <div className="flex gap-2">
                {(['queue', 'library', 'soundgenic', 'history', 'playlists'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-3 py-1 text-xs font-['Orbitron'] font-bold rounded ${activeTab === tab ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50' : 'text-white/50'}`}
                  >
                    {tab.toUpperCase().slice(0, 3)}
                  </button>
                ))}
              </div>
              <div className="flex-1 overflow-y-auto min-h-[400px]">
                {activeTab === 'queue' && <QueueView />}
                {activeTab === 'library' && <LibraryView currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
                {activeTab === 'soundgenic' && <SoundgenicView currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
                {activeTab === 'history' && <HistoryView />}
                {activeTab === 'playlists' && <PlaylistsView />}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 divide-x divide-black/20 brushed-silver-panel border-t-2 border-white/40 text-neutral-800">
            <div className="p-6 flex flex-col items-center justify-center min-h-[300px]">
              <div className="flex items-center justify-center gap-6 mb-4">
                <button onClick={handlePlayPause} className="w-16 h-16 rounded-full bg-white flex items-center justify-center text-2xl shadow-xl">{isPlaying ? '⏸' : '▶'}</button>
              </div>
              <div className="flex items-center gap-4 w-full justify-around">
                <div className="w-32 h-40 bg-[#f2eee3] border border-neutral-400 rounded relative overflow-hidden">
                  <div className="absolute bottom-4 left-1/2 w-1 h-32 bg-red-600 origin-bottom transition-transform" style={{ transform: `translateX(-50%) rotate(${(vuL - 0.5) * 60}deg)` }} />
                </div>
                <div className="w-40 h-40 rounded-full dial-aluminum relative flex items-center justify-center">
                  <span className="text-2xl font-bold">{volume.toFixed(1)}</span>
                  <input type="range" min="-60" max="0" step="0.5" value={volume} onChange={(e) => handleVolume(parseFloat(e.target.value))} className="absolute inset-0 opacity-0 cursor-pointer" />
                </div>
                <div className="w-32 h-40 bg-[#f2eee3] border border-neutral-400 rounded relative overflow-hidden">
                  <div className="absolute bottom-4 left-1/2 w-1 h-32 bg-red-600 origin-bottom transition-transform" style={{ transform: `translateX(-50%) rotate(${(vuR - 0.5) * 60}deg)` }} />
                </div>
              </div>
            </div>

            <div className="p-6 flex flex-col justify-between">
              <span className="text-xs font-bold text-neutral-800">◆ DSP DASHBOARD</span>
              <div className="grid grid-cols-3 gap-4">
                {/* Simplified Dials for brevity in this response context */}
                <div className="flex flex-col items-center">
                   <div className="w-12 h-12 rounded-full dial-aluminum" />
                   <span className="text-[10px] mt-1">OUTPUT EQ</span>
                </div>
              </div>
              <button onClick={handleApply} className="mt-4 px-6 py-2 bg-neutral-800 text-white rounded">APPLY</button>
            </div>
          </div>
        </div>
      </div>

      {/* ────────────────────────────────────────────────────────────────────────
          【2】MOBILE CONSOLE VIEW
      ──────────────────────────────────────────────────────────────────────── */}
      <div className="block lg:hidden w-full max-w-[440px] light-oak-frame rounded-[4rem] p-3.5 shadow-2xl relative my-auto">
        <div className="brushed-silver-panel rounded-[3.2rem] overflow-hidden relative flex flex-col p-4">
          
          <div className="w-full bg-black/95 rounded p-3 mb-3 font-mono text-xs text-red-500">
            {artist} — {title}
          </div>

          <div className="w-full aspect-square bg-black/90 rounded mb-3 flex items-center justify-center">
            {artworkUrl ? <img src={artworkUrl} className="w-full h-full object-cover" /> : <span className="text-5xl">♪</span>}
          </div>

          <div className="relative w-full h-[340px] bg-[#12161c] rounded-2xl overflow-hidden border border-white/10">
            <div className="bg-black/60 px-3 py-2 flex items-center justify-between">
              <button onClick={() => setDspOpen(true)} className="text-[11px] font-bold text-white">▽ DSP</button>
            </div>
            <div className="p-2 overflow-y-auto">
              {activeTab === 'queue' && <QueueView />}
              {/* ... other views ... */}
            </div>

            {/* DSP Rolldown Drawer Overlay (0.3s Transition & Safe Toggle) */}
            {dspOpen && (
              <div 
                className="absolute inset-0 z-50 bg-[#8c9a9b] brushed-silver-panel p-3.5 flex flex-col justify-between overflow-y-auto shadow-2xl transition-all duration-300 ease-out"
                style={{ animation: 'shutter-roll-down-03 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards' }}
              >
                {/* Drawer Header with Back-to-Play Trigger */}
                <div className="flex items-center justify-between border-b border-black/20 pb-1.5">
                  <span className="text-[11px] font-['Orbitron'] font-bold text-neutral-900 tracking-wider">
                    ◆ DSP DASHBOARD ENGINE
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setDspOpen(false)
                    }}
                    className="flex items-center gap-1 text-[11px] font-['Orbitron'] font-black text-neutral-900 hover:text-black cursor-pointer px-2 py-0.5 rounded border border-neutral-700/30 active:scale-95 transition-transform"
                  >
                    <span>PLY</span>
                    <span>▲</span>
                  </button>
                </div>

                <div className="flex-1 flex flex-col items-center justify-center">
                   {/* DSP Controls */}
                   <span className="text-neutral-800 text-xs font-bold">DSP CONTROL PANEL</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {playlistTarget && (
        <AddToPlaylistModal tracks={playlistTarget} onClose={() => setPlaylistTarget(null)} />
      )}
    </div>
  )
}
