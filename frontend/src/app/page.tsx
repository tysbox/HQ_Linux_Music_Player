'use client';
import { useState, useEffect, useRef, useCallback } from 'react';

// ─── API endpoints ────────────────────────────────────────────────────────────
const API = typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : 'http://localhost:8000';
const WS_URL = typeof window !== 'undefined'
  ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.hostname}:8000/ws/now_playing`
  : 'ws://localhost:8000/ws/now_playing';

// ─── Types ────────────────────────────────────────────────────────────────────
interface DspConfig {
  volume: number;
  music_type: string;
  eq_output: string;
  crossfeed: string;
  hum_noise: string;
  reverb: string;
  reverb_intensity: number;
}

interface SavedAudioConfig extends DspConfig {
  mode: 'pure' | 'dsp';
  device: string;
}

interface NowPlaying {
  title: string;
  artist: string;
  album: string;
  file: string;
  song_id: string;
  state: string;
  audio?: string;
  elapsed?: number;
  duration?: number;
}

interface Device {
  id: string;
  name: string;
}

// ─── Dial option definitions ──────────────────────────────────────────────────
const fmtTime = (s: number) => {
  const t = Math.floor(s);
  const m = Math.floor(t / 60);
  const sec = t % 60;
  return `${m}:${sec.toString().padStart(2, '0')}`;
};

const HUM_OPTS = ['none', '50hz', '60hz'];
const HUM_LBL: Record<string, string> = { none: 'OFF', '50hz': '50 Hz', '60hz': '60 Hz' };

const EQ_OPTS = ['none', 'jazz', 'classical', 'electronic', 'vocal'];
const EQ_LBL: Record<string, string> = {
  none: 'OFF', jazz: 'Jazz', classical: 'Classical',
  electronic: 'Electronic', vocal: 'Vocal',
};

const OUT_OPTS = ['none', 'studio-monitors', 'JBL-Speakers', 'planar-magnetic', 'loud-speaker', 'Tube-Warmth', 'Crystal-Clarity'];
const OUT_LBL: Record<string, string> = {
  none: 'OFF', 'studio-monitors': 'Studio Mon.', 'JBL-Speakers': 'JBL Speakers',
  'planar-magnetic': 'Planar Mag.', 'loud-speaker': 'Loudness',
  'Tube-Warmth': 'Tube Warmth', 'Crystal-Clarity': 'Crystal Clarity',
};

const REV_OPTS = ['none', 'hall', 'jazz_club'];
const REV_LBL: Record<string, string> = { none: 'OFF', hall: 'Symphony Hall', jazz_club: 'Jazz Club' };

const XF_OPTS = ['none', 'light', 'standard'];
const XF_LBL: Record<string, string> = { none: 'OFF', light: 'Light', standard: 'Standard' };

// ─── VU Meters + Volume Dial ──────────────────────────────────────────────────
function VUMetersAndDial({
  playing,
  volume,
  handleVolume,
  applySettings,
  applying,
  volBypass,
}: {
  playing: boolean;
  volume: number;
  handleVolume: (v: number) => void;
  applySettings: () => void;
  applying: boolean;
  volBypass: boolean;
}) {
  const [vuL, setVuL] = useState(0);
  const [vuR, setVuR] = useState(0);
  const vuTarget = useRef({ l: 0, r: 0 });
  const vuFrameRef = useRef<number | null>(null);
  const vuJitterRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const animate = () => {
      const noise = playing ? (Math.random() - 0.5) * 0.05 : 0;
      setVuL(p => Math.max(0, Math.min(1, p + (vuTarget.current.l - p) * 0.14 + noise)));
      setVuR(p => Math.max(0, Math.min(1, p + (vuTarget.current.r - p) * 0.14 + noise * 0.8)));
      vuFrameRef.current = requestAnimationFrame(animate);
    };
    if (playing) {
      vuTarget.current = { l: 0.55 + Math.random() * 0.2, r: 0.48 + Math.random() * 0.2 };
      vuJitterRef.current = setInterval(() => {
        vuTarget.current = { l: 0.42 + Math.random() * 0.35, r: 0.38 + Math.random() * 0.35 };
      }, 700);
    } else {
      vuTarget.current = { l: 0, r: 0 };
    }
    vuFrameRef.current = requestAnimationFrame(animate);
    return () => {
      if (vuFrameRef.current) cancelAnimationFrame(vuFrameRef.current);
      if (vuJitterRef.current) clearInterval(vuJitterRef.current);
    };
  }, [playing]);

  // Needle rotation: volume range -60 to 0, map to CSS rotation
  // At -60: needle points far left (~-135deg), at 0: needle points far right (~+135deg)
  const needleAngle = -135 + ((volume + 60) / 60) * 270;

  return (
    <div className="flex items-center justify-center gap-10 w-full shrink-0">
      {/* LEFT VU METER */}
      <div className="h-64 w-2.5 bg-black/25 rounded-full overflow-hidden flex flex-col-reverse">
        <div
          className="vu-meter-bar w-full transition-all duration-75"
          style={{ height: `${vuL * 100}%` }}
        />
      </div>

      {/* MAIN VOLUME DIAL */}
      <div className="relative w-72 h-72 rounded-full control-dial-outer p-2.5 flex items-center justify-center shrink-0">
        <div className="w-full h-full rounded-full dial-aluminum flex flex-col items-center justify-center relative shrink-0">
          {/* Rotating needle indicator */}
          <div
            className="absolute inset-0 rounded-full pointer-events-none transition-transform duration-100"
            style={{ transform: `rotate(${needleAngle}deg)` }}
          >
            <div className="w-2.5 h-2.5 bg-on-surface/90 rounded-full absolute top-4 left-1/2 -translate-x-1/2" />
          </div>

          {/* Center display */}
          <div className="flex flex-col items-center justify-center z-30 pointer-events-none">
            <div className="flex items-baseline gap-1.5">
              {volBypass ? (
                <span className="text-4xl font-bold text-gray-500 tracking-tight">BYPASS</span>
              ) : (
                <>
                  <span className="text-6xl font-light tracking-tighter text-on-surface font-bold text-white">
                    {volume.toFixed(1)}
                  </span>
                  <span className="text-xl font-bold text-white uppercase tracking-wider">dB</span>
                </>
              )}
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); applySettings(); }}
              disabled={applying}
              className={`mt-6 w-20 h-20 rounded-full flex items-center justify-center text-[10px] font-bold tracking-[0.2em] uppercase transition-all cursor-pointer pointer-events-auto border border-gray-500/50 ${
                applying
                  ? 'bg-gradient-to-b from-green-300 to-green-500 text-white shadow-[inset_0_2px_4px_rgba(255,255,255,0.5),0_2px_4px_rgba(0,0,0,0.3)]'
                  : 'bg-gradient-to-b from-gray-100 to-gray-400 text-gray-800 shadow-[inset_0_2px_4px_rgba(255,255,255,0.9),0_6px_12px_rgba(0,0,0,0.4)] active:shadow-[inset_0_4px_8px_rgba(0,0,0,0.4),0_2px_4px_rgba(255,255,255,0.5)] active:translate-y-1'
              }`}
            >
              {applying ? 'WAIT' : 'APPLY'}
            </button>
          </div>

          {/* Invisible range input overlay for drag interaction */}
          <input
            type="range"
            min="-60"
            max="0"
            step="1"
            value={volume}
            onChange={e => handleVolume(Number(e.target.value))}
            disabled={volBypass}
            className="absolute inset-0 w-full h-full opacity-0 z-20"
            style={{ cursor: volBypass ? 'default' : 'pointer' }}
          />
        </div>
      </div>

      {/* RIGHT VU METER */}
      <div className="h-64 w-2.5 bg-black/25 rounded-full overflow-hidden flex flex-col-reverse">
        <div
          className="vu-meter-bar w-full transition-all duration-75"
          style={{ height: `${vuR * 100}%` }}
        />
      </div>
    </div>
  );
}

// ─── SmallDial ────────────────────────────────────────────────────────────────
function SmallDial({
  label,
  value,
  options,
  labels,
  onChange,
  showBar = false,
  barValue = 5,
  onBarChange,
}: {
  label: string;
  value: string;
  options: string[];
  labels: Record<string, string>;
  onChange: (v: string) => void;
  showBar?: boolean;
  barValue?: number;
  onBarChange?: (v: number) => void;
}) {
  const idx = Math.max(0, options.indexOf(value));
  const total = options.length;
  // Arc: -135° (min) to +135° (max) — 270° sweep
  const angle = total > 1 ? -135 + (idx / (total - 1)) * 270 : -135;
  const isOff = idx === 0;

  const cycleOption = () => {
    const nextIdx = (idx + 1) % total;
    onChange(options[nextIdx]);
  };

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Dial knob */}
      <div
        className="w-20 h-20 rounded-full control-dial-outer p-1.5 flex items-center justify-center cursor-pointer shadow-xl"
        onClick={cycleOption}
        title={`${label}: click to cycle`}
      >
        <div className="w-full h-full rounded-full dial-aluminum relative">
          {/* Rotating marker */}
          <div
            className="absolute inset-0 rounded-full pointer-events-none transition-transform duration-300"
            style={{ transform: `rotate(${angle}deg)` }}
          >
            <div
              className="w-1.5 h-4 rounded-full absolute left-1/2 top-2 -translate-x-1/2"
              style={{ background: isOff ? 'rgba(0,0,0,0.25)' : 'rgba(0,0,0,0.8)' }}
            />
          </div>
          {/* OFF label */}
          {isOff && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <span className="text-[10px] font-bold text-on-surface uppercase opacity-40">Off</span>
            </div>
          )}
        </div>
      </div>

      {/* Label + value / bar */}
      <div className="flex flex-col items-center gap-1.5 text-center w-full">
        <p className="text-[10px] font-bold tracking-[0.25em] uppercase text-white">{label}</p>

        {showBar ? (
          <>
            <div
              className="level-bar-bg cursor-pointer w-full max-w-[70px]"
              onClick={(e) => {
                if (isOff || !onBarChange) return;
                const rect = e.currentTarget.getBoundingClientRect();
                const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                onBarChange(Math.max(1, Math.round(pct * 10)));
              }}
            >
              <div
                className="level-bar-fill transition-all duration-300"
                style={{ width: isOff ? '0%' : `${barValue * 10}%` }}
              />
            </div>
            <span className="text-[9px] font-bold text-white uppercase">
              {labels[value] ?? value}
            </span>
            <span className="text-[9px] font-bold text-white uppercase">
              {isOff ? '—' : `${barValue * 10}%`}
            </span>
          </>
        ) : (
          <span className="text-[9px] font-bold text-white uppercase">
            {labels[value] ?? value}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function App() {
  const [mounted, setMounted] = useState(false);
  const [mode, setMode] = useState<'pure' | 'dsp'>('pure');
  const [device, setDevice] = useState('');
  const [devices, setDevices] = useState<Device[]>([]);
  const [volume, setVolume] = useState(-5);
  const [humNoise, setHumNoise] = useState('none');
  const [musicType, setMusicType] = useState('none');
  const [eqOutput, setEqOutput] = useState('none');
  const [reverb, setReverb] = useState('none');
  const [reverbInt, setReverbInt] = useState(5);
  const [crossfeed, setCrossfeed] = useState('none');
  const [crossInt, setCrossInt] = useState(5);
  const [applying, setApplying] = useState(false);
  const [wsStatus, setWsStatus] = useState<'connecting' | 'ok' | 'error'>('connecting');
  const [nowPlaying, setNowPlaying] = useState<NowPlaying>({
    title: '', artist: '', album: '', file: '', song_id: '', state: 'stop', audio: '', elapsed: 0, duration: 0,
  });
  const [formatBadge, setFormatBadge] = useState('');
  const [displayElapsed, setDisplayElapsed] = useState(0);

  // Presets
  const [presets, setPresets] = useState<Record<string, DspConfig>>({});
  const [presetName, setPresetName] = useState('');

  // Derived flags — same logic as original
  const isBt = device.includes('bluealsa');
  const btFallback = mode === 'pure' && isBt;
  // In pure mode on non-BT device, volume is bypassed (hardware handles it)
  const volBypass = mode === 'pure' && !btFallback;

  useEffect(() => { setMounted(true); }, []);

  // ── WebSocket ──────────────────────────────────────────────────────────────
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setWsStatus('connecting');
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => { setWsStatus('ok'); if (retryRef.current) clearTimeout(retryRef.current); };
    ws.onclose = () => { setWsStatus('error'); retryRef.current = setTimeout(connectWS, 3000); };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data) as NowPlaying & { error?: string };
        if (!d.error) {
          setNowPlaying(d);
          setDisplayElapsed(d.elapsed ?? 0);
          // Derive format badge from file extension + audio info from MPD
          const ext = d.file?.split('.').pop()?.toUpperCase() ?? '';
          const fmt = ext && ['FLAC', 'WAV', 'AIFF', 'DSD', 'DSF', 'DFF', 'MP3', 'AAC'].includes(ext) ? ext : '';
          if (fmt && d.audio) {
            const [rateStr, bitsStr] = d.audio.split(':');
            const khz = rateStr ? (parseInt(rateStr) / 1000).toFixed(rateStr.endsWith('000') ? 0 : 1) : '';
            const bits = bitsStr || '';
            setFormatBadge(bits && khz ? `${fmt} ${bits}bit / ${khz}kHz` : fmt);
          } else {
            setFormatBadge(fmt);
          }
        }
      } catch { /* ignore parse errors */ }
    };
    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connectWS();
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connectWS]);

  // ── Progress timer ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (nowPlaying.state !== 'play') return;
    const id = setInterval(() => {
      setDisplayElapsed(p => p + 1);
    }, 1000);
    return () => clearInterval(id);
  }, [nowPlaying.state, nowPlaying.song_id]);

  // ── Device list ────────────────────────────────────────────────────────────
  const fetchDevices = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/devices`);
      const d: Device[] = await r.json();
      setDevices(d);
      if (!device && d.length > 0) {
        const usb = d.find(x => x.id.includes('plughw') && !x.id.includes('1,0'));
        setDevice(usb ? usb.id : d[0].id);
      }
    } catch { /* network unavailable */ }
  }, [device]);

  useEffect(() => { fetchDevices(); }, []);

  const fetchSavedConfig = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/config`);
      if (!r.ok) return;
      const cfg: SavedAudioConfig = await r.json();
      setMode(cfg.mode === 'dsp' ? 'dsp' : 'pure');
      if (cfg.device) setDevice(cfg.device);
      setVolume(cfg.volume);
      setMusicType(cfg.music_type);
      setEqOutput(cfg.eq_output);
      setCrossfeed(cfg.crossfeed);
      setHumNoise(cfg.hum_noise);
      setReverb(cfg.reverb);
      setReverbInt(cfg.reverb_intensity);
    } catch {}
  }, []);

  useEffect(() => { fetchSavedConfig(); }, [fetchSavedConfig]);

  // ── Presets ────────────────────────────────────────────────────────────────
  const fetchPresets = useCallback(async () => {
    try { setPresets(await (await fetch(`${API}/api/presets`)).json()); } catch {}
  }, []);

  useEffect(() => { fetchPresets(); }, []);

  const savePreset = async () => {
    if (!presetName.trim()) return;
    const config: DspConfig = {
      volume, music_type: musicType, eq_output: eqOutput, crossfeed,
      hum_noise: humNoise, reverb, reverb_intensity: reverbInt,
    };
    try {
      const r = await fetch(`${API}/api/presets/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: presetName.trim(), config }),
      });
      const d = await r.json();
      if (d.status === 'success') { setPresets(d.presets); setPresetName(''); }
    } catch {}
  };

  const loadPreset = (name: string) => {
    const p = presets[name];
    if (!p) return;
    setVolume(p.volume);
    setMusicType(p.music_type);
    if (p.eq_output) setEqOutput(p.eq_output);
    setCrossfeed(p.crossfeed);
    setHumNoise(p.hum_noise);
    setReverb(p.reverb);
    setReverbInt(p.reverb_intensity);
  };

  const deletePreset = async (name: string) => {
    try {
      const r = await fetch(`${API}/api/presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
      setPresets((await r.json()).presets);
    } catch {}
  };

  // ── Volume — DSPモード（BT含む）では即時 /api/volume に送信 ─────────────
  const handleVolume = async (v: number) => {
    setVolume(v);
    if (!volBypass) {
      try {
        await fetch(`${API}/api/volume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ volume: v }),
        });
      } catch {}
    }
  };

  // ── Apply ──────────────────────────────────────────────────────────────────
  const applySettings = async () => {
    if (!device || device === 'none' || device === 'error') {
      alert('有効な出力デバイスを選択してください');
      return;
    }
    setApplying(true);
    try {
      const r = await fetch(`${API}/api/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode, device, volume,
          music_type: musicType,
          eq_output: eqOutput,
          crossfeed,
          hum_noise: humNoise,
          reverb,
          reverb_intensity: reverbInt,
        }),
      });
      if (!r.ok) {
        const txt = await r.text();
        alert(`Apply failed: ${r.status} ${r.statusText}\n${txt}`);
      }
    } catch (err) {
      alert(`Apply failed: ${err}`);
    } finally {
      setApplying(false);
    }
  };

  const artUrl = nowPlaying.song_id
    ? `${API}/api/art?file=${encodeURIComponent(nowPlaying.file)}&artist=${encodeURIComponent(nowPlaying.artist)}&album=${encodeURIComponent(nowPlaying.album)}&_ts=${nowPlaying.song_id}`
    : '';

  // Progress bar percentage
  const progressPct = nowPlaying.duration
    ? Math.min(100, (displayElapsed / nowPlaying.duration) * 100)
    : 0;

  if (!mounted) return null;

  return (
    <div className="font-body bg-[#050505] flex justify-center items-start min-h-screen m-0 overflow-x-hidden py-10">
      <style>{`
        :root {
          --color-on-surface: #2d3436;
          --color-on-surface-variant: #636e72;
          --color-surface: #f5f6fa;
        }
        .material-symbols-outlined {
          font-variation-settings: 'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24;
        }
        .brushed-silver-panel {
          background-color: #95a5a6;
          background-image:
            radial-gradient(circle at 50% -10%, rgba(255,255,255,1) 0%, transparent 60%),
            radial-gradient(circle at 10% 40%, rgba(255,255,255,0.6) 0%, transparent 30%),
            radial-gradient(circle at 90% 70%, rgba(255,255,255,0.5) 0%, transparent 30%),
            linear-gradient(180deg, #bdc3c7 0%, #95a5a6 20%, #7f8c8d 60%, #2c3e50 100%),
            repeating-linear-gradient(90deg, rgba(255,255,255,0.08) 0px, rgba(255,255,255,0.08) 1px, transparent 1px, transparent 2px);
          box-shadow: inset 0 0 150px rgba(0,0,0,0.5), inset 0 10px 30px rgba(255,255,255,0.8);
        }
        .light-oak-frame {
          background: #8e6d45;
          background-image:
            linear-gradient(to right, rgba(0,0,0,0.3) 0%, transparent 8%, transparent 92%, rgba(0,0,0,0.3) 100%),
            repeating-linear-gradient(45deg, rgba(0,0,0,0.08) 0%, rgba(0,0,0,0.08) 1.5%, transparent 1.5%, transparent 12%),
            linear-gradient(135deg, #a68154 0%, #8e6d45 50%, #6e5233 100%);
          box-shadow: inset 0 0 100px rgba(0,0,0,0.6), 0 60px 120px rgba(0,0,0,0.7);
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
        .level-bar-bg {
          background: rgba(0,0,0,0.4);
          height: 6px;
          width: 70px;
          position: relative;
          overflow: hidden;
          border-radius: 9999px;
        }
        .level-bar-fill {
          background: #39FF14;
          height: 100%;
          position: absolute;
          left: 0;
          top: 0;
          box-shadow: 0 0 8px #39FF14, 0 0 15px #39FF14;
        }
        .album-art-container {
          box-shadow: 0 40px 80px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.4);
          background: #ffffff;
        }
        .text-on-surface { color: var(--color-on-surface); }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
      `}</style>

      <div className="w-[800px] flex items-center justify-center h-fit transform scale-[0.45] sm:scale-[0.6] md:scale-[0.8] lg:scale-100 origin-top pt-20 mb-20">
        <div className="light-oak-frame rounded-[6rem] w-full pt-8 pb-8 px-8">
          <div className="brushed-silver-panel rounded-[4rem] overflow-hidden relative flex flex-col pt-[26px]">

            {/* HEADER */}
            {/* Top header removed as requested */}

            {/* BLUETOOTH WARNING — preserved from original */}
            {btFallback && (
              <div style={{ padding: '8px 24px', background: 'rgba(234,179,8,0.12)', borderTop: '0.5px solid rgba(234,179,8,0.25)', borderBottom: '0.5px solid rgba(234,179,8,0.25)' }}>
                <span style={{ fontSize: 12, color: 'rgba(234,179,8,0.9)' }}>
                  ⚠️ Bluetooth はビットパーフェクト非対応のためエフェクト OFF の DSP で再生します
                </span>
              </div>
            )}

            <main className="flex-grow flex flex-col items-center px-12 pt-12 overflow-hidden pb-12">

              {/* MPD STATUS & NOW PLAYING */}
              <div className="w-full flex flex-col items-center gap-6 mb-6 shrink-0">
                <div className="w-full max-w-[650px] bg-black/90 rounded-sm border-2 border-white/5 p-4 flex flex-col gap-2 shadow-[inset_0_0_20px_rgba(0,0,0,1),0_0_15px_rgba(0,0,0,0.5)] mb-2">
                  {/* Status row */}
                  <div className="flex justify-between items-center px-2">
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-1.5 h-1.5 rounded-full ${wsStatus === 'ok' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(52,211,153,0.8)]' : wsStatus === 'connecting' ? 'bg-yellow-500' : 'bg-gray-600'}`}
                        style={{ animation: wsStatus === 'connecting' ? 'pulse 1s infinite' : 'none' }}
                      />
                      <span
                        className={`text-[11px] font-bold tracking-[0.2em] uppercase font-mono ${wsStatus === 'ok' ? 'text-emerald-500' : wsStatus === 'connecting' ? 'text-yellow-500' : 'text-gray-500'}`}
                        style={{ textShadow: wsStatus === 'ok' ? '0 0 10px rgba(52,211,153,0.8)' : 'none' }}
                      >
                        {wsStatus === 'ok' ? 'MPD CONNECTED' : wsStatus === 'connecting' ? 'CONNECTING…' : 'DISCONNECTED — RETRYING'}
                      </span>
                    </div>
                    <span
                      className="text-[11px] font-bold text-red-600/90 tracking-[0.1em] uppercase font-mono"
                      style={{ textShadow: '0 0 8px rgba(220,38,38,0.6)' }}
                    >
                      {formatBadge || '---'}
                    </span>
                  </div>

                  <div className="h-px w-full bg-red-900/30" />

                  {/* Track info row */}
                  <div className="px-2 flex justify-between items-center gap-4">
                    <span
                      className="text-[13px] font-black text-red-600 tracking-[0.15em] uppercase font-mono truncate"
                      style={{ textShadow: '0 0 12px rgba(220,38,38,0.9)' }}
                    >
                      {nowPlaying.artist
                        ? `${nowPlaying.artist} — ${nowPlaying.title}`
                        : 'Not Playing'}
                    </span>
                    <span className="text-[11px] font-bold text-red-600/70 tracking-[0.1em] uppercase font-mono shrink-0">
                      {fmtTime(displayElapsed)} / {nowPlaying.duration ? fmtTime(nowPlaying.duration) : '--:--'}
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div className="px-2">
                    <div className="h-1 w-full bg-red-900/20 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-red-600/70 rounded-full transition-all duration-1000 linear"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* ALBUM ART */}
                <div className="w-full max-w-[650px] aspect-square album-art-container p-1 rounded-sm bg-white shrink-0">
                  {artUrl ? (
                    <img
                      alt="Current Track Art"
                      className="w-full h-full object-cover shadow-2xl"
                      src={artUrl}
                    />
                  ) : (
                    <div className="w-full h-full bg-gray-900 flex items-center justify-center shadow-2xl">
                      <span className="material-symbols-outlined text-6xl text-white/20">album</span>
                    </div>
                  )}
                </div>
              </div>

              {/* CENTRAL VOLUME DIAL WITH VU METERS */}
              <div className="w-full flex flex-col items-center mb-12 shrink-0">
                <VUMetersAndDial
                  playing={nowPlaying.state === 'play'}
                  volume={volume}
                  handleVolume={handleVolume}
                  applySettings={applySettings}
                  applying={applying}
                  volBypass={volBypass}
                />
              </div>

              {/* MODE AND OUTPUT DEVICE ROW */}
              <div className="flex justify-center items-center gap-16 mb-12 w-full shrink-0">

                {/* MODE SELECTOR */}
                <div className="flex flex-col items-center relative">
                  <div className="w-20 h-20 rounded-full border border-black/10 flex items-center justify-center bg-white/40 backdrop-blur-lg cursor-pointer shadow-xl relative overflow-hidden shrink-0">
                    <span className="text-[10px] font-black text-on-surface uppercase text-center leading-tight tracking-tighter pointer-events-none px-1 break-words">
                      {mode.toUpperCase()}
                    </span>
                    <select
                      value={mode}
                      onChange={e => setMode(e.target.value as 'pure' | 'dsp')}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    >
                      <option value="pure">PURE</option>
                      <option value="dsp">DSP</option>
                    </select>
                  </div>
                  <label className="text-[10px] uppercase tracking-[0.3em] font-bold text-white mt-4">Mode</label>
                </div>

                {/* OUTPUT DEVICE */}
                <div className="flex flex-col items-center relative">
                  <div className="w-20 h-20 rounded-full border border-black/10 flex items-center justify-center bg-white/40 backdrop-blur-lg cursor-pointer shadow-xl relative overflow-hidden shrink-0">
                    <span className="text-[10px] font-black text-on-surface uppercase text-center leading-tight tracking-tighter pointer-events-none px-1 break-words">
                      {devices.find(d => d.id === device)?.name?.slice(0, 8) || 'Select'}
                    </span>
                    <select
                      value={device}
                      onChange={e => setDevice(e.target.value)}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    >
                      {devices.map(d => (
                        <option key={d.id} value={d.id} disabled={d.id === 'none'}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex items-center gap-2 mt-4">
                    <label className="text-[10px] uppercase tracking-[0.3em] font-bold text-white">Output</label>
                    {/* Refresh button — matches original */}
                    <button
                      onClick={fetchDevices}
                      className="text-white/40 hover:text-white/70 text-xs transition-colors"
                      title="Refresh device list"
                    >↻</button>
                  </div>
                </div>
              </div>

              {/* 2×3 CONTROL GRID */}
              <div className="grid grid-cols-2 gap-x-20 gap-y-12 w-full mb-12 shrink-0">
                <SmallDial
                  label="Output EQ"
                  value={eqOutput}
                  options={OUT_OPTS}
                  labels={OUT_LBL}
                  onChange={setEqOutput}
                />
                <SmallDial
                  label="Source EQ"
                  value={musicType}
                  options={EQ_OPTS}
                  labels={EQ_LBL}
                  onChange={setMusicType}
                />
                <SmallDial
                  label="Crossfeed"
                  value={crossfeed}
                  options={XF_OPTS}
                  labels={XF_LBL}
                  onChange={setCrossfeed}
                  showBar
                  barValue={crossInt}
                  onBarChange={setCrossInt}
                />
                <SmallDial
                  label="Ambience"
                  value={reverb}
                  options={REV_OPTS}
                  labels={REV_LBL}
                  onChange={setReverb}
                  showBar
                  barValue={reverbInt}
                  onBarChange={setReverbInt}
                />
                <SmallDial
                  label="Hum Filter"
                  value={humNoise}
                  options={HUM_OPTS}
                  labels={HUM_LBL}
                  onChange={setHumNoise}
                />
                {/* 6th cell: quick-load preset dial */}
                <div className="flex flex-col items-center gap-3">
                  <div
                    className="w-20 h-20 rounded-full control-dial-outer p-1.5 flex items-center justify-center cursor-pointer shadow-xl"
                    onClick={() => {
                      const keys = Object.keys(presets);
                      if (keys.length === 0) return;
                      const currentIdx = keys.indexOf(presetName);
                      const nextIdx = (currentIdx + 1) % keys.length;
                      const next = keys[nextIdx];
                      setPresetName(next);
                      loadPreset(next);
                    }}
                    title="Click to cycle through saved presets"
                  >
                    <div className="w-full h-full rounded-full dial-aluminum relative flex items-center justify-center">
                      <span className="text-[8px] font-bold text-on-surface uppercase text-center leading-tight pointer-events-none px-1 opacity-60">
                        {Object.keys(presets).length === 0 ? 'No\nPreset' : presetName || 'Cycle'}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-col items-center gap-1.5 text-center w-full">
                    <p className="text-[10px] font-bold tracking-[0.25em] uppercase text-white">Preset</p>
                    <span className="text-[9px] font-bold text-white uppercase">
                      {presetName || '—'}
                    </span>
                  </div>
                </div>
              </div>

              {/* PRESET REGISTRATION PANEL */}
              <div className="w-full max-w-[650px] bg-black/60 rounded-xl border border-white/10 p-5 mb-8 flex flex-col gap-4 shadow-xl shrink-0">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold tracking-[0.2em] text-white/50 uppercase">🎛 Preset Reg.</span>
                </div>

                {/* Preset list (load + delete) */}
                <div className="flex flex-wrap gap-2">
                  {Object.keys(presets).length === 0 && (
                    <span className="text-[10px] text-white/30">No presets saved</span>
                  )}
                  {Object.keys(presets).map(name => (
                    <div
                      key={name}
                      className="flex items-center bg-white/5 rounded-full border border-white/10 overflow-hidden"
                    >
                      <button
                        onClick={() => { setPresetName(name); loadPreset(name); }}
                        className={`px-4 py-2 text-[10px] font-bold transition-colors ${presetName === name ? 'text-green-400' : 'text-white/80 hover:text-white'}`}
                      >
                        {name}
                      </button>
                      <button
                        onClick={() => {
                          deletePreset(name);
                          if (presetName === name) setPresetName('');
                        }}
                        className="px-3 py-2 text-[10px] text-red-400 hover:bg-red-500/20 transition-colors border-l border-white/10"
                        title="Delete Preset"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>

                {/* Save new preset */}
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    value={presetName}
                    onChange={e => setPresetName(e.target.value)}
                    placeholder="New preset name..."
                    className="flex-1 bg-black/50 border border-white/10 rounded-md px-4 py-2 text-[11px] text-white outline-none focus:border-white/30"
                    onKeyDown={e => e.key === 'Enter' && savePreset()}
                  />
                  <button
                    onClick={savePreset}
                    className="px-6 py-2 bg-green-500/20 text-green-400 border border-green-500/30 rounded-md text-[11px] font-bold hover:bg-green-500/30 transition-colors tracking-wider"
                  >
                    SAVE
                  </button>
                </div>
              </div>

            </main>
          </div>
        </div>
      </div>
    </div>
  );
}
