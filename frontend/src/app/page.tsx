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

const HUM_OPTS  = ['none', '50hz', '60hz'];
const HUM_LBL: Record<string, string> = { none: 'OFF', '50hz': '50 Hz', '60hz': '60 Hz' };

const EQ_OPTS   = ['none', 'jazz', 'classical', 'electronic', 'vocal'];
const EQ_LBL: Record<string, string>  = {
  none: 'OFF', jazz: 'Jazz', classical: 'Classical',
  electronic: 'Electronic', vocal: 'Vocal',
};

const OUT_OPTS = ['none', 'studio-monitors', 'JBL-Speakers', 'planar-magnetic', 'loud-speaker', 'Tube-Warmth', 'Crystal-Clarity'];
const OUT_LBL: Record<string, string> = {
  none: 'OFF', 'studio-monitors': 'Studio Mon.', 'JBL-Speakers': 'JBL Speakers',
  'planar-magnetic': 'Planar Mag.', 'loud-speaker': 'Loudness',
  'Tube-Warmth': 'Tube Warmth', 'Crystal-Clarity': 'Crystal Clarity',
};

const REV_OPTS  = ['none', 'hall', 'jazz_club'];
const REV_LBL: Record<string, string> = { none: 'OFF', hall: 'Symphony Hall', jazz_club: 'Jazz Club' };

const XF_OPTS   = ['none', 'light', 'standard'];
const XF_LBL: Record<string, string>  = { none: 'OFF', light: 'Light', standard: 'Standard' };

// ─── Dial geometry ────────────────────────────────────────────────────────────
// Arc: M 8 24 A 10 10 0 1 1 24 24  (270° sweep, lower-left to lower-right)
// Needle angle: 135° + frac×270° (in SVG coordinate space)
const DIAL_ARC_LEN = 2 * Math.PI * 10 * (270 / 360); // ≈ 47.12

function dialGeom(idx: number, total: number) {
  const frac      = total <= 1 ? 0 : idx / (total - 1);
  const angleDeg  = 135 + frac * 270;
  const angleRad  = (angleDeg * Math.PI) / 180;
  return {
    frac,
    nx:     16 + 9  * Math.cos(angleRad),
    ny:     16 + 9  * Math.sin(angleRad),
    filled: frac * DIAL_ARC_LEN,
  };
}

// ─── DialControl component ────────────────────────────────────────────────────
function DialControl({
  label, color, options, labels, value, onChange,
  showBar = false, barValue = 5, onBarChange,
}: {
  label: string;
  color: string;
  options: string[];
  labels: Record<string, string>;
  value: string;
  onChange: (v: string) => void;
  showBar?: boolean;
  barValue?: number;
  onBarChange?: (v: number) => void;
}) {
  const idx   = Math.max(0, options.indexOf(value));
  const isOff = idx === 0;
  const { nx, ny, filled } = dialGeom(idx, options.length);
  const dashOffset = DIAL_ARC_LEN - filled;

  return (
    <div style={{
      background: '#141414',
      border: '0.5px solid rgba(255,255,255,0.07)',
      borderRadius: 8,
      padding: '10px 12px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {/* Dial SVG */}
        <svg width="32" height="32" viewBox="0 0 32 32" style={{ flexShrink: 0 }}>
          <circle cx="16" cy="16" r="13" fill="#1a1a1a" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
          {/* Background track */}
          <path d="M 8 24 A 10 10 0 1 1 24 24"
            fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="3" strokeLinecap="round"/>
          {/* Filled arc */}
          {!isOff && filled > 0.5 && (
            <path d="M 8 24 A 10 10 0 1 1 24 24"
              fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
              strokeDasharray={DIAL_ARC_LEN}
              strokeDashoffset={dashOffset}
            />
          )}
          {/* Center pivot */}
          <circle cx="16" cy="16" r="2.5" fill="#0d0d0d" stroke="rgba(255,255,255,0.15)" strokeWidth="0.5"/>
          {/* Needle */}
          <line x1="16" y1="16" x2={nx} y2={ny}
            stroke={isOff ? 'rgba(255,255,255,0.22)' : color}
            strokeWidth="1.5" strokeLinecap="round"
          />
          {/* Tip */}
          <circle cx={nx} cy={ny} r="1.5" fill={isOff ? 'rgba(255,255,255,0.22)' : color}/>
        </svg>

        {/* Label + current value */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1px', marginBottom: 3 }}>
            {label}
          </div>
          <div style={{
            fontSize: 12,
            fontWeight: 500,
            color: isOff ? 'rgba(255,255,255,0.28)' : 'rgba(255,255,255,0.88)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {labels[value] ?? 'OFF'}
          </div>
        </div>

        {/* Prev / Next buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <button
            onClick={() => onChange(options[Math.max(0, idx - 1)])}
            disabled={idx === 0}
            style={{
              background: 'none', border: 'none', padding: '3px 5px', lineHeight: 1,
              fontSize: 10, cursor: idx === 0 ? 'default' : 'pointer',
              color: idx === 0 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.4)',
            }}
          >▲</button>
          <button
            onClick={() => onChange(options[Math.min(options.length - 1, idx + 1)])}
            disabled={idx === options.length - 1}
            style={{
              background: 'none', border: 'none', padding: '3px 5px', lineHeight: 1,
              fontSize: 10, cursor: idx === options.length - 1 ? 'default' : 'pointer',
              color: idx === options.length - 1 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.4)',
            }}
          >▼</button>
        </div>
      </div>

      {/* Intensity bar (reverb / crossfeed) */}
      {showBar && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.2)', width: 20 }}>
            {isOff ? 'OFF' : 'MIN'}
          </span>
          <div
            style={{
              flex: 1, height: 4, background: 'rgba(255,255,255,0.07)',
              borderRadius: 2, cursor: isOff ? 'default' : 'pointer', position: 'relative',
            }}
            onClick={(e) => {
              if (isOff || !onBarChange) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const pct  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              onBarChange(Math.max(1, Math.round(pct * 10)));
            }}
          >
            <div style={{
              height: '100%',
              width: isOff ? '0%' : `${barValue * 10}%`,
              background: isOff ? 'transparent' : color,
              borderRadius: 2,
              transition: 'width 0.12s',
            }}/>
            {!isOff && (
              <div style={{
                position: 'absolute',
                width: 10, height: 10,
                borderRadius: '50%',
                background: color,
                border: '2px solid #141414',
                top: '50%',
                left: `${barValue * 10}%`,
                transform: 'translate(-50%, -50%)',
              }}/>
            )}
          </div>
          <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.2)', width: 20, textAlign: 'right' }}>MAX</span>
          <span style={{ fontSize: 10, color: isOff ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.5)', width: 26, textAlign: 'right' }}>
            {isOff ? '—' : `${barValue * 10}%`}
          </span>
        </div>
      )}
    </div>
  );
}

// ─── VU Meter: analog half-circle needle ─────────────────────────────────────
// Arc: M 10 68 A 55 55 0 0 1 120 68 (180° semicircle, center 65,68, radius 55)
// Needle angle: Math.PI × (1 + level)  → level=0→left, 0.5→up, 1→right
const VU_ARC_LEN = Math.PI * 55; // ≈ 172.8

function VUMeter({ level, label, uid }: { level: number; label: string; uid: string }) {
  const lv  = Math.max(0, Math.min(1, level));
  const ang = Math.PI * (1 + lv);
  const nx  = 65 + 48 * Math.cos(ang);
  const ny  = 68 + 48 * Math.sin(ang);
  const dbVal = lv < 0.02 ? '−∞' : `${Math.round(-60 + lv * 63)} dB`;
  const dbClr = lv > 0.85 ? '#ef4444' : lv > 0.68 ? '#eab308' : '#22c55e';
  const gradId = `vu-g-${uid}`;

  return (
    <div style={{ textAlign: 'center' }}>
      <svg width="130" height="72" viewBox="0 0 130 72">
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stopColor="#22c55e"/>
            <stop offset="65%"  stopColor="#eab308"/>
            <stop offset="100%" stopColor="#ef4444"/>
          </linearGradient>
        </defs>
        {/* Scale background */}
        <path d="M 10 68 A 55 55 0 0 1 120 68"
          fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="5" strokeLinecap="round"/>
        {/* Colored scale */}
        <path d="M 10 68 A 55 55 0 0 1 120 68"
          fill="none" stroke={`url(#${gradId})`} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={VU_ARC_LEN}
          strokeDashoffset={VU_ARC_LEN * (1 - lv)}
        />
        {/* Tick marks at −∞, −20, −10, −6, −3, 0, +3 */}
        {[0, 0.22, 0.45, 0.63, 0.77, 0.92, 1].map((t, i) => {
          const a  = Math.PI * (1 + t);
          const x1 = 65 + 52 * Math.cos(a);
          const y1 = 68 + 52 * Math.sin(a);
          const x2 = 65 + 57 * Math.cos(a);
          const y2 = 68 + 57 * Math.sin(a);
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(255,255,255,0.15)" strokeWidth="1"/>;
        })}
        {/* Pivot */}
        <circle cx="65" cy="68" r="4" fill="#1a1a1a" stroke="rgba(255,255,255,0.2)" strokeWidth="0.5"/>
        {/* Needle */}
        <line x1="65" y1="68" x2={nx} y2={ny}
          stroke="rgba(255,255,255,0.9)" strokeWidth="1.5" strokeLinecap="round"/>
        {/* Labels */}
        <text x="10"  y="67" fontSize="7" fill="rgba(255,255,255,0.2)" textAnchor="middle">−∞</text>
        <text x="65"  y="12" fontSize="7" fill="rgba(255,255,255,0.2)" textAnchor="middle">0</text>
        <text x="120" y="67" fontSize="7" fill="rgba(255,255,255,0.2)" textAnchor="middle">+3</text>
      </svg>
      <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', marginTop: -2 }}>
        {label}&nbsp;<span style={{ color: dbClr }}>{dbVal}</span>
      </div>
    </div>
  );
}

// ─── VU Container (isolated to prevent 60fps re-renders bubbling up) ──────────
function VUContainer({ playing, prefix, wrapStyle }: { playing: boolean; prefix: string; wrapStyle?: React.CSSProperties }) {
  const [vuL, setVuL]   = useState(0);
  const [vuR, setVuR]   = useState(0);
  const vuTarget        = useRef({ l: 0, r: 0 });
  const vuFrameRef      = useRef<number | null>(null);
  const vuJitterRef     = useRef<ReturnType<typeof setInterval> | null>(null);

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
      if (vuFrameRef.current)  cancelAnimationFrame(vuFrameRef.current);
      if (vuJitterRef.current) clearInterval(vuJitterRef.current);
    };
  }, [playing]);

  return (
    <div style={{ display: 'flex', gap: 4, ...wrapStyle }}>
      <VUMeter level={vuL} label="L" uid={`${prefix}-l`}/>
      <VUMeter level={vuR} label="R" uid={`${prefix}-r`}/>
    </div>
  );
}

// ─── DeviceList (top-level to avoid re-mount on parent re-render) ─────────────
function DeviceList({
  devices, device, setDevice, fetchDevices, compact = false,
}: {
  devices: Device[];
  device: string;
  setDevice: (v: string) => void;
  fetchDevices: () => void;
  compact?: boolean;
}) {
  return (
    <div style={{ padding: compact ? '8px 14px' : 0, background: compact ? '#111' : 'transparent', borderBottom: compact ? '0.5px solid rgba(255,255,255,0.06)' : 'none', marginTop: compact ? 0 : 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px' }}>OUTPUT DEVICE</span>
        <button onClick={fetchDevices} style={{ background: 'none', border: 'none', fontSize: 9, color: 'rgba(255,255,255,0.25)', cursor: 'pointer' }}>↻</button>
      </div>
      <select
        value={device}
        onChange={e => setDevice(e.target.value)}
        style={{
          width: '100%',
          background: '#1a1a1a',
          border: '0.5px solid rgba(255,255,255,0.1)',
          borderRadius: 6,
          padding: '10px 12px',
          color: 'rgba(255,255,255,0.9)',
          fontSize: 11,
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        {devices.map(d => (
          <option key={d.id} value={d.id} disabled={d.id === 'none'}>{d.name}</option>
        ))}
      </select>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function AudioController() {
  const [mounted, setMounted]       = useState(false);
  const [mode, setMode]             = useState<'pure' | 'dsp'>('pure');
  const [device, setDevice]         = useState('');
  const [devices, setDevices]       = useState<Device[]>([]);
  const [volume, setVolume]         = useState(-5);
  const [humNoise, setHumNoise]     = useState('none');
  const [musicType, setMusicType]   = useState('none');
  const [eqOutput, setEqOutput]     = useState('none');
  const [reverb, setReverb]         = useState('none');
  const [reverbInt, setReverbInt]   = useState(5);
  const [crossfeed, setCrossfeed]   = useState('none');
  const [crossInt, setCrossInt]     = useState(5);
  const [applying, setApplying]     = useState(false);
  const [engineOpen, setEngineOpen] = useState(false);
  const [wsStatus, setWsStatus]     = useState<'connecting' | 'ok' | 'error'>('connecting');
  const [nowPlaying, setNowPlaying] = useState<NowPlaying>({
    title: '', artist: '', album: '', file: '', song_id: '', state: 'stop', audio: '', elapsed: 0, duration: 0,
  });
  const [formatBadge, setFormatBadge] = useState('');
  const [displayElapsed, setDisplayElapsed] = useState(0);

  // Presets
  const [presets, setPresets]       = useState<Record<string, DspConfig>>({});
  const [presetName, setPresetName] = useState('');
  const [presetOpen, setPresetOpen] = useState(false);

  const isBt       = device.includes('bluealsa');
  const btFallback = mode === 'pure' && isBt;
  const volBypass  = mode === 'pure' && !btFallback;

  useEffect(() => { setMounted(true); }, []);

  // ── WebSocket ────────────────────────────────────────────────────────────────
  const wsRef    = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setWsStatus('connecting');
    const ws = new WebSocket(WS_URL);
    ws.onopen    = () => { setWsStatus('ok'); if (retryRef.current) clearTimeout(retryRef.current); };
    ws.onclose   = () => { setWsStatus('error'); retryRef.current = setTimeout(connectWS, 3000); };
    ws.onerror   = () => ws.close();
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

  // ── Progress timer (increments elapsed locally each second when playing) ────
  useEffect(() => {
    if (nowPlaying.state !== 'play') return;
    const id = setInterval(() => {
      setDisplayElapsed(p => p + 1);
    }, 1000);
    return () => clearInterval(id);
  }, [nowPlaying.state, nowPlaying.song_id]);

  // ── Device list ──────────────────────────────────────────────────────────────
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

  // ── Presets ──────────────────────────────────────────────────────────────────
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
    setPresetOpen(false);
  };

  const deletePreset = async (name: string) => {
    try {
      const r = await fetch(`${API}/api/presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
      setPresets((await r.json()).presets);
    } catch {}
  };

  // ── Volume ───────────────────────────────────────────────────────────────────
  const handleVolume = async (v: number) => {
    setVolume(v);
    if (mode === 'dsp' && !isBt) {
      try {
        await fetch(`${API}/api/volume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ volume: v }),
        });
      } catch {}
    }
  };

  // ── Apply ────────────────────────────────────────────────────────────────────
  const applySettings = async () => {
    if (!device || device === 'none' || device === 'error') {
      alert('有効な出力デバイスを選択してください'); return;
    }
    setApplying(true);
    try {
      await fetch(`${API}/api/apply`, {
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
    } catch {
      /* swallow – retry is manual */
    } finally {
      setApplying(false);
    }
  };

  const artUrl = nowPlaying.song_id
    ? `${API}/api/art?file=${encodeURIComponent(nowPlaying.file)}&artist=${encodeURIComponent(nowPlaying.artist)}&album=${encodeURIComponent(nowPlaying.album)}&_ts=${nowPlaying.song_id}`
    : '';

  if (!mounted) return null;

  // ── Shared sub-elements ───────────────────────────────────────────────────────
  const WsDot = () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 6 }}>
      <div style={{
        width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
        background: wsStatus === 'ok' ? '#22c55e' : wsStatus === 'connecting' ? '#eab308' : '#ef4444',
        animation: wsStatus === 'connecting' ? 'pulse 1s infinite' : 'none',
      }}/>
      <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)' }}>
        {wsStatus === 'ok' ? 'MPD connected' : wsStatus === 'connecting' ? 'Connecting…' : 'Disconnected — retrying'}
      </span>
    </div>
  );

  const BtWarning = () => btFallback ? (
    <div style={{ padding: '8px 14px', background: 'rgba(234,179,8,0.08)', borderBottom: '0.5px solid rgba(234,179,8,0.2)' }}>
      <span style={{ fontSize: 11, color: 'rgba(234,179,8,0.85)' }}>
        ⚠️ Bluetooth はビットパーフェクト非対応のためエフェクト OFF の DSP で再生します
      </span>
    </div>
  ) : null;

  const HeroAlbumArt = ({ size }: { size: number }) => artUrl ? (
    <img src={artUrl} alt="album art" style={{ width: size, height: size, borderRadius: 14, objectFit: 'cover', border: '0.5px solid rgba(255,255,255,0.12)', flexShrink: 0 }}/>
  ) : (
    <div style={{ width: size, height: size, borderRadius: 14, background: 'linear-gradient(135deg,#1e3a5f,#2d6a8f,#0f2030)', border: '0.5px solid rgba(255,255,255,0.12)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontSize: size * 0.18, color: 'rgba(255,255,255,0.12)' }}>♪</span>
    </div>
  );

  const NpText = ({ titleSize = 18, artistSize = 12, center = true }) => (
    <div style={{ textAlign: center ? 'center' : 'left' }}>
      <div style={{ fontSize: titleSize, fontWeight: 500, color: 'rgba(255,255,255,0.95)', letterSpacing: -0.3, lineHeight: 1.3, marginBottom: 3 }}>
        {nowPlaying.title || 'Not Playing'}
      </div>
      <div style={{ fontSize: artistSize, color: 'rgba(255,255,255,0.45)', marginBottom: 8 }}>
        {nowPlaying.artist || 'Waiting for MPD…'}
      </div>
      {formatBadge && (
        <div style={{ display: center ? 'flex' : 'inline-flex', justifyContent: center ? 'center' : 'flex-start', marginBottom: 10 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', background: 'rgba(59,130,246,0.12)', border: '0.5px solid rgba(59,130,246,0.25)', borderRadius: 5, padding: '3px 8px' }}>
            <span style={{ fontSize: 10, color: 'rgba(59,130,246,0.9)', letterSpacing: '0.5px', fontWeight: 500 }}>
              {formatBadge}
            </span>
          </div>
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', minWidth: 30, textAlign: 'right' }}>{fmtTime(displayElapsed)}</span>
        <div style={{ flex: 1, height: 2, background: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
          <div style={{ height: '100%', width: `${nowPlaying.duration ? Math.min(100, (displayElapsed / nowPlaying.duration) * 100) : 0}%`, background: 'rgba(255,255,255,0.55)', borderRadius: 1, transition: 'width 1s linear' }}/>
        </div>
        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', minWidth: 30 }}>{nowPlaying.duration ? fmtTime(nowPlaying.duration) : '--:--'}</span>
      </div>
    </div>
  );

  const ModeToggle = ({ size = 'normal' }: { size?: 'normal' | 'compact' }) => (
    <div style={{ display: 'flex', gap: size === 'compact' ? 5 : 6, padding: size === 'compact' ? 0 : '10px 14px', background: size === 'compact' ? 'transparent' : '#111', borderBottom: size === 'compact' ? 'none' : '0.5px solid rgba(255,255,255,0.06)' }}>
      {(['pure', 'dsp'] as const).map(m => (
        <button key={m} onClick={() => setMode(m)} style={{
          flex: size === 'compact' ? 'none' : 1,
          width: size === 'compact' ? 72 : undefined,
          padding: size === 'compact' ? '8px 0' : '8px 0',
          borderRadius: 7,
          border: m === 'dsp' && mode !== 'dsp' ? '0.5px solid rgba(59,130,246,0.3)' : 'none',
          fontSize: 11, fontWeight: 500, letterSpacing: '0.8px', cursor: 'pointer',
          background:
            m === 'pure' && mode === 'pure' ? 'rgba(255,255,255,0.93)' :
            m === 'dsp'  && mode === 'dsp'  ? 'rgba(59,130,246,0.85)' :
            'transparent',
          color:
            m === 'pure' && mode === 'pure' ? '#111' :
            m === 'dsp'  && mode === 'dsp'  ? '#fff' :
            m === 'dsp' ? 'rgba(59,130,246,0.7)' : 'rgba(255,255,255,0.4)',
        }}>
          {m.toUpperCase()}
        </button>
      ))}
    </div>
  );

  const VolumeSlider = ({ desktop = false }: { desktop?: boolean }) => (
    <div style={{ padding: desktop ? 0 : '10px 14px', background: desktop ? 'transparent' : '#111', borderBottom: desktop ? 'none' : '0.5px solid rgba(255,255,255,0.06)', marginTop: desktop ? 14 : 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px' }}>VOLUME</span>
        <span style={{ fontSize: 10, color: volBypass ? 'rgba(255,255,255,0.2)' : '#22c55e' }}>
          {volBypass ? 'BYPASS' : `${volume} dB`}
        </span>
      </div>
      <input
        type="range" min="-60" max="0" step="1" value={volume}
        onChange={e => handleVolume(Number(e.target.value))}
        disabled={volBypass}
        style={{ width: '100%', accentColor: '#22c55e', opacity: volBypass ? 0.25 : 1, cursor: volBypass ? 'default' : 'pointer' }}
      />
      {desktop && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
          {['−60', '−30', '0 dB'].map(l => (
            <span key={l} style={{ fontSize: 8, color: 'rgba(255,255,255,0.18)' }}>{l}</span>
          ))}
        </div>
      )}
    </div>
  );

  const DialGrid = () => (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
      <DialControl label="HUM FILTER" color="#ef4444" options={HUM_OPTS} labels={HUM_LBL} value={humNoise} onChange={setHumNoise}/>
      <DialControl label="SOURCE EQ"  color="#3b82f6" options={EQ_OPTS}  labels={EQ_LBL}  value={musicType} onChange={setMusicType}/>
      <div style={{ gridColumn: 'span 2' }}>
        <DialControl label="OUTPUT EQ" color="#10b981" options={OUT_OPTS} labels={OUT_LBL} value={eqOutput} onChange={setEqOutput}/>
      </div>
      <div style={{ gridColumn: 'span 2' }}>
        <DialControl
          label="AMBIENCE" color="#eab308"
          options={REV_OPTS} labels={REV_LBL}
          value={reverb} onChange={setReverb}
          showBar barValue={reverbInt} onBarChange={setReverbInt}
        />
      </div>
      <div style={{ gridColumn: 'span 2' }}>
        <DialControl
          label="CROSSFEED" color="#a855f7"
          options={XF_OPTS} labels={XF_LBL}
          value={crossfeed} onChange={setCrossfeed}
          showBar barValue={crossInt} onBarChange={setCrossInt}
        />
      </div>
    </div>
  );

  const PresetPanel = () => (
    <div style={{ background: '#141414', border: '0.5px solid rgba(255,255,255,0.07)', borderRadius: 8, padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px' }}>🎛 PRESETS</span>
        <button onClick={() => setPresetOpen(o => !o)} style={{ background: 'none', border: 'none', fontSize: 9, color: 'rgba(255,255,255,0.35)', cursor: 'pointer' }}>
          {presetOpen ? '▲ 閉じる' : '▼ 開く'}
        </button>
      </div>
      {presetOpen && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {Object.keys(presets).length === 0 && (
            <p style={{ fontSize: 10, color: 'rgba(255,255,255,0.25)', margin: 0 }}>保存済みプリセットなし</p>
          )}
          {Object.keys(presets).map(name => (
            <div key={name} style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
              <button onClick={() => loadPreset(name)} style={{ flex: 1, textAlign: 'left', background: '#1a1a1a', border: '0.5px solid rgba(255,255,255,0.08)', borderRadius: 5, padding: '5px 8px', fontSize: 10, color: 'rgba(255,255,255,0.65)', cursor: 'pointer' }}>
                {name}
              </button>
              <button onClick={() => deletePreset(name)} style={{ background: 'none', border: 'none', padding: '0 4px', fontSize: 10, color: 'rgba(239,68,68,0.55)', cursor: 'pointer' }}>✕</button>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 5, marginTop: 2 }}>
            <input
              type="text" value={presetName}
              onChange={e => setPresetName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && savePreset()}
              placeholder="プリセット名…"
              style={{ flex: 1, background: '#0d0d0d', border: '0.5px solid rgba(255,255,255,0.1)', borderRadius: 5, padding: '5px 8px', fontSize: 10, color: 'rgba(255,255,255,0.7)', outline: 'none' }}
            />
            <button onClick={savePreset} style={{ background: 'rgba(34,197,94,0.15)', border: '0.5px solid rgba(34,197,94,0.3)', borderRadius: 5, padding: '5px 10px', fontSize: 10, color: '#22c55e', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              保存
            </button>
          </div>
        </div>
      )}
    </div>
  );

  const ApplyButton = ({ full = false, large = false }: { full?: boolean; large?: boolean }) => (
    <button
      onClick={applySettings}
      disabled={applying}
      style={{
        width: full ? '100%' : undefined,
        padding: large ? '13px 20px' : '11px 16px',
        background: applying ? 'rgba(34,197,94,0.45)' : '#22c55e',
        color: '#000',
        border: 'none',
        borderRadius: 8,
        fontSize: large ? 14 : 12,
        fontWeight: 500,
        letterSpacing: '0.5px',
        cursor: applying ? 'default' : 'pointer',
        transition: 'background 0.15s',
      }}
    >
      {applying ? 'Applying…' : 'APPLY SETTINGS'}
    </button>
  );

  // ────────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0a', color: '#fff', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        input[type=range] { height:4px; }
      `}</style>

      {/* ═══════════════════════ MOBILE (< 768px) ═══════════════════════════ */}
      <div className="md:hidden" style={{ paddingBottom: 80 }}>

        {/* Hero */}
        <div style={{ position: 'relative', background: '#0a0a0a', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 65%,#1a2f4a 0%,#0a0a0a 72%)', pointerEvents: 'none' }}/>
          <div style={{ position: 'relative', zIndex: 2, padding: '24px 20px 0', display: 'flex', justifyContent: 'center' }}>
            <HeroAlbumArt size={240}/>
          </div>
          <div style={{ position: 'relative', zIndex: 2, padding: '14px 20px 16px', textAlign: 'center' }}>
            <NpText titleSize={18} artistSize={12} center/>
            <WsDot/>
          </div>
        </div>

        <ModeToggle/>
        <BtWarning/>
        <VolumeSlider/>
        <DeviceList devices={devices} device={device} setDevice={setDevice} fetchDevices={fetchDevices} compact/>

        {/* Sound engine accordion */}
        <button
          onClick={() => setEngineOpen(o => !o)}
          style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: '#111', borderBottom: '0.5px solid rgba(255,255,255,0.06)', border: 'none', cursor: 'pointer', color: 'white' }}
        >
          <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px' }}>SOUND ENGINE</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>
              {EQ_LBL[musicType]} · {REV_LBL[reverb]} · {XF_LBL[crossfeed]}
            </span>
            <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)' }}>{engineOpen ? '▲' : '▼'}</span>
          </div>
        </button>

        {(mode === 'dsp' || btFallback || engineOpen) && (
          <div style={{ background: '#0d0d0d', padding: 14 }}>
            {/* VU meters */}
            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px', marginBottom: 8 }}>SIGNAL LEVEL</div>
            <VUContainer playing={nowPlaying.state === 'play'} prefix="mob" wrapStyle={{ justifyContent: 'center', marginBottom: 14 }}/>

            <DialGrid/>
            <div style={{ marginTop: 10 }}><PresetPanel/></div>
          </div>
        )}
      </div>

      {/* Fixed APPLY footer — mobile */}
      <div
        className="md:hidden"
        style={{ position: 'fixed', bottom: 0, left: 0, right: 0, padding: '10px 14px', background: 'rgba(10,10,10,0.96)', borderTop: '0.5px solid rgba(255,255,255,0.08)', zIndex: 50 }}
      >
        <ApplyButton full large/>
      </div>

      {/* ═══════════════════════ DESKTOP (≥ 768px) ══════════════════════════ */}
      <div className="hidden md:block">

        {/* Hero */}
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 24, padding: 24, background: '#0a0a0a', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 25% 50%,#1a2f4a 0%,#0a0a0a 65%)', pointerEvents: 'none' }}/>
          <div style={{ position: 'relative', zIndex: 2 }}>
            <HeroAlbumArt size={190}/>
          </div>
          <div style={{ position: 'relative', zIndex: 2, flex: 1, minWidth: 0 }}>
            <NpText titleSize={22} artistSize={13} center={false}/>
            <WsDot/>
          </div>
          <div style={{ position: 'relative', zIndex: 2 }}>
            <ModeToggle size="compact"/>
          </div>
        </div>

        <BtWarning/>

        {/* Studio panel */}
        <div style={{ background: '#0d0d0d', padding: '18px 24px' }}>
          <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>

            {/* LEFT: VU + Volume + Device */}
            <div style={{ width: 238, flexShrink: 0 }}>
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px', marginBottom: 8 }}>SIGNAL LEVEL</div>
              <VUContainer playing={nowPlaying.state === 'play'} prefix="dsk"/>
              <VolumeSlider desktop/>
              <DeviceList devices={devices} device={device} setDevice={setDevice} fetchDevices={fetchDevices}/>
            </div>

            {/* CENTER: Sound engine dials */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px', marginBottom: 8 }}>SOUND ENGINE</div>
              <DialGrid/>
            </div>

            {/* RIGHT: Presets + Apply */}
            <div style={{ width: 160, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.28)', letterSpacing: '1.2px', marginBottom: -2 }}>CONTROLS</div>
              <PresetPanel/>
              <ApplyButton full/>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
