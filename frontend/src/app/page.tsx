'use client';
import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

export default function AudioController() {
  const [mounted, setMounted] = useState(false);
  const nodeRef = useRef(null);
  const [mode, setMode] = useState('pure');
  const [device, setDevice] = useState('plug:bluealsa');
  const [devicesList, setDevicesList] = useState([{ id: 'plug:bluealsa', name: 'Loading...' }]);
  const [volume, setVolume] = useState(-5);
  const [musicType, setMusicType] = useState('none');
  const [eqOutput, setEqOutput] = useState('none');
  const [crossfeed, setCrossfeed] = useState('none');
  const [humNoise, setHumNoise] = useState('none');
  const [reverb, setReverb] = useState('none');
  const [reverbIntensity, setReverbIntensity] = useState(5);
  const [nowPlaying, setNowPlaying] = useState({ title: '', artist: '', album: '', file: '', song_id: '' });

  useEffect(() => {
    setMounted(true);
    const fetchNowPlaying = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/now_playing');
        const data = await res.json();
        if (data.song_id && data.song_id !== nowPlaying.song_id) setNowPlaying(data);
      } catch (err) {}
    };
    fetchNowPlaying();
    const interval = setInterval(fetchNowPlaying, 2000);
    return () => clearInterval(interval);
  }, [nowPlaying.song_id]);

  const fetchDevices = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/devices');
      const data = await res.json();
      setDevicesList(data);
      // Removed forced auto-select that grabs PC Speakers aggressively
      const connectedDac = data.find((d: any) => d.id.includes('plug:hw:'));
      if (connectedDac) setDevice(connectedDac.id);
    } catch (err) {}
  };
  useEffect(() => { fetchDevices(); }, []);

  const handleVolumeChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const newVol = Number(e.target.value);
    setVolume(newVol);
    if (mode === 'dsp') {
      await fetch('http://localhost:8000/api/volume', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ volume: newVol }) });
    }
  };

  const applySettings = async () => {
    if (device === 'none') { alert('USB-DAC Not Connected'); return; }
    await fetch('http://localhost:8000/api/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode, device, volume, music_type: musicType, eq_output: eqOutput, crossfeed, hum_noise: humNoise, reverb, reverb_intensity: reverbIntensity }) });
    alert('Settings Applied & Engine Restarted.');
  };

  const artUrl = nowPlaying.song_id ? `http://localhost:8000/api/art?file=${encodeURIComponent(nowPlaying.file)}&artist=${encodeURIComponent(nowPlaying.artist)}&album=${encodeURIComponent(nowPlaying.album)}&_ts=${nowPlaying.song_id}` : '';


  if (!mounted) return null;
  return (
    <div className="min-h-screen bg-black text-white p-6 font-sans selection:bg-green-500">
      <div className="max-w-7xl mx-auto">
        
        {/* Left Side: Controls */}
        <div className="w-full md:w-[450px] flex-shrink-0 space-y-6">
        
        <div className="bg-gray-900 p-2 rounded-2xl flex space-x-2 shadow-lg">
          <button onClick={() => setMode('pure')} className={`flex-1 py-3 rounded-xl font-bold transition-all ${mode === 'pure' ? 'bg-white text-black shadow-md' : 'text-gray-400 hover:text-white'}`}>PURE</button>
          <button onClick={() => setMode('dsp')} className={`flex-1 py-3 rounded-xl font-bold transition-all ${mode === 'dsp' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-400 hover:text-white'}`}>DSP</button>
        </div>

        <div className="bg-gray-900 p-5 rounded-2xl shadow-lg">
          <label className="text-gray-400 text-xs uppercase flex justify-between mb-3 font-bold tracking-widest">
            <span>Volume</span><span className={mode === 'pure' ? 'text-gray-600' : 'text-green-400'}>{mode === 'pure' ? 'Bypass' : `${volume} dB`}</span>
          </label>
          <input type="range" min="-60" max="0" value={volume} onChange={handleVolumeChange} disabled={mode === 'pure' ? true : undefined} className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-green-500 disabled:opacity-30" />
        </div>

        <div className="bg-gray-900 p-5 rounded-2xl shadow-lg">
          <div className="flex justify-between mb-3 items-center">
            <label className="text-gray-400 text-xs uppercase font-bold tracking-widest">Output Device</label>
            <button onClick={fetchDevices} className="text-gray-500 text-xs hover:text-white transition-colors">🔄 Refresh</button>
          </div>
          <select value={device} onChange={(e) => setDevice(e.target.value)} className="w-full bg-gray-800 text-white p-3 rounded-xl outline-none border border-gray-700 focus:border-green-500 cursor-pointer">
            {devicesList.map((d) => <option key={d.id} value={d.id} disabled={d.id === 'none' ? true : undefined}>{d.name}</option>)}
          </select>
        </div>

        {mode === 'dsp' && (
          <div className="bg-gray-900 p-5 rounded-2xl shadow-lg space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-300">
            <div className="bg-gray-800/50 p-4 rounded-xl border border-gray-700">
              <label className="text-gray-300 text-xs uppercase font-bold tracking-widest block mb-2">⚡ Smart Clean</label>
              <select value={humNoise} onChange={(e) => setHumNoise(e.target.value)} className="w-full bg-gray-900 p-3 rounded-lg outline-none text-sm text-gray-300">
                <option value="none">Off</option><option value="50hz">On - 50Hz</option><option value="60hz">On - 60Hz</option>
              </select>
            </div>
            <div className="bg-gray-800/50 p-4 rounded-xl border border-gray-700">
              <label className="text-gray-300 text-xs uppercase font-bold tracking-widest block mb-2">🎻 Ambience (IR Reverb)</label>
              <select value={reverb} onChange={(e) => setReverb(e.target.value)} className="w-full bg-gray-900 p-3 rounded-lg outline-none text-sm text-gray-300">
                <option value="none">Dry</option><option value="hall">Symphony Hall</option><option value="jazz_club">Jazz Club</option>
              </select>
              {reverb !== 'none' && (
                <div className="mt-3">
                  <div className="flex justify-between text-xs text-gray-500 mb-1"><span>Subtle</span><span className="text-green-400">{reverbIntensity}%</span><span>Strong</span></div>
                  <input type="range" min="1" max="10" value={reverbIntensity} onChange={(e) => setReverbIntensity(Number(e.target.value))} className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-gray-400 text-[10px] uppercase font-bold tracking-widest block mb-2">Music EQ</label>
                <select value={musicType} onChange={(e) => setMusicType(e.target.value)} className="w-full bg-gray-800 p-3 rounded-lg outline-none text-sm text-gray-300">
                  <option value="none">Flat</option>
                  <option value="jazz">Lively Jazz</option>
                  <option value="classical">Orchestral</option>
                  <option value="electronic">Punchy Electronic</option>
                  <option value="vocal">Vocal Presence</option>
                </select>
              </div>
              <div>
                <label className="text-gray-400 text-[10px] uppercase font-bold tracking-widest block mb-2">Device EQ</label>
                <select value={eqOutput} onChange={(e) => setEqOutput(e.target.value)} className="w-full bg-gray-800 p-3 rounded-lg outline-none text-sm text-gray-300">
                  <option value="none">Flat</option>
                  <option value="studio-monitors">Studio Monitors</option>
                  <option value="JBL-Speakers">JBL Signature</option>
                  <option value="planar-magnetic">Planar Magnetic</option>
                  <option value="bt-earphones">BT Earphones</option>
                  <option value="Tube-Warmth">Tube Warmth</option>
                  <option value="Crystal-Clarity">Crystal Clarity</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-sm text-gray-400 font-medium block mb-1">Headphone Crossfeed</label>
              <div className="relative">
                <select value={crossfeed} onChange={(e) => setCrossfeed(e.target.value)} className="w-full bg-gray-800 text-white rounded-lg p-2.5 border border-gray-700 focus:outline-none focus:border-green-500 transition-colors cursor-pointer">
                  <option value="none">Off</option><option value="light">Light (Subtle)</option><option value="standard">Standard</option>
                </select>
              </div>
            </div>
          </div>
        )}
        <button onClick={applySettings} className="w-full bg-green-500 text-black py-4 rounded-2xl font-bold text-lg hover:bg-green-400 transition-colors shadow-[0_0_20px_rgba(34,197,94,0.3)] mt-4 active:scale-95">APPLY SETTINGS</button>
      </div>

        </div> {/* End Left Side */}
        

      {/* Floating Draggable Album Art for Landscape / Tablet */}
      <div className="hidden md:block">
        <motion.div 
            drag
            dragMomentum={false}
            initial={{ x: 500, y: 0 }}
            className="fixed top-10 z-50 flex flex-col shadow-2xl rounded-3xl w-[35vw] max-w-[500px] min-w-[300px]"
            style={{ cursor: "grab" }}
            whileDrag={{ cursor: "grabbing" }}
        >
          <div className="drag-handle w-full bg-gray-800 text-gray-400 text-center py-3 rounded-t-3xl font-bold uppercase text-xs tracking-widest border border-gray-700 hover:bg-gray-700 hover:text-white transition-colors">
            ::: DRAG POSITION :::
          </div>
          <div className="bg-gray-900/80 backdrop-blur-xl rounded-b-3xl p-8 flex flex-col items-center shadow-[0_30px_60px_rgba(0,0,0,0.9)] relative border border-gray-700/50 border-t-0">
             <div className="w-full aspect-square bg-gray-800 rounded-2xl overflow-hidden shadow-2xl mb-8 z-10 pointer-events-none">
               {artUrl ? <img src={artUrl} alt="Art" className="w-full h-full object-cover select-none pointer-events-none" /> : <span className="text-gray-600 flex h-full items-center justify-center text-xl">No Signal</span>}
             </div>
             <h2 className="text-4xl font-extrabold text-center w-full z-10 tracking-tight leading-tight line-clamp-2">{nowPlaying.title || 'Not Playing'}</h2>
             <p className="text-blue-400 text-xl text-center w-full z-10 mt-2 font-medium">{nowPlaying.artist || 'Waiting for MPD...'}</p>
          </div>
        </motion.div>
      </div>
        
      </div>
    
  );
}
