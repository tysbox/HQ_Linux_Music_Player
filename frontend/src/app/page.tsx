'use client';
import { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';

const API = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000';

const WS_URL = typeof window !== 'undefined'
  ? `ws://${window.location.hostname}:8000/ws/now_playing`
  : 'ws://localhost:8000/ws/now_playing';

interface DspConfig {
  volume: number;
  music_type: string;
  eq_output: string;
  crossfeed: string;
  hum_noise: string;
  reverb: string;
  reverb_intensity: number;
}

export default function AudioController() {
  const [mounted, setMounted]           = useState(false);
  const [mode, setMode]                 = useState<'pure' | 'dsp'>('pure');
  const [device, setDevice]             = useState('');
  const [devicesList, setDevicesList]   = useState<{id:string; name:string}[]>([]);
  const [volume, setVolume]             = useState(-5);
  const [musicType, setMusicType]       = useState('none');
  const [eqOutput, setEqOutput]         = useState('none');
  const [crossfeed, setCrossfeed]       = useState('none');
  const [humNoise, setHumNoise]         = useState('none');
  const [reverb, setReverb]             = useState('none');
  const [reverbIntensity, setReverbIntensity] = useState(5);
  const [nowPlaying, setNowPlaying]     = useState({
    title: '', artist: '', album: '', file: '', song_id: '', state: 'stop',
  });
  const [applying, setApplying]         = useState(false);
  const [lastResult, setLastResult]     = useState<{bt_fallback?: boolean} | null>(null);
  const [wsStatus, setWsStatus]         = useState<'connecting'|'ok'|'error'>('connecting');

  // プリセット
  const [presets, setPresets]           = useState<Record<string, DspConfig>>({});
  const [presetName, setPresetName]     = useState('');
  const [presetOpen, setPresetOpen]     = useState(false);

  const isBtDevice     = device.includes('bluealsa');
  const btPureFallback = mode === 'pure' && isBtDevice;

  useEffect(() => { setMounted(true); }, []);

  // ── WebSocket — Now Playing ──────────────────────────────────────────────
  const wsRef       = useRef<WebSocket | null>(null);
  const retryRef    = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setWsStatus('connecting');
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setWsStatus('ok');
      if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }
    };
    ws.onclose = () => {
      setWsStatus('error');
      retryRef.current = setTimeout(connectWS, 3000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (!data.error) setNowPlaying(data);
      } catch {}
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

  // ── デバイス一覧 ─────────────────────────────────────────────────────────
  const fetchDevices = async () => {
    try {
      const res  = await fetch(`${API}/api/devices`);
      const data = await res.json();
      setDevicesList(data);
      if (!device && data.length > 0) {
        const usb = data.find((d: {id:string}) =>
          d.id.includes('plughw') && !d.id.includes('1,0'));
        setDevice(usb ? usb.id : data[0].id);
      }
    } catch {}
  };
  useEffect(() => { fetchDevices(); }, []);

  // ── プリセット ────────────────────────────────────────────────────────────
  const fetchPresets = async () => {
    try {
      const res  = await fetch(`${API}/api/presets`);
      setPresets(await res.json());
    } catch {}
  };
  useEffect(() => { fetchPresets(); }, []);

  const savePreset = async () => {
    if (!presetName.trim()) { alert('プリセット名を入力してください'); return; }
    const config: DspConfig = {
      volume, music_type: musicType, eq_output: eqOutput,
      crossfeed, hum_noise: humNoise, reverb, reverb_intensity: reverbIntensity,
    };
    const res  = await fetch(`${API}/api/presets/save`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: presetName.trim(), config }),
    });
    const data = await res.json();
    if (data.status === 'success') { setPresets(data.presets); setPresetName(''); }
  };

  const loadPreset = (name: string) => {
    const p = presets[name];
    if (!p) return;
    setVolume(p.volume);       setMusicType(p.music_type);
    setEqOutput(p.eq_output);  setCrossfeed(p.crossfeed);
    setHumNoise(p.hum_noise);  setReverb(p.reverb);
    setReverbIntensity(p.reverb_intensity);
    setPresetOpen(false);
  };

  const deletePreset = async (name: string) => {
    const res  = await fetch(`${API}/api/presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const data = await res.json();
    setPresets(data.presets);
  };

  // ── ボリューム ────────────────────────────────────────────────────────────
  const handleVolumeChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value);
    setVolume(v);
    if (mode === 'dsp' && !isBtDevice) {
      try {
        await fetch(`${API}/api/volume`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ volume: v }),
        });
      } catch {}
    }
  };

  // ── 設定適用 ──────────────────────────────────────────────────────────────
  const applySettings = async () => {
    if (device === 'none' || device === 'error') {
      alert('有効な出力デバイスを選択してください'); return;
    }
    setApplying(true); setLastResult(null);
    try {
      const res = await fetch(`${API}/api/apply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode, device, volume,
          music_type: musicType, eq_output: eqOutput,
          crossfeed, hum_noise: humNoise, reverb, reverb_intensity: reverbIntensity,
        }),
      });
      setLastResult(await res.json());
    } catch {
      setLastResult(null);
    } finally { setApplying(false); }
  };

  const artUrl = nowPlaying.song_id
    ? `${API}/api/art?file=${encodeURIComponent(nowPlaying.file)}&artist=${encodeURIComponent(nowPlaying.artist)}&album=${encodeURIComponent(nowPlaying.album)}&_ts=${nowPlaying.song_id}`
    : '';

  if (!mounted) return null;
  const presetNames = Object.keys(presets);

  return (
    <div className="min-h-screen bg-black text-white p-6 font-sans selection:bg-green-500">
      <div className="max-w-7xl mx-auto">
        <div className="w-full md:w-[450px] flex-shrink-0 space-y-6">

          {/* WS ステータス */}
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <span className={`w-2 h-2 rounded-full ${
              wsStatus === 'ok'         ? 'bg-green-500' :
              wsStatus === 'connecting' ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'
            }`}/>
            {wsStatus === 'ok'         ? 'MPD Connected' :
             wsStatus === 'connecting' ? 'Connecting…'   : 'MPD Disconnected — retrying'}
          </div>

          {/* モード選択 */}
          <div className="bg-gray-900 p-2 rounded-2xl flex space-x-2 shadow-lg">
            <button onClick={() => setMode('pure')}
              className={`flex-1 py-3 rounded-xl font-bold transition-all ${
                mode === 'pure' ? 'bg-white text-black shadow-md' : 'text-gray-400 hover:text-white'
              }`}>PURE</button>
            <button onClick={() => setMode('dsp')}
              className={`flex-1 py-3 rounded-xl font-bold transition-all ${
                mode === 'dsp' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-400 hover:text-white'
              }`}>DSP</button>
          </div>

          {btPureFallback && (
            <div className="bg-yellow-900/50 border border-yellow-600 rounded-xl px-4 py-3 text-yellow-300 text-sm">
              ⚠️ Bluetooth はビットパーフェクト非対応のため、エフェクト OFF の DSP モードで再生します。
            </div>
          )}
          {lastResult?.bt_fallback && (
            <div className="bg-blue-900/40 border border-blue-500 rounded-xl px-4 py-2 text-blue-300 text-xs">
              ✅ BT パススルーモードで起動しました
            </div>
          )}

          {/* ボリューム */}
          <div className="bg-gray-900 p-5 rounded-2xl shadow-lg">
            <label className="text-gray-400 text-xs uppercase flex justify-between mb-3 font-bold tracking-widest">
              <span>Volume</span>
              <span className={mode === 'pure' && !btPureFallback ? 'text-gray-600' : 'text-green-400'}>
                {mode === 'pure' && !btPureFallback ? 'Bypass (MPD Direct)' : `${volume} dB`}
              </span>
            </label>
            <input type="range" min="-60" max="0" value={volume}
              onChange={handleVolumeChange}
              disabled={mode === 'pure' && !btPureFallback}
              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-green-500 disabled:opacity-30"
            />
          </div>

          {/* 出力デバイス */}
          <div className="bg-gray-900 p-5 rounded-2xl shadow-lg">
            <div className="flex justify-between mb-3 items-center">
              <label className="text-gray-400 text-xs uppercase font-bold tracking-widest">Output Device</label>
              <button onClick={fetchDevices} className="text-gray-500 text-xs hover:text-white transition-colors">🔄 Refresh</button>
            </div>
            <select value={device} onChange={(e) => setDevice(e.target.value)}
              className="w-full bg-gray-800 text-white p-3 rounded-xl outline-none border border-gray-700 focus:border-green-500 cursor-pointer">
              {devicesList.map((d) => (
                <option key={d.id} value={d.id} disabled={d.id === 'none' || d.id === 'error'}>
                  {d.name}{d.id.includes('bluealsa') && mode === 'pure' ? ' ⚠️ DSP FB' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* DSP コントロール */}
          {(mode === 'dsp' && !btPureFallback) && (
            <div className="bg-gray-900 p-5 rounded-2xl shadow-lg space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-300">

              {/* プリセット */}
              <div className="bg-gray-800/70 p-4 rounded-xl border border-gray-600">
                <div className="flex justify-between items-center mb-2">
                  <label className="text-gray-300 text-xs uppercase font-bold tracking-widest">🎛 DSP Presets</label>
                  <button onClick={() => setPresetOpen(o => !o)}
                    className="text-gray-500 text-xs hover:text-white transition-colors">
                    {presetOpen ? '▲ 閉じる' : '▼ 開く'}
                  </button>
                </div>
                {presetOpen && (
                  <div className="space-y-3 mt-3">
                    {presetNames.length > 0 && (
                      <div className="space-y-1">
                        {presetNames.map(name => (
                          <div key={name} className="flex items-center gap-2">
                            <button onClick={() => loadPreset(name)}
                              className="flex-1 text-left bg-gray-700 hover:bg-gray-600 text-white text-sm px-3 py-2 rounded-lg transition-colors truncate">
                              {name}
                            </button>
                            <button onClick={() => deletePreset(name)}
                              className="text-red-500 hover:text-red-400 text-xs px-2 py-2">✕</button>
                          </div>
                        ))}
                      </div>
                    )}
                    {presetNames.length === 0 && (
                      <p className="text-gray-600 text-xs">保存済みプリセットはありません</p>
                    )}
                    <div className="flex gap-2">
                      <input type="text" value={presetName}
                        onChange={e => setPresetName(e.target.value)}
                        placeholder="プリセット名..."
                        className="flex-1 bg-gray-900 text-white text-sm px-3 py-2 rounded-lg border border-gray-600 focus:border-green-500 outline-none"
                      />
                      <button onClick={savePreset}
                        className="bg-green-700 hover:bg-green-600 text-white text-xs px-3 py-2 rounded-lg transition-colors whitespace-nowrap">
                        保存
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* ハムノイズ除去 */}
              <div className="bg-gray-800/50 p-4 rounded-xl border border-gray-700">
                <label className="text-gray-300 text-xs uppercase font-bold tracking-widest block mb-2">⚡ Smart Clean</label>
                <select value={humNoise} onChange={(e) => setHumNoise(e.target.value)}
                  className="w-full bg-gray-900 p-3 rounded-lg outline-none text-sm text-gray-300">
                  <option value="none">Off</option>
                  <option value="50hz">On — 50 Hz</option>
                  <option value="60hz">On — 60 Hz</option>
                </select>
              </div>

              {/* IR リバーブ */}
              <div className="bg-gray-800/50 p-4 rounded-xl border border-gray-700">
                <label className="text-gray-300 text-xs uppercase font-bold tracking-widest block mb-2">🎻 Ambience (IR Reverb)</label>
                <select value={reverb} onChange={(e) => setReverb(e.target.value)}
                  className="w-full bg-gray-900 p-3 rounded-lg outline-none text-sm text-gray-300">
                  <option value="none">Dry</option>
                  <option value="hall">Symphony Hall</option>
                  <option value="jazz_club">Jazz Club</option>
                </select>
                {reverb !== 'none' && (
                  <div className="mt-3">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Subtle</span><span className="text-green-400">{reverbIntensity}%</span><span>Strong</span>
                    </div>
                    <input type="range" min="1" max="10" value={reverbIntensity}
                      onChange={(e) => setReverbIntensity(Number(e.target.value))}
                      className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                    />
                  </div>
                )}
              </div>

              {/* Music EQ / Device EQ */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-gray-400 text-[10px] uppercase font-bold tracking-widest block mb-2">Music EQ</label>
                  <select value={musicType} onChange={(e) => setMusicType(e.target.value)}
                    className="w-full bg-gray-800 p-3 rounded-lg outline-none text-sm text-gray-300">
                    <option value="none">Flat</option>
                    <option value="jazz">Lively Jazz</option>
                    <option value="classical">Orchestral</option>
                    <option value="electronic">Punchy Electronic</option>
                    <option value="vocal">Vocal Presence</option>
                  </select>
                </div>
                <div>
                  <label className="text-gray-400 text-[10px] uppercase font-bold tracking-widest block mb-2">Device EQ</label>
                  <select value={eqOutput} onChange={(e) => setEqOutput(e.target.value)}
                    className="w-full bg-gray-800 p-3 rounded-lg outline-none text-sm text-gray-300">
                    <option value="none">Flat</option>
                    <option value="studio-monitors">Studio Monitors</option>
                    <option value="JBL-Speakers">JBL Signature</option>
                    <option value="planar-magnetic">Planar Magnetic</option>
                    <option value="bt-earphones">BT Earphones</option>
                    <option value="loud-speaker">Loud Speaker (JBL + Crystal)</option>
                    <option value="Tube-Warmth">Tube Warmth</option>
                    <option value="Crystal-Clarity">Crystal Clarity</option>
                  </select>
                </div>
              </div>

              {/* クロスフィード */}
              <div>
                <label className="text-sm text-gray-400 font-medium block mb-1">Headphone Crossfeed</label>
                <select value={crossfeed} onChange={(e) => setCrossfeed(e.target.value)}
                  className="w-full bg-gray-800 text-white rounded-lg p-2.5 border border-gray-700 focus:outline-none focus:border-green-500 transition-colors cursor-pointer">
                  <option value="none">Off</option>
                  <option value="light">Light (Subtle)</option>
                  <option value="standard">Standard</option>
                </select>
              </div>
            </div>
          )}

          {/* APPLY ボタン */}
          <button onClick={applySettings} disabled={applying}
            className="w-full bg-green-500 text-black py-4 rounded-2xl font-bold text-lg hover:bg-green-400 transition-colors shadow-[0_0_20px_rgba(34,197,94,0.3)] mt-4 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed">
            {applying ? 'Applying…' : 'APPLY SETTINGS'}
          </button>
        </div>

        {/* フローティングアルバムアート */}
        <div className="hidden md:block">
          <motion.div drag dragMomentum={false} initial={{ x: 500, y: 0 }}
            className="fixed top-10 z-50 flex flex-col shadow-2xl rounded-3xl w-[35vw] max-w-[500px] min-w-[300px]"
            style={{ cursor: 'grab' }} whileDrag={{ cursor: 'grabbing' }}>
            <div className="drag-handle w-full bg-gray-800 text-gray-400 text-center py-3 rounded-t-3xl font-bold uppercase text-xs tracking-widest border border-gray-700 hover:bg-gray-700 hover:text-white transition-colors">
              ::: DRAG POSITION :::
            </div>
            <div className="bg-gray-900/80 backdrop-blur-xl rounded-b-3xl p-8 flex flex-col items-center shadow-[0_30px_60px_rgba(0,0,0,0.9)] relative border border-gray-700/50 border-t-0">
              <div className="w-full aspect-square bg-gray-800 rounded-2xl overflow-hidden shadow-2xl mb-8 z-10 pointer-events-none">
                {artUrl
                  ? <img src={artUrl} alt="Art" className="w-full h-full object-cover select-none pointer-events-none" />
                  : <span className="text-gray-600 flex h-full items-center justify-center text-xl">No Signal</span>
                }
              </div>
              <h2 className="text-4xl font-extrabold text-center w-full z-10 tracking-tight leading-tight line-clamp-2">
                {nowPlaying.title || 'Not Playing'}
              </h2>
              <p className="text-blue-400 text-xl text-center w-full z-10 mt-2 font-medium">
                {nowPlaying.artist || 'Waiting for MPD…'}
              </p>
              <p className="text-gray-600 text-xs mt-3 uppercase tracking-widest">
                {nowPlaying.state === 'play' ? '▶ Playing' :
                 nowPlaying.state === 'pause' ? '⏸ Paused' : '■ Stopped'}
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
