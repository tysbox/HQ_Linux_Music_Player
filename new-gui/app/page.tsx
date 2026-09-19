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

const XF_OPTS = ['none', '15', '30', '60', '90']
const XF_LBL: Record<string, string> = { none: 'OFF', '15': '15°', '30': '30°', '60': '60°', '90': '90°' }

// Stage 7: CTC（クロストークキャンセレーション）= 角度（ダイヤル）× 距離感（アンダーバー＝強度）
// 既定 OFF。crossfeed とは排他（CTC を選ぶと crossfeed は無視される）
const CTC_OPTS = ['none', '15', '30', '60', '90']
const CTC_LBL: Record<string, string> = { none: 'OFF', '15': '15°', '30': '30°', '60': '60°', '90': '90°' }

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
    <div className="w-full space-y-1.5 my-1">
      {/* PC参考準拠: h-2.5 / bg-black/80 / border-white/15 / shadow-inner */}
      <div className="relative w-full h-2.5 bg-black/80 rounded-full overflow-hidden border border-white/15 flex items-center shadow-inner">
        <div className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full shadow-[0_0_10px_rgba(52,211,153,0.5)] transition-all duration-200" style={{ width: `${pct}%` }} />
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
      <div className="flex justify-between text-[11px] font-mono text-white/60 px-0.5">
        <span className="text-emerald-400 font-semibold">{formatDuration(displayPos)}</span>
        <span>{formatDuration(duration) || '--:--'}</span>
      </div>
    </div>
  )
})

export default function AudiophileConsoleApp() {
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

  // Seek Target Ref
  const [seekTarget, setSeekTarget] = useState<number | null>(null)

  // DSP Controls State
  const [eqOutput, setEqOutput] = useState('none')
  const [musicType, setMusicType] = useState('none')
  const [humFilter, setHumFilter] = useState('none')
  const [ambience, setAmbience] = useState('none')
  const [ambienceIntensity, setAmbienceIntensity] = useState(50)
  const [crossfeed, setCrossfeed] = useState('none')
  const [crossfeedIntensity, setCrossfeedIntensity] = useState(50)
  // Stage 7: CTC (クロストークキャンセレーション) — 既定 OFF
  const [ctc, setCtc] = useState('none')
  const [ctcIntensity, setCtcIntensity] = useState(50)
  const [presetName, setPresetName] = useState('LateNight')
  const [presetInput, setPresetInput] = useState('')
  const [presets, setPresets] = useState<string[]>(['LateNight', 'Studio Ref', 'Triode Warmth'])

  // VU Levels
  const [vuL, setVuL] = useState(0)
  const [vuR, setVuR] = useState(0)

  useEffect(() => {
    setMounted(true)
  }, [])

  // Dynamic Ballistic VU jitter synced to actual playback state
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
        const list = Array.isArray(data) ? data : data.devices || []
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
        const cfg = await api.dsp.config()
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
        // Stage 7: CTC 状態の復帰（既定 none）
        if (cfg.ctc) setCtc(cfg.ctc)
        if (typeof cfg.ctc_intensity === 'number') setCtcIntensity(cfg.ctc_intensity)
      } catch (e) {
        console.warn('Initial DSP config not loaded yet', e)
      }
    }
    fetchDevices()
    fetchConfig()
  }, [])

  // Resolve artwork (Local MPD vs UPnP)
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
    ctc?: string
    ctc_intensity?: number
  }) => {
    api.dsp.updateDspParams({
      music_type: params.music_type ?? musicType,
      eq_output: params.eq_output ?? eqOutput,
      crossfeed: params.crossfeed ?? crossfeed,
      crossfeed_intensity: params.crossfeed_intensity ?? crossfeedIntensity,
      hum_noise: params.hum_noise ?? humFilter,
      reverb: params.reverb ?? ambience,
      reverb_intensity: params.reverb_intensity ?? ambienceIntensity,
      ctc: params.ctc ?? ctc,
      ctc_intensity: params.ctc_intensity ?? ctcIntensity,
    }).catch(err => console.error('DSP params update failed', err))
  }

  // Cycle dial and trigger hot-reload
  const cycleDial = (
    cur: string,
    list: string[],
    setter: (v: string) => void,
    key: 'music_type' | 'eq_output' | 'crossfeed' | 'hum_noise' | 'reverb' | 'ctc'
  ) => {
    const idx = Math.max(0, list.indexOf(cur))
    const next = list[(idx + 1) % list.length]
    setter(next)
    if (next !== 'none') setMode('dsp')
    syncDspParams({ [key]: next })
  }

  // Master Apply — 連打時は合体し、CamillaDSP再起動は1回だけにする。
  // 06:52 のような「同一秒に4つの switch_audio.sh が並走し underrun の嵐」
  // の再発防止のため、前面でも3秒クールダウンを設ける。
  const lastApplyRef = useRef<number>(0)
  const handleApply = async () => {
    if (applying) return
    const now = Date.now()
    if (now - lastApplyRef.current < 3000) return
    lastApplyRef.current = now
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
        ctc,
        ctc_intensity: ctcIntensity,
      })
    } catch (e) {
      console.error('Apply DSP failed', e)
    } finally {
      setTimeout(() => setApplying(false), 3000)
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

  // If server-side rendering, render initial container frame to avoid flash/blank screen
  if (!mounted) {
    return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center font-mono">INITIALIZING CONSOLE...</div>
  }

  return (
    <div className="min-h-screen bg-[#050505] text-white flex flex-col items-center justify-center p-2 sm:p-4 md:p-6 select-none font-['Space_Grotesk']">
      
      {/* ────────────────────────────────────────────────────────────────────────
          【1】DESKTOP CONSOLE VIEW (lg: 1024px〜)
          ・上下ツートーン ＆ 左右50/50 分割
          ・上部: パープリッシュガラス・HUD・正方形フルアルバムアート / タブブラウザ (QUE, LIB, SRV, HIS, LIST)
          ・下部: 完全シルバーパネル
            - 左: トランスポート、中央ボリュームを向く対称VUメーター、アルミホイール、APPLYボタン
            - 右: DSPダッシュボード 64-Bit、6基ダイヤル、可変アンダーバー、プリセット保存
          ・New GUI デザイン採用: max-w-[1380px] / rounded-[24px] / p-5 (Image PC 準拠)
          ・レスポンシブ: lg未満では hidden、scale変換は使用しない (表示破綻の原因となるため)
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

          {/* Upper Section: Purplish Charcoal Smoked Glass (50/50 Split) — PC参考準拠 grid-cols-12 */}
          <div className="grid grid-cols-12 divide-x divide-white/10">
            {/* Upper Left (cols 6): HUD + Album Art + Real-time Seek */}
            <div className="col-span-6 purplish-glass-panel p-6 flex flex-col gap-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <span className="font-['Orbitron'] font-black tracking-widest text-base text-amber-400">REFERENCE CONSOLE</span>
                  <span className="text-[9px] px-1.5 py-0.5 bg-black/60 text-white/60 border border-white/10 rounded">STUDIO STEREO</span>
                </div>
                <div className="text-[10px] font-mono text-emerald-400 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  MPD DIRECT BITSTREAM
                </div>
              </div>

              {/* Status Bar */}
              <div className="bg-black/80 border border-white/10 rounded p-2.5 flex items-center justify-between font-mono text-xs">
                <div className="flex items-center gap-2 truncate">
                  <span className={`w-2 h-2 rounded-full ${isPlaying ? 'bg-emerald-400' : 'bg-amber-500'}`} />
                  <span className="text-amber-400/90 font-bold truncate">{artist} — {title}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0 text-[10px] text-white/70">
                  <span className="text-emerald-400 font-bold">{track?.source === 'upnp' ? 'UPNP' : 'PCM'}</span>
                  <span>{formatDuration(status.position)} / {formatDuration(status.duration) || '--:--'}</span>
                </div>
              </div>

              {/* Album Art: Full Square Frame with fallback — object-contain で全アート収まる */}
              <div className="w-full aspect-square max-h-[380px] bg-black/90 rounded border border-white/10 overflow-hidden relative shadow-2xl flex items-center justify-center mx-auto">
                {artworkUrl ? (
                  <img src={artworkUrl} alt="Album Art" className="w-full h-full object-contain" />
                ) : (
                  <div className="flex flex-col items-center justify-center text-white/20">
                    <span className="text-7xl mb-2">♪</span>
                    <span className="text-xs font-mono tracking-widest uppercase">No Artwork</span>
                  </div>
                )}
              </div>

              {/* Real-time Seek Bar */}
              <SeekBar
                position={status.position}
                duration={status.duration}
                seekTarget={seekTarget}
                onSeek={(v) => {
                  setSeekTarget(v)
                }}
                onSeekCommit={() => {
                  if (seekTarget !== null) {
                    api.playback.seek(seekTarget).catch(err => console.error('Seek error', err))
                  }
                  setSeekTarget(null)
                }}
              />
            </div>

            {/* Upper Right (cols 6): Functional Tabs + Integrated Sub-views (QUEUE / LIB / SRV / HIS / LIST) */}
            <div className="col-span-6 purplish-glass-panel p-6 flex flex-col gap-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex gap-2">
                  {([
                    { id: 'queue', label: 'QUE', badge: status.queue_length },
                    { id: 'library', label: 'LIB' },
                    { id: 'soundgenic', label: 'SRV' },
                    { id: 'history', label: 'HIS' },
                    { id: 'playlists', label: 'LIST' },
                  ] as { id: Tab; label: string; badge?: number }[]).map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id as Tab)}
                      className={`px-3 py-1 text-xs font-['Orbitron'] font-bold rounded tracking-wider border transition-all cursor-pointer ${
                        activeTab === tab.id
                          ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50 shadow-[0_0_8px_rgba(52,211,153,0.3)]'
                          : 'bg-black/40 text-white/50 border-white/5 hover:text-white/90'
                      }`}
                    >
                      {tab.label} {tab.badge !== undefined && tab.badge > 0 && <span className="text-[10px] opacity-75">{tab.badge}</span>}
                    </button>
                  ))}
                </div>
                <span className="text-[10px] font-mono text-white/40 flex items-center gap-1.5">
                  SYSTEM READY <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                </span>
              </div>

              {/* Render Selected View */}
              <div className="flex-1 overflow-y-auto pr-1 max-h-[460px] bg-black/30 rounded border border-white/5 p-2">
                {activeTab === 'queue'      && <QueueView />}
                {activeTab === 'library'    && <LibraryView currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
                {activeTab === 'soundgenic' && <SoundgenicView currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
                {activeTab === 'history'    && <HistoryView />}
                {activeTab === 'playlists'  && <PlaylistsView />}
              </div>
            </div>
          </div>

          {/* Lower Section: Pure Brushed Silver Panel (50/50 Split) — PC参考準拠 grid-cols-12 */}
          <div className="grid grid-cols-12 divide-x divide-black/20 brushed-silver-panel border-t-2 border-white/50 text-neutral-800">
            {/* Lower Left (cols 6): Transports, Symmetrical VU Meters, Master Attenuator Wheel */}
            <div className="col-span-6 p-6 flex flex-col items-center justify-between min-h-[410px]">

              {/* Transport Buttons — PC参考準拠: アルミ削り出し丸ボタン */}
              <div className="flex items-center justify-between w-full max-w-[420px] mx-auto px-4 mb-2 select-none">
                <button
                  onClick={() => api.playback.toggleRandom()}
                  title="Shuffle"
                  className="w-10 h-10 rounded-full dial-aluminum border border-neutral-400/80 flex items-center justify-center shadow-md hover:scale-105 active:scale-95 transition-all cursor-pointer text-base"
                >
                  <span className={status.random ? 'text-emerald-700' : 'text-neutral-800'}>🔀</span>
                </button>
                <button
                  onClick={() => api.playback.previous()}
                  title="Previous"
                  className="w-11 h-11 rounded-full dial-aluminum border border-neutral-400/80 flex items-center justify-center shadow-md hover:scale-105 active:scale-95 transition-all cursor-pointer text-xl text-neutral-800"
                >
                  ⏮
                </button>
                <button
                  onClick={handlePlayPause}
                  title={isPlaying ? 'Pause' : 'Play'}
                  className={`relative w-14 h-14 rounded-full control-dial-outer p-1 flex items-center justify-center shadow-lg hover:scale-105 active:scale-95 transition-all cursor-pointer ${
                    isPlaying
                      ? 'ring-2 ring-emerald-400/60 shadow-[0_0_18px_rgba(52,211,153,0.55)]'
                      : 'ring-1 ring-white/30 shadow-md'
                  }`}
                >
                  <span className="w-full h-full rounded-full dial-aluminum border border-white/60 flex items-center justify-center relative shadow-inner text-2xl">
                    <span className={`absolute inset-0 rounded-full border pointer-events-none transition-all ${isPlaying ? 'border-emerald-400/60 shadow-[inset_0_0_8px_rgba(52,211,153,0.35)]' : 'border-transparent'}`} />
                    <span className={isPlaying ? 'text-emerald-600 drop-shadow-[0_0_8px_rgba(52,211,153,0.9)]' : 'text-neutral-800 drop-shadow-[0_1px_1px_rgba(255,255,255,0.7)]'}>{isPlaying ? '⏸' : '▶'}</span>
                  </span>
                </button>
                <button
                  onClick={() => api.playback.next()}
                  title="Next"
                  className="w-11 h-11 rounded-full dial-aluminum border border-neutral-400/80 flex items-center justify-center shadow-md hover:scale-105 active:scale-95 transition-all cursor-pointer text-xl text-neutral-800"
                >
                  ⏭
                </button>
                <button
                  onClick={() => api.playback.toggleRepeat()}
                  title="Repeat"
                  className="w-10 h-10 rounded-full dial-aluminum border border-neutral-400/80 flex items-center justify-center shadow-md hover:scale-105 active:scale-95 transition-all cursor-pointer text-base"
                >
                  <span className={status.repeat ? 'text-emerald-700' : 'text-neutral-800'}>🔁</span>
                </button>
              </div>

              {/* Symmetrical VU Needles + Central Master Wheel — Image PC準拠 */}
              <div className="flex items-center justify-between w-full px-2 gap-4 my-2">
                {/* Left VU Meter — Image PC準拠: 105×256 / dB目盛 / 対称針 */}
                <div className="w-[105px] h-64 bg-gradient-to-b from-[#f8f5eb] via-[#f3ecda] to-[#e7dcbf] border-2 border-neutral-700/70 rounded-lg p-2 shadow-[inset_0_3px_12px_rgba(0,0,0,0.45),0_4px_10px_rgba(0,0,0,0.25)] flex flex-col items-center justify-between relative overflow-hidden shrink-0 select-none">
                  <div className="absolute inset-0 bg-gradient-to-br from-amber-200/25 via-transparent to-black/20 pointer-events-none" />
                  <div className="w-full flex items-center justify-between z-10 px-0.5"><span className="text-[9px] font-black font-mono tracking-widest text-neutral-700">CH-L</span><span className="text-[7px] font-bold font-mono text-neutral-500 uppercase tracking-tight">1.228V RMS</span></div>
                  <svg viewBox="0 0 100 210" className="w-full h-full z-10 overflow-visible">
                    <defs><filter id="glow-l" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="1" stdDeviation="0.8" floodColor="#000000" floodOpacity="0.35" /></filter></defs>
                    <g transform="translate(100, 0) scale(-1, 1)">
                      <circle cx="15" cy="105" r="70" fill="none" stroke="#1c1917" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="87.96 439.82" strokeDashoffset="32.99" />
                      <circle cx="15" cy="105" r="70" fill="none" stroke="#dc2626" strokeWidth="1.8" strokeLinecap="round" strokeDasharray="21.99 439.82" strokeDashoffset="54.98" />
                      <line x1="60.3" y1="59.7" x2="65.9" y2="54.1" stroke="#dc2626" strokeWidth="1.4" />
                      <line x1="64.7" y1="64.7" x2="71.0" y2="59.7" stroke="#dc2626" strokeWidth="1.2" />
                      <line x1="68.7" y1="70.1" x2="75.4" y2="65.8" stroke="#dc2626" strokeWidth="1.2" />
                      <line x1="72.0" y1="75.9" x2="80.0" y2="71.9" stroke="#dc2626" strokeWidth="2.0" />
                      <line x1="74.7" y1="82.1" x2="82.2" y2="79.2" stroke="#1c1917" strokeWidth="1.2" />
                      <line x1="77.8" y1="92.8" x2="85.7" y2="91.3" stroke="#1c1917" strokeWidth="1.2" />
                      <line x1="79.0" y1="105.0" x2="87.0" y2="105.0" stroke="#1c1917" strokeWidth="1.4" />
                      <line x1="77.8" y1="117.2" x2="85.7" y2="118.7" stroke="#1c1917" strokeWidth="1.2" />
                      <line x1="73.0" y1="132.0" x2="80.3" y2="135.4" stroke="#1c1917" strokeWidth="1.2" />
                      <line x1="60.3" y1="150.3" x2="65.9" y2="155.9" stroke="#1c1917" strokeWidth="1.4" />
                      <line x1="15" y1="105" x2={15 + 73 * Math.cos((45 - vuL * 90) * Math.PI / 180)} y2={105 + 73 * Math.sin((45 - vuL * 90) * Math.PI / 180)} stroke="#b91c1c" strokeWidth="1.5" strokeLinecap="round" filter="url(#glow-l)" className="vu-needle" />
                      <line x1="15" y1="105" x2="8" y2="105" stroke="#1f2937" strokeWidth="2.4" strokeLinecap="round" />
                      <circle cx="15" cy="105" r="6.5" fill="#1c1917" stroke="#78716c" strokeWidth="0.8" />
                      <circle cx="15" cy="105" r="2.4" fill="#d6d3d1" />
                      <line x1="13.5" y1="105" x2="16.5" y2="105" stroke="#44403c" strokeWidth="0.6" />
                    </g>
                    <text x="27" y="48" textAnchor="end" fontSize="5" fontWeight="bold" fill="#dc2626" fontFamily="monospace">+3</text>
                    <text x="24" y="58" textAnchor="end" fontSize="5" fontWeight="bold" fill="#dc2626" fontFamily="monospace">+2</text>
                    <text x="22" y="68" textAnchor="end" fontSize="5" fontWeight="bold" fill="#dc2626" fontFamily="monospace">+1</text>
                    <text x="16" y="78.5" textAnchor="end" fontSize="6" fontWeight="900" fill="#dc2626" fontFamily="monospace">0</text>
                    <text x="15.5" y="88" textAnchor="end" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-1</text>
                    <text x="13.5" y="97" textAnchor="end" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-3</text>
                    <text x="12.5" y="107" textAnchor="end" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-5</text>
                    <text x="13.5" y="122" textAnchor="end" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-7</text>
                    <text x="16.5" y="141" textAnchor="end" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-10</text>
                    <text x="27" y="166" textAnchor="end" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-20</text>
                    <text x="52" y="94" textAnchor="end" fontSize="8" fontWeight="900" fill="#3a3733" fontFamily="'Space Grotesk'" letterSpacing="1">VU</text>
                    <text x="52" y="102" textAnchor="end" fontSize="4.2" fontWeight="bold" fill="#84796c" fontFamily="monospace">dBFS</text>
                  </svg>
                  <span className="text-[9px] font-mono font-black text-neutral-800 bg-white/90 px-2 py-0.5 rounded border border-neutral-300 shadow-sm z-10">
                    {(volume - (1 - vuL) * 12).toFixed(1)} dB
                  </span>
                </div>

                {/* Central Aluminum Attenuator Dial */}
                <div className="relative w-52 h-52 rounded-full control-dial-outer p-2 flex items-center justify-center shrink-0">
                  <div className="w-full h-full rounded-full dial-aluminum flex flex-col items-center justify-center relative shadow-2xl">
                    <div
                      className="absolute inset-0 rounded-full pointer-events-none transition-transform duration-100"
                      style={{ transform: `rotate(${-135 + ((volume + 60) / 60) * 270}deg)` }}
                    >
                      <div className="w-2 h-2 bg-neutral-800 rounded-full absolute top-3 left-1/2 -translate-x-1/2" />
                    </div>

                    <div className="flex flex-col items-center justify-center z-30 pointer-events-none">
                      <span className="text-[9px] font-bold text-neutral-500 uppercase tracking-widest">LEVEL</span>
                      <div className="flex items-baseline gap-0.5">
                        <span className="text-4xl font-extralight tracking-tight text-neutral-800 font-bold">{volume.toFixed(1)}</span>
                        <span className="text-xs font-bold text-neutral-600 uppercase">dB</span>
                      </div>
                    </div>
                    {/* APPLY: ダイヤル外に分離 — 音量inputとヒット領域を重ねない */}
                    <button
                      type="button"
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => { e.stopPropagation(); handleApply() }}
                      disabled={applying}
                      className={`absolute -bottom-2 left-1/2 -translate-x-1/2 z-30 w-14 h-14 rounded-full flex items-center justify-center text-[9px] font-bold tracking-widest uppercase transition-all cursor-pointer border border-neutral-400 ${
                        applying
                          ? 'bg-emerald-500 text-white shadow-inner scale-95'
                          : 'bg-gradient-to-b from-white to-gray-300 text-neutral-800 shadow-md active:scale-95'
                      }`}
                    >
                      {applying ? 'WAIT' : 'APPLY'}
                    </button>
                    {/* 音量操作はダイヤル上部のリング領域のみ (中央ボタンと重ならないよう inset を絞る) */}
                    <input
                      type="range"
                      min="-60"
                      max="0"
                      step="0.5"
                      value={volume}
                      onChange={(e) => handleVolume(parseFloat(e.target.value))}
                      className="absolute inset-x-4 top-2 bottom-16 opacity-0 z-10 cursor-pointer"
                    />
                  </div>
                </div>

                {/* Right VU Meter — Image PC準拠: 105×256 / dB目盛 / 対称針 */}
                <div className="w-[105px] h-64 bg-gradient-to-b from-[#f8f5eb] via-[#f3ecda] to-[#e7dcbf] border-2 border-neutral-700/70 rounded-lg p-2 shadow-[inset_0_3px_12px_rgba(0,0,0,0.45),0_4px_10px_rgba(0,0,0,0.25)] flex flex-col items-center justify-between relative overflow-hidden shrink-0 select-none">
                  <div className="absolute inset-0 bg-gradient-to-bl from-amber-200/25 via-transparent to-black/20 pointer-events-none" />
                  <div className="w-full flex items-center justify-between z-10 px-0.5"><span className="text-[7px] font-bold font-mono text-neutral-500 uppercase tracking-tight">1.228V RMS</span><span className="text-[9px] font-black font-mono tracking-widest text-neutral-700">CH-R</span></div>
                  <svg viewBox="0 0 100 210" className="w-full h-full z-10 overflow-visible">
                    <defs><filter id="glow-r" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="1" stdDeviation="0.8" floodColor="#000000" floodOpacity="0.35" /></filter></defs>
                    <circle cx="15" cy="105" r="70" fill="none" stroke="#1c1917" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="87.96 439.82" strokeDashoffset="32.99" />
                    <circle cx="15" cy="105" r="70" fill="none" stroke="#dc2626" strokeWidth="1.8" strokeLinecap="round" strokeDasharray="21.99 439.82" strokeDashoffset="54.98" />
                    <line x1="60.3" y1="59.7" x2="65.9" y2="54.1" stroke="#dc2626" strokeWidth="1.4" />
                    <line x1="64.7" y1="64.7" x2="71.0" y2="59.7" stroke="#dc2626" strokeWidth="1.2" />
                    <line x1="68.7" y1="70.1" x2="75.4" y2="65.8" stroke="#dc2626" strokeWidth="1.2" />
                    <line x1="72.0" y1="75.9" x2="80.0" y2="71.9" stroke="#dc2626" strokeWidth="2.0" />
                    <line x1="74.7" y1="82.1" x2="82.2" y2="79.2" stroke="#1c1917" strokeWidth="1.2" />
                    <line x1="77.8" y1="92.8" x2="85.7" y2="91.3" stroke="#1c1917" strokeWidth="1.2" />
                    <line x1="79.0" y1="105.0" x2="87.0" y2="105.0" stroke="#1c1917" strokeWidth="1.4" />
                    <line x1="77.8" y1="117.2" x2="85.7" y2="118.7" stroke="#1c1917" strokeWidth="1.2" />
                    <line x1="73.0" y1="132.0" x2="80.3" y2="135.4" stroke="#1c1917" strokeWidth="1.2" />
                    <line x1="60.3" y1="150.3" x2="65.9" y2="155.9" stroke="#1c1917" strokeWidth="1.4" />
                    <text x="73" y="48" fontSize="5" fontWeight="bold" fill="#dc2626" fontFamily="monospace">+3</text>
                    <text x="76" y="58" fontSize="5" fontWeight="bold" fill="#dc2626" fontFamily="monospace">+2</text>
                    <text x="78" y="68" fontSize="5" fontWeight="bold" fill="#dc2626" fontFamily="monospace">+1</text>
                    <text x="84" y="78.5" fontSize="6" fontWeight="900" fill="#dc2626" fontFamily="monospace">0</text>
                    <text x="84.5" y="88" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-1</text>
                    <text x="86.5" y="97" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-3</text>
                    <text x="87.5" y="107" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-5</text>
                    <text x="86.5" y="122" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-7</text>
                    <text x="83.5" y="141" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-10</text>
                    <text x="73" y="166" fontSize="4.8" fontWeight="bold" fill="#333" fontFamily="monospace">-20</text>
                    <text x="48" y="94" fontSize="8" fontWeight="900" fill="#3a3733" fontFamily="'Space Grotesk'" letterSpacing="1">VU</text>
                    <text x="48" y="102" fontSize="4.2" fontWeight="bold" fill="#84796c" fontFamily="monospace">dBFS</text>
                    <line x1="15" y1="105" x2={15 + 73 * Math.cos((45 - vuR * 90) * Math.PI / 180)} y2={105 + 73 * Math.sin((45 - vuR * 90) * Math.PI / 180)} stroke="#b91c1c" strokeWidth="1.5" strokeLinecap="round" filter="url(#glow-r)" className="vu-needle" />
                    <line x1="15" y1="105" x2="8" y2="105" stroke="#1f2937" strokeWidth="2.4" strokeLinecap="round" />
                    <circle cx="15" cy="105" r="6.5" fill="#1c1917" stroke="#78716c" strokeWidth="0.8" />
                    <circle cx="15" cy="105" r="2.4" fill="#d6d3d1" />
                    <line x1="13.5" y1="105" x2="16.5" y2="105" stroke="#44403c" strokeWidth="0.6" />
                  </svg>
                  <span className="text-[9px] font-mono font-black text-neutral-800 bg-white/90 px-2 py-0.5 rounded border border-neutral-300 shadow-sm z-10">
                    {(volume - (1 - vuR) * 12).toFixed(1)} dB
                  </span>
                </div>
              </div>

              {/* Lower Selector Controls (Mode & Output device dropdowns) */}
              <div className="flex items-center gap-4 mt-2">
                <div className="relative bg-neutral-300/80 px-3 py-1 rounded-full border border-neutral-400 text-xs font-bold text-neutral-800 flex items-center gap-1 cursor-pointer">
                  <span className={`w-2 h-2 rounded-full ${mode === 'dsp' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                  <span>MODE: {mode.toUpperCase()}</span>
                  <select
                    value={mode}
                    onChange={(e) => {
                      const m = e.target.value as 'pure' | 'dsp'
                      setMode(m)
                      api.dsp.apply({
                        mode: m,
                        device,
                        volume,
                        music_type: musicType,
                        eq_output: m === 'pure' ? 'none' : eqOutput,
                        crossfeed: m === 'pure' ? 'none' : crossfeed,
                        crossfeed_intensity: crossfeedIntensity,
                        hum_noise: m === 'pure' ? 'none' : humFilter,
                        reverb: m === 'pure' ? 'none' : ambience,
                        reverb_intensity: ambienceIntensity,
                      }).catch(err => console.error('Mode apply failed', err))
                    }}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  >
                    <option value="dsp">DSP MASTER</option>
                    <option value="pure">PURE DIRECT</option>
                  </select>
                </div>

                <div className="relative bg-neutral-300/80 px-3 py-1 rounded-full border border-neutral-400 text-xs font-bold text-neutral-800 flex items-center gap-1 cursor-pointer">
                  <span>⚡ OUT: {devices.find(d => d.id === device)?.name?.slice(0, 12) || 'SELECT'}</span>
                  <select
                    value={device}
                    onChange={(e) => {
                      const d = e.target.value
                      setDevice(d)
                      api.dsp.apply({
                        mode,
                        device: d,
                        volume,
                        music_type: musicType,
                        eq_output: eqOutput,
                        crossfeed,
                        crossfeed_intensity: crossfeedIntensity,
                        hum_noise: humFilter,
                        reverb: ambience,
                        reverb_intensity: ambienceIntensity,
                      }).catch(err => console.error('Device apply failed', err))
                    }}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  >
                    {devices.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Lower Right (cols 6): DSP Dashboard Engine — PC参考準拠 */}
            <div className="col-span-6 p-6 flex flex-col justify-between min-h-[410px]">
              <div className="flex items-center justify-between border-b border-black/15 pb-2">
                <span className="text-xs font-['Orbitron'] font-black tracking-widest text-neutral-900">◆ DSP DASHBOARD 64-BIT</span>
                <span className="text-[10px] font-mono text-emerald-800 font-bold bg-emerald-500/20 px-2.5 py-0.5 rounded-full border border-emerald-600/30">
                  LOCKED (0 XRUN)
                </span>
              </div>

              {/* Telemetry Metrics — PC参考準拠: shadow-inner / text-[9px] */}
              <div className="grid grid-cols-6 gap-2 bg-neutral-300/70 p-2 rounded-lg border border-neutral-400/60 text-[10px] font-mono text-center my-2 shadow-inner">
                <div><div className="text-neutral-600 font-bold text-[9px]">MODE</div><div className="font-black text-neutral-900">{mode.toUpperCase()}</div></div>
                <div><div className="text-neutral-600 font-bold text-[9px]">VOLUME</div><div className="font-black text-neutral-900">{volume.toFixed(1)} dB</div></div>
                <div><div className="text-neutral-600 font-bold text-[9px]">LATENCY</div><div className="font-black text-emerald-800">0.42 ms</div></div>
                <div><div className="text-neutral-600 font-bold text-[9px]">FORMAT</div><div className="font-black text-neutral-900">{track?.source === 'upnp' ? 'STREAM' : 'FLAC'}</div></div>
                <div><div className="text-neutral-600 font-bold text-[9px]">DEPTH</div><div className="font-black text-neutral-900">24b</div></div>
                <div><div className="text-neutral-600 font-bold text-[9px]">RATE</div><div className="font-black text-emerald-800">192k</div></div>
              </div>

              {/* 6 Rotary Dials — PC参考準拠: gap-y-4 / font-extrabold */}
              <div className="grid grid-cols-3 gap-y-4 gap-x-6 py-2 place-items-center">
                {/* 1. Output EQ */}
                <div className="flex flex-col items-center gap-1">
                  <button
                    onClick={() => cycleDial(eqOutput, EQ_OUT_OPTS, setEqOutput, 'eq_output')}
                    className="w-14 h-14 rounded-full dial-aluminum shadow-md border border-neutral-400 relative flex items-center justify-center cursor-pointer active:scale-95"
                  >
                    <div className="w-1 h-3 bg-neutral-800 rounded-full absolute top-1" />
                    <span className="text-[8px] font-bold text-neutral-800 text-center leading-none px-1">{EQ_OUT_LBL[eqOutput] || eqOutput}</span>
                  </button>
                  <span className="text-[10px] font-bold tracking-wider text-neutral-700 uppercase">OUTPUT EQ</span>
                </div>

                {/* 2. Source EQ */}
                <div className="flex flex-col items-center gap-1">
                  <button
                    onClick={() => cycleDial(musicType, EQ_SRC_OPTS, setMusicType, 'music_type')}
                    className="w-14 h-14 rounded-full dial-aluminum shadow-md border border-neutral-400 relative flex items-center justify-center cursor-pointer active:scale-95"
                  >
                    <div className="w-1 h-3 bg-neutral-800 rounded-full absolute top-1" />
                    <span className="text-[8px] font-bold text-neutral-800 text-center leading-none px-1">{EQ_SRC_LBL[musicType] || musicType}</span>
                  </button>
                  <span className="text-[10px] font-bold tracking-wider text-neutral-700 uppercase">SOURCE EQ</span>
                </div>

                {/* 3. Hum Filter */}
                <div className="flex flex-col items-center gap-1">
                  <button
                    onClick={() => cycleDial(humFilter, HUM_OPTS, setHumFilter, 'hum_noise')}
                    className="w-14 h-14 rounded-full dial-aluminum shadow-md border border-neutral-400 relative flex items-center justify-center cursor-pointer active:scale-95"
                  >
                    <div className="w-1 h-3 bg-neutral-800 rounded-full absolute top-1" />
                    <span className="text-[8px] font-bold text-neutral-800">{HUM_LBL[humFilter]}</span>
                  </button>
                  <span className="text-[10px] font-bold tracking-wider text-neutral-700 uppercase">HUM FILTER</span>
                </div>

                {/* 4. Ambience + Underbar */}
                <div className="flex flex-col items-center gap-1">
                  <button
                    onClick={() => cycleDial(ambience, REV_OPTS, setAmbience, 'reverb')}
                    className="w-14 h-14 rounded-full dial-aluminum shadow-md border border-neutral-400 relative flex items-center justify-center cursor-pointer active:scale-95"
                  >
                    <div className="w-1 h-3 bg-neutral-800 rounded-full absolute top-1" />
                    <span className="text-[8px] font-bold text-neutral-800 text-center leading-none px-1">{REV_LBL[ambience] || ambience}</span>
                  </button>
                  <span className="text-[10px] font-bold tracking-wider text-neutral-700 uppercase">AMBIENCE</span>
                  <div
                    className="w-14 h-1.5 bg-neutral-400 rounded-full overflow-hidden cursor-pointer"
                    onClick={(e) => {
                      const r = e.currentTarget.getBoundingClientRect()
                      const val = Math.max(0, Math.min(100, Math.round(((e.clientX - r.left) / r.width) * 100)))
                      setAmbienceIntensity(val)
                      syncDspParams({ reverb_intensity: val })
                    }}
                  >
                    <div className="h-full bg-emerald-600 rounded-full" style={{ width: `${ambience === 'none' ? 0 : ambienceIntensity}%` }} />
                  </div>
                </div>

                {/* 5. Crossfeed + Underbar */}
                <div className="flex flex-col items-center gap-1">
                  <button
                    onClick={() => cycleDial(crossfeed, XF_OPTS, setCrossfeed, 'crossfeed')}
                    className="w-14 h-14 rounded-full dial-aluminum shadow-md border border-neutral-400 relative flex items-center justify-center cursor-pointer active:scale-95"
                  >
                    <div className="w-1 h-3 bg-neutral-800 rounded-full absolute top-1" />
                    <span className="text-[8px] font-bold text-neutral-800">{XF_LBL[crossfeed]}</span>
                  </button>
                  <span className="text-[10px] font-bold tracking-wider text-neutral-700 uppercase">CROSSFEED</span>
                  <div
                    className="w-14 h-1.5 bg-neutral-400 rounded-full overflow-hidden cursor-pointer"
                    onClick={(e) => {
                      const r = e.currentTarget.getBoundingClientRect()
                      const val = Math.max(0, Math.min(100, Math.round(((e.clientX - r.left) / r.width) * 100)))
                      setCrossfeedIntensity(val)
                      syncDspParams({ crossfeed_intensity: val })
                    }}
                  >
                    <div className="h-full bg-emerald-600 rounded-full" style={{ width: `${crossfeed === 'none' ? 0 : crossfeedIntensity}%` }} />
                  </div>
                </div>

                {/* 6. CTC + Underbar（Stage 7: PRESET ダイヤル廃止 → その位置へ CTC を配置） */}
                {/*    角度＝ダイヤル、距離感＝アンダーバー（強度）。Preset 適用は下の登録パネルへ移設 */}
                <div className="flex flex-col items-center gap-1">
                  <button
                    onClick={() => cycleDial(ctc, CTC_OPTS, setCtc, 'ctc')}
                    className="w-14 h-14 rounded-full dial-aluminum shadow-md border border-neutral-400 relative flex items-center justify-center cursor-pointer active:scale-95"
                  >
                    <div className="w-1 h-3 bg-neutral-800 rounded-full absolute top-1" />
                    <span className="text-[8px] font-bold text-neutral-800">{CTC_LBL[ctc]}</span>
                  </button>
                  <span className="text-[10px] font-bold tracking-wider text-neutral-700 uppercase">CTC</span>
                  <div
                    className="w-14 h-1.5 bg-neutral-400 rounded-full overflow-hidden cursor-pointer"
                    onClick={(e) => {
                      const r = e.currentTarget.getBoundingClientRect()
                      const val = Math.max(0, Math.min(100, Math.round(((e.clientX - r.left) / r.width) * 100)))
                      setCtcIntensity(val)
                      syncDspParams({ ctc_intensity: val })
                    }}
                  >
                    <div className="h-full bg-emerald-600 rounded-full" style={{ width: `${ctc === 'none' ? 0 : ctcIntensity}%` }} />
                  </div>
                </div>
              </div>

              {/* Preset Registration — 適用（クリック）＋ 保存はここで行う */}
              <div className="flex flex-col gap-2 mt-2 pt-2 border-t border-black/15">
                <div className="flex flex-wrap items-center gap-1.5">
                  {presets.length === 0 ? (
                    <span className="text-[10px] text-neutral-600">No presets saved</span>
                  ) : (
                    presets.map((p) => (
                      <button
                        key={p}
                        onClick={() => setPresetName(p)}
                        className={`px-2.5 py-1 text-[10px] font-bold rounded border transition-colors cursor-pointer ${
                          presetName === p
                            ? 'bg-emerald-700 text-white border-emerald-800'
                            : 'bg-neutral-200 text-neutral-800 border-neutral-500 hover:bg-neutral-300'
                        }`}
                      >
                        {p}
                      </button>
                    ))
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={presetInput}
                    onChange={(e) => setPresetInput(e.target.value)}
                    placeholder="New preset name..."
                    className="flex-1 bg-black/80 text-white border border-neutral-500 rounded px-3 py-1.5 text-xs font-mono placeholder:text-white/40 focus:outline-none focus:border-emerald-500"
                  />
                  <button
                    onClick={() => {
                      const name = presetInput.trim()
                      if (name && !presets.includes(name)) {
                        setPresets((p) => [...p, name])
                        setPresetName(name)
                        setPresetInput('')
                      }
                    }}
                    className="px-4 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-['Orbitron'] font-bold rounded shadow transition-all cursor-pointer"
                  >
                    SAVE
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Footer Metabar */}
          <div className="px-6 py-2 bg-black/90 border-t border-white/10 flex items-center justify-between text-[10px] font-mono text-white/50">
            <div className="flex gap-4">
              <span>EARTH ISOLATION: <strong className="text-emerald-400">GALVANIC PASS</strong></span>
              <span>CHASSIS TEMP: 36.8°C</span>
              <span>CLOCK DRIFT: ±0.002 ppm</span>
            </div>
            <div className="flex items-center gap-2 text-emerald-400 font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              IIR CASCADE PASSIVE FILTER ACTIVE
            </div>
          </div>
        </div>
      </div>

      {/* ────────────────────────────────────────────────────────────────────────
          【2】MOBILE CONSOLE VIEW (lg未満: 〜1023px)
          ・縦型DAPコンソール（オーク枠＋ブラッシュドシルバーボディ）
          ・上部: MPDステータスHUD、アートワーク、トランスポート、左右20セグLED VU、中央アッテネーター
          ・下部: シャッター式ロールダウン切替（通常時はタブ切替＋実機ビュー、▽DSPでDSPパネル展開）
          ・New GUI デザイン採用: max-w-[440px] / rounded-[4rem] / p-3.5 (Image Mobile 準拠)
          ・レスポンシブ: lg以上では hidden、scale変換は使用しない
      ──────────────────────────────────────────────────────────────────────── */}
      <div className="block lg:hidden w-full max-w-[440px] light-oak-frame rounded-[4rem] p-3.5 shadow-2xl relative my-auto">
        <div className="brushed-silver-panel rounded-[3.2rem] overflow-hidden relative flex flex-col p-4">
          
          {/* Top MPD Status Panel */}
          <div className="w-full bg-black/95 rounded border border-white/10 p-3 shadow-inner font-mono text-xs flex flex-col gap-1.5 mb-3">
            <div className="flex items-center justify-between text-[10px]">
              <div className="flex items-center gap-1.5 text-emerald-400 font-bold">
                <span className={`w-1.5 h-1.5 rounded-full ${wsState === 'connected' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
                {wsState === 'connected' ? 'MPD CONNECTED' : 'DISCONNECTED'}
              </div>
              <span className="text-red-500 font-bold tracking-wider">{track?.source === 'upnp' ? 'STREAM' : 'FLAC 192K'}</span>
            </div>
            <div className="h-px bg-red-950/40 w-full" />
            <div className="flex items-center justify-between text-[11px] text-red-500 font-bold truncate">
              <span className="truncate">{artist} — {title}</span>
              <span className="text-red-400/70 text-[9px] shrink-0 ml-2">
                {formatDuration(status.position)} / {formatDuration(status.duration) || '--:--'}
              </span>
            </div>
          </div>

          {/* Album Artwork — object-contain で全アート収まる（正方形） */}
          <div className="w-full aspect-square bg-black/90 p-1 rounded shadow-2xl overflow-hidden mb-3 flex items-center justify-center border border-white/10">
            {artworkUrl ? (
              <img src={artworkUrl} alt="Album Art" className="w-full h-full object-contain rounded-sm" />
            ) : (
              <span className="text-5xl text-white/20">♪</span>
            )}
          </div>

          {/* Mobile SeekBar */}
          <SeekBar
            position={status.position}
            duration={status.duration}
            seekTarget={seekTarget}
            onSeek={(v) => {
              setSeekTarget(v)
            }}
            onSeekCommit={() => {
              if (seekTarget !== null) {
                api.playback.seek(seekTarget).catch(err => console.error('Seek error', err))
              }
              setSeekTarget(null)
            }}
          />

          {/* Transport Controls Row — Image Mobile準拠: 立体アルミ丸ボタン */}
          <div className="w-full flex items-center justify-between px-2 my-2 select-none">
            <button onClick={() => api.playback.toggleRandom()} title="Shuffle" className="w-10 h-10 rounded-full control-dial-outer p-1 flex items-center justify-center cursor-pointer transition-transform active:scale-95 shadow-md group">
              <span className="w-full h-full rounded-full dial-aluminum flex items-center justify-center border border-white/60 shadow-inner text-sm">
                <span className={status.random ? 'text-emerald-600 drop-shadow-[0_0_4px_#34d399]' : 'text-neutral-700 group-hover:text-neutral-900'}>🔀</span>
              </span>
            </button>
            <button onClick={() => api.playback.previous()} title="Previous" className="w-10 h-10 rounded-full control-dial-outer p-1 flex items-center justify-center cursor-pointer transition-transform active:scale-95 shadow-md group">
              <span className="w-full h-full rounded-full dial-aluminum flex items-center justify-center border border-white/60 shadow-inner text-lg text-neutral-700 group-hover:text-neutral-900">⏮</span>
            </button>
            <button
              onClick={handlePlayPause}
              title="Play/Pause"
              className={`w-12 h-12 rounded-full control-dial-outer p-1 flex items-center justify-center cursor-pointer transition-transform active:scale-95 group relative ${
                isPlaying ? 'shadow-[0_0_12px_rgba(52,211,153,0.4)] border border-emerald-500/40' : 'shadow-md'
              }`}
            >
              <span className="w-full h-full rounded-full dial-aluminum flex items-center justify-center border border-white/80 shadow-inner relative text-2xl">
                <span className={isPlaying ? 'text-emerald-500 drop-shadow-[0_0_6px_#34d399]' : 'text-neutral-700'}>
                  {isPlaying ? '⏸' : '▶'}
                </span>
              </span>
            </button>
            <button onClick={() => api.playback.next()} title="Next" className="w-10 h-10 rounded-full control-dial-outer p-1 flex items-center justify-center cursor-pointer transition-transform active:scale-95 shadow-md group">
              <span className="w-full h-full rounded-full dial-aluminum flex items-center justify-center border border-white/60 shadow-inner text-lg text-neutral-700 group-hover:text-neutral-900">⏭</span>
            </button>
            <button onClick={() => api.playback.toggleRepeat()} title="Repeat" className="w-10 h-10 rounded-full control-dial-outer p-1 flex items-center justify-center cursor-pointer transition-transform active:scale-95 shadow-md group">
              <span className="w-full h-full rounded-full dial-aluminum flex items-center justify-center border border-white/60 shadow-inner text-sm">
                <span className={status.repeat ? 'text-emerald-600 drop-shadow-[0_0_4px_#34d399]' : 'text-neutral-700 group-hover:text-neutral-900'}>🔁</span>
              </span>
            </button>
          </div>

          {/* Volume Dial with Dual 20-Segment LED VU Meters */}
          <div className="relative flex items-center justify-center py-2 mb-2">
            {/* Left 20-segment LED VU Bar */}
            <div className="absolute left-2 w-3 h-48 bg-black/60 rounded p-0.5 flex flex-col-reverse justify-between shadow-inner">
              {Array.from({ length: 20 }).map((_, i) => {
                const on = isPlaying && i / 19 <= vuL
                const col = i < 13 ? '#22c55e' : i < 17 ? '#eab308' : '#ef4444'
                return (
                  <div
                    key={i}
                    className="w-full h-1.5 rounded-sm"
                    style={{
                      backgroundColor: on ? col : 'transparent',
                      boxShadow: on ? `0 0 4px ${col}` : 'none',
                    }}
                  />
                )
              })}
            </div>

            {/* Central Aluminum Attenuator Dial */}
            <div className="relative w-48 h-48 rounded-full control-dial-outer p-2 flex items-center justify-center shrink-0">
              <div className="w-full h-full rounded-full dial-aluminum flex flex-col items-center justify-center relative shadow-2xl">
                <div
                  className="absolute inset-0 rounded-full pointer-events-none transition-transform duration-100"
                  style={{ transform: `rotate(${-135 + ((volume + 60) / 60) * 270}deg)` }}
                >
                  <div className="w-2 h-2 bg-neutral-800 rounded-full absolute top-3 left-1/2 -translate-x-1/2" />
                </div>

                <div className="flex flex-col items-center justify-center z-30 pointer-events-none">
                  <div className="flex items-baseline gap-0.5">
                    <span className="text-4xl font-extralight tracking-tight text-neutral-800 font-bold">{volume.toFixed(1)}</span>
                    <span className="text-xs font-bold text-neutral-600 uppercase">dB</span>
                  </div>
                </div>
                {/* APPLY: ダイヤル外に分離 — 音量inputとヒット領域を重ねない */}
                <button
                  type="button"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => { e.stopPropagation(); handleApply() }}
                  disabled={applying}
                  className={`absolute -bottom-2 left-1/2 -translate-x-1/2 z-30 w-12 h-12 rounded-full flex items-center justify-center text-[8px] font-bold tracking-widest uppercase transition-all cursor-pointer border border-neutral-400 ${
                    applying
                      ? 'bg-emerald-500 text-white shadow-inner scale-95'
                      : 'bg-gradient-to-b from-white to-gray-300 text-neutral-800 shadow-md active:scale-95'
                  }`}
                >
                  {applying ? 'WAIT' : 'APPLY'}
                </button>
                {/* 音量操作はダイヤル上部のリング領域のみ */}
                <input
                  type="range"
                  min="-60"
                  max="0"
                  step="0.5"
                  value={volume}
                  onChange={(e) => handleVolume(parseFloat(e.target.value))}
                  className="absolute inset-x-4 top-2 bottom-14 opacity-0 z-10 cursor-pointer"
                />
              </div>
            </div>

            {/* Right 20-segment LED VU Bar */}
            <div className="absolute right-2 w-3 h-48 bg-black/60 rounded p-0.5 flex flex-col-reverse justify-between shadow-inner">
              {Array.from({ length: 20 }).map((_, i) => {
                const on = isPlaying && i / 19 <= vuR
                const col = i < 13 ? '#22c55e' : i < 17 ? '#eab308' : '#ef4444'
                return (
                  <div
                    key={i}
                    className="w-full h-1.5 rounded-sm"
                    style={{
                      backgroundColor: on ? col : 'transparent',
                      boxShadow: on ? `0 0 4px ${col}` : 'none',
                    }}
                  />
                )
              })}
            </div>
          </div>

          {/* Mode & Output Badges */}
          <div className="flex items-center justify-center gap-8 mb-3">
            <div className="flex flex-col items-center relative">
              <div className="w-14 h-14 rounded-full bg-white/40 backdrop-blur-md border border-black/10 flex items-center justify-center shadow-lg font-bold text-[9px] text-neutral-800 cursor-pointer">
                {mode.toUpperCase()}
              </div>
              <select
                value={mode}
                onChange={(e) => {
                  const m = e.target.value as 'pure' | 'dsp'
                  setMode(m)
                  api.dsp.apply({
                    mode: m,
                    device,
                    volume,
                    music_type: musicType,
                    eq_output: m === 'pure' ? 'none' : eqOutput,
                    crossfeed: m === 'pure' ? 'none' : crossfeed,
                    crossfeed_intensity: crossfeedIntensity,
                    hum_noise: m === 'pure' ? 'none' : humFilter,
                    reverb: m === 'pure' ? 'none' : ambience,
                    reverb_intensity: ambienceIntensity,
                  }).catch(err => console.error('Mobile mode apply failed', err))
                }}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              >
                <option value="dsp">DSP</option>
                <option value="pure">PURE</option>
              </select>
              <span className="text-[10px] font-bold text-white tracking-widest mt-1">MODE</span>
            </div>

            <div className="flex flex-col items-center relative">
              <div className="w-14 h-14 rounded-full bg-white/40 backdrop-blur-md border border-black/10 flex items-center justify-center shadow-lg font-bold text-[9px] text-neutral-800 cursor-pointer text-center px-1 truncate">
                {devices.find(d => d.id === device)?.name?.slice(0, 7) || 'DEVICE'}
              </div>
              <select
                value={device}
                onChange={(e) => {
                  const d = e.target.value
                  setDevice(d)
                  api.dsp.apply({
                    mode,
                    device: d,
                    volume,
                    music_type: musicType,
                    eq_output: eqOutput,
                    crossfeed,
                    crossfeed_intensity: crossfeedIntensity,
                    hum_noise: humFilter,
                    reverb: ambience,
                    reverb_intensity: ambienceIntensity,
                  }).catch(err => console.error('Mobile device apply failed', err))
                }}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              >
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
              <span className="text-[10px] font-bold text-white tracking-widest mt-1">OUTPUT</span>
            </div>
          </div>

          {/* Lower Shutter Switchable Panel: Tabs / Browser vs DSP Drawer */}
          <div className="w-full bg-[#12161c] rounded-2xl overflow-hidden border border-white/10 shadow-2xl relative min-h-[340px]">
            {/* Header + ▽ DSP Trigger */}
            <div className="bg-black/60 px-3 py-2 flex items-center justify-between border-b border-white/10">
              <div className="flex gap-1.5">
                {(['queue', 'library', 'soundgenic', 'history', 'playlists'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-2 py-0.5 text-[9px] font-['Orbitron'] font-bold rounded ${
                      activeTab === tab ? 'bg-emerald-500/20 text-emerald-400' : 'text-white/40'
                    }`}
                  >
                    {tab === 'queue' ? 'QUE' : tab === 'library' ? 'LIB' : tab === 'soundgenic' ? 'SRV' : tab === 'history' ? 'HIS' : 'LIST'}
                    {tab === 'queue' && status.queue_length > 0 && (
                      <span className="ml-1 text-[8px] opacity-75">{status.queue_length}</span>
                    )}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setDspOpen(true)}
                className="flex items-center gap-1 text-[11px] font-['Orbitron'] font-black text-white hover:text-emerald-400 cursor-pointer ml-2"
              >
                <span>▽</span>
                <span>DSP</span>
              </button>
            </div>

            {/* Tab Views */}
            <div className="p-2 max-h-[340px] overflow-y-auto">
              {activeTab === 'queue'      && <QueueView />}
              {activeTab === 'library'    && <LibraryView currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
              {activeTab === 'soundgenic' && <SoundgenicView currentUri={track?.uri} onAddToPlaylist={handleAddToPlaylist} />}
              {activeTab === 'history'    && <HistoryView />}
              {activeTab === 'playlists'  && <PlaylistsView />}
            </div>

            {/* DSP Rolldown Drawer Overlay */}
            {dspOpen && (
              <div className="absolute inset-0 z-50 bg-[#8c9a9b] brushed-silver-panel p-3.5 flex flex-col justify-between overflow-y-auto animate-shutter">
                {/* Drawer Header */}
                <div className="flex items-center justify-between border-b border-black/20 pb-1.5">
                  <span className="text-[11px] font-['Orbitron'] font-bold text-neutral-900 tracking-wider">◆ DSP DASHBOARD ENGINE</span>
                  <button
                    onClick={() => setDspOpen(false)}
                    className="flex items-center gap-1 text-[11px] font-['Orbitron'] font-black text-neutral-900 hover:text-black cursor-pointer"
                  >
                    <span>PLY</span>
                    <span>▲</span>
                  </button>
                </div>

                {/* Telemetry Box */}
                <div className="bg-black/85 border border-emerald-500/40 rounded p-2 my-2 shadow-inner font-mono text-[9px]">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-emerald-300">
                    <div className="flex justify-between"><span>MODE</span><strong className="text-white">{mode.toUpperCase()}</strong></div>
                    <div className="flex justify-between"><span>FORMAT</span><strong className="text-white">{track?.source === 'upnp' ? 'STREAM' : 'FLAC'}</strong></div>
                    <div className="flex justify-between"><span>ATTN</span><strong className="text-white">{volume.toFixed(1)} dB</strong></div>
                    <div className="flex justify-between"><span>LATENCY</span><strong className="text-white">0.42 ms</strong></div>
                  </div>
                </div>

                {/* 6 Rotary Dials */}
                <div className="grid grid-cols-3 gap-y-2 gap-x-2 my-1 place-items-center">
                  {/* Output EQ */}
                  <div className="flex flex-col items-center gap-1">
                    <button
                      onClick={() => cycleDial(eqOutput, EQ_OUT_OPTS, setEqOutput, 'eq_output')}
                      className="w-12 h-12 rounded-full dial-aluminum shadow border border-neutral-400 relative flex items-center justify-center cursor-pointer"
                    >
                      <div className="w-1 h-2 bg-neutral-800 rounded-full absolute top-1" />
                      <span className="text-[7px] font-bold text-neutral-800 text-center leading-none px-0.5">{EQ_OUT_LBL[eqOutput] || eqOutput}</span>
                    </button>
                    <span className="text-[8px] font-bold text-neutral-900 uppercase">OUTPUT EQ</span>
                  </div>

                  {/* Source EQ */}
                  <div className="flex flex-col items-center gap-1">
                    <button
                      onClick={() => cycleDial(musicType, EQ_SRC_OPTS, setMusicType, 'music_type')}
                      className="w-12 h-12 rounded-full dial-aluminum shadow border border-neutral-400 relative flex items-center justify-center cursor-pointer"
                    >
                      <div className="w-1 h-2 bg-neutral-800 rounded-full absolute top-1" />
                      <span className="text-[7px] font-bold text-neutral-800 text-center leading-none px-0.5">{EQ_SRC_LBL[musicType] || musicType}</span>
                    </button>
                    <span className="text-[8px] font-bold text-neutral-900 uppercase">SOURCE EQ</span>
                  </div>

                  {/* Hum Filter */}
                  <div className="flex flex-col items-center gap-1">
                    <button
                      onClick={() => cycleDial(humFilter, HUM_OPTS, setHumFilter, 'hum_noise')}
                      className="w-12 h-12 rounded-full dial-aluminum shadow border border-neutral-400 relative flex items-center justify-center cursor-pointer"
                    >
                      <div className="w-1 h-2 bg-neutral-800 rounded-full absolute top-1" />
                      <span className="text-[7px] font-bold text-neutral-800">{HUM_LBL[humFilter]}</span>
                    </button>
                    <span className="text-[8px] font-bold text-neutral-900 uppercase">HUM FILTER</span>
                  </div>

                  {/* Ambience + Underbar（モバイル） */}
                  <div className="flex flex-col items-center gap-1">
                    <button
                      onClick={() => cycleDial(ambience, REV_OPTS, setAmbience, 'reverb')}
                      className="w-12 h-12 rounded-full dial-aluminum shadow border border-neutral-400 relative flex items-center justify-center cursor-pointer"
                    >
                      <div className="w-1 h-2 bg-neutral-800 rounded-full absolute top-1" />
                      <span className="text-[7px] font-bold text-neutral-800 text-center leading-none px-0.5">{REV_LBL[ambience] || ambience}</span>
                    </button>
                    <span className="text-[8px] font-bold text-neutral-900 uppercase">AMBIENCE</span>
                    <div
                      className="w-12 h-1.5 bg-neutral-400 rounded-full overflow-hidden cursor-pointer"
                      onClick={(e) => {
                        const r = e.currentTarget.getBoundingClientRect()
                        const val = Math.max(0, Math.min(100, Math.round(((e.clientX - r.left) / r.width) * 100)))
                        setAmbienceIntensity(val)
                        syncDspParams({ reverb_intensity: val })
                      }}
                    >
                      <div className="h-full bg-emerald-600 rounded-full" style={{ width: `${ambience === 'none' ? 0 : ambienceIntensity}%` }} />
                    </div>
                  </div>

                  {/* Crossfeed + Underbar（モバイル） */}
                  <div className="flex flex-col items-center gap-1">
                    <button
                      onClick={() => cycleDial(crossfeed, XF_OPTS, setCrossfeed, 'crossfeed')}
                      className="w-12 h-12 rounded-full dial-aluminum shadow border border-neutral-400 relative flex items-center justify-center cursor-pointer"
                    >
                      <div className="w-1 h-2 bg-neutral-800 rounded-full absolute top-1" />
                      <span className="text-[7px] font-bold text-neutral-800">{XF_LBL[crossfeed]}</span>
                    </button>
                    <span className="text-[8px] font-bold text-neutral-900 uppercase">CROSSFEED</span>
                    <div
                      className="w-12 h-1.5 bg-neutral-400 rounded-full overflow-hidden cursor-pointer"
                      onClick={(e) => {
                        const r = e.currentTarget.getBoundingClientRect()
                        const val = Math.max(0, Math.min(100, Math.round(((e.clientX - r.left) / r.width) * 100)))
                        setCrossfeedIntensity(val)
                        syncDspParams({ crossfeed_intensity: val })
                      }}
                    >
                      <div className="h-full bg-emerald-600 rounded-full" style={{ width: `${crossfeed === 'none' ? 0 : crossfeedIntensity}%` }} />
                    </div>
                  </div>

                  {/* CTC + Underbar（Stage 7: モバイル PRESET ダイヤル廃止 → その位置へ CTC を配置） */}
                  <div className="flex flex-col items-center gap-1">
                    <button
                      onClick={() => cycleDial(ctc, CTC_OPTS, setCtc, 'ctc')}
                      className="w-12 h-12 rounded-full dial-aluminum shadow border border-neutral-400 relative flex items-center justify-center cursor-pointer"
                    >
                      <div className="w-1 h-2 bg-neutral-800 rounded-full absolute top-1" />
                      <span className="text-[7px] font-bold text-neutral-800">{CTC_LBL[ctc]}</span>
                    </button>
                    <span className="text-[8px] font-bold text-neutral-900 uppercase">CTC</span>
                    <div
                      className="w-12 h-1.5 bg-neutral-400 rounded-full overflow-hidden cursor-pointer"
                      onClick={(e) => {
                        const r = e.currentTarget.getBoundingClientRect()
                        const val = Math.max(0, Math.min(100, Math.round(((e.clientX - r.left) / r.width) * 100)))
                        setCtcIntensity(val)
                        syncDspParams({ ctc_intensity: val })
                      }}
                    >
                      <div className="h-full bg-emerald-600 rounded-full" style={{ width: `${ctc === 'none' ? 0 : ctcIntensity}%` }} />
                    </div>
                  </div>
                </div>

                {/* Mobile Preset Registration — 適用（クリック）＋ 保存はここで行う */}
                <div className="flex flex-col gap-2 pt-2 border-t border-black/15">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {presets.length === 0 ? (
                      <span className="text-[9px] text-neutral-600">No presets saved</span>
                    ) : (
                      presets.map((p) => (
                        <button
                          key={p}
                          onClick={() => setPresetName(p)}
                          className={`px-2 py-0.5 text-[9px] font-bold rounded border transition-colors cursor-pointer ${
                            presetName === p
                              ? 'bg-emerald-700 text-white border-emerald-800'
                              : 'bg-neutral-200 text-neutral-800 border-neutral-500 hover:bg-neutral-300'
                          }`}
                        >
                          {p}
                        </button>
                      ))
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={presetInput}
                      onChange={(e) => setPresetInput(e.target.value)}
                      placeholder="Preset name..."
                      className="flex-1 bg-black/90 text-white border border-neutral-500 rounded px-2 py-1 text-[10px] font-mono placeholder:text-white/40 focus:outline-none"
                    />
                    <button
                      onClick={() => {
                        const name = presetInput.trim()
                        if (name && !presets.includes(name)) {
                          setPresets((p) => [...p, name])
                          setPresetName(name)
                          setPresetInput('')
                        }
                      }}
                      className="px-3 py-1 bg-emerald-700 text-white text-[10px] font-['Orbitron'] font-bold rounded shadow cursor-pointer"
                    >
                      SAVE
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Add To Playlist Modal */}
      {playlistTarget && (
        <AddToPlaylistModal
          tracks={playlistTarget}
          onClose={() => setPlaylistTarget(null)}
        />
      )}

    </div>
  )
}