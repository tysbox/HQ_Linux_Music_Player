'use client'
// ─────────────────────────────────────────────────────────────────────────────
// TotalCurveOverlay — Bisen AlbumArtFrame Total Mode + totalCurve.ts の移植.
// 全 DSP 段の合成イコライジングカーブをアルバムアート上に表示 (±3dB 過補正警告付き)。
// ─────────────────────────────────────────────────────────────────────────────
import React from 'react'
import { Activity } from 'lucide-react'

// ── EQ バンド定義 (backend/dsp/yaml_generator.py MUSIC_EQ / OUTPUT_EQ と同一) ──
const MUSIC_EQ_BANDS: Record<string, { freq: number; q: number; gain: number }[]> = {
  none: [],
  jazz: [
    { freq: 80, q: 0.9, gain: 2.5 }, { freq: 300, q: 1.0, gain: 1.0 },
    { freq: 7000, q: 0.8, gain: 0.7 },
  ],
  classical: [
    { freq: 60, q: 0.7, gain: 1.0 }, { freq: 400, q: 0.9, gain: -0.5 },
    { freq: 8000, q: 0.8, gain: 1.0 },
  ],
  electronic: [
    { freq: 50, q: 0.8, gain: 4.0 }, { freq: 400, q: 1.2, gain: -2.0 },
    { freq: 10000, q: 0.9, gain: 2.5 },
  ],
  vocal: [
    { freq: 150, q: 1.0, gain: -1.0 }, { freq: 1000, q: 0.8, gain: 3.0 },
    { freq: 3000, q: 0.9, gain: 2.0 },
  ],
}

const OUTPUT_EQ_BANDS: Record<string, { freq: number; q: number; gain: number }[]> = {
  none: [],
  'studio-monitors': [
    { freq: 80, q: 0.8, gain: 3.0 }, { freq: 2500, q: 1.0, gain: -0.8 },
    { freq: 20000, q: 1.0, gain: 3.0 },
  ],
  'JBL-Speakers': [
    { freq: 70, q: 0.7, gain: 3.0 }, { freq: 1200, q: 1.0, gain: -2.0 },
    { freq: 13000, q: 0.8, gain: 5.0 },
  ],
  'planar-magnetic': [
    { freq: 30, q: 0.7, gain: 1.0 }, { freq: 180, q: 0.9, gain: -1.0 },
    { freq: 15000, q: 0.8, gain: 1.0 },
  ],
  'loud-speaker': [
    { freq: 70, q: 0.7, gain: 4.0 }, { freq: 300, q: 1.0, gain: 1.0 },
    { freq: 8000, q: 0.7, gain: 4.0 }, { freq: 16000, q: 0.9, gain: 2.5 },
  ],
  'Tube-Warmth': [
    { freq: 200, q: 0.8, gain: 2.5 }, { freq: 4000, q: 1.0, gain: -1.5 },
    { freq: 10000, q: 0.8, gain: -2.0 },
  ],
  'Crystal-Clarity': [
    { freq: 100, q: 1.2, gain: -2.0 }, { freq: 8000, q: 0.7, gain: 4.0 },
    { freq: 16000, q: 0.9, gain: 2.5 },
  ],
}

// ── カーブ計算 (Bisen totalCurve.ts bandResponseAt 移植) ──────────────────
function bandResponseAt(freq: number, band: { freq: number; q: number; gain: number; type?: string }): number {
  const octDiff = Math.log2(freq / band.freq)
  const gain = band.gain
  const type = band.type || 'peaking'
  if (type === 'lowshelf') return gain / (1 + Math.exp(octDiff * 3))
  if (type === 'highshelf') return gain / (1 + Math.exp(-octDiff * 3))
  const bandwidth = 1.0 / (band.q || 1.0)
  return gain * Math.exp(-0.5 * Math.pow(octDiff / (bandwidth * 0.5), 2))
}

function eqBandsDbAt(freq: number, bands: { freq: number; q: number; gain: number }[]): number {
  return bands.reduce((sum, b) => sum + bandResponseAt(freq, b), 0)
}

function crossfeedDbAt(freq: number, crossfeed: string, intensity: number): number {
  if (crossfeed === 'none') return 0
  const lowGain = -3.0 * (intensity / 100.0)
  if (freq >= 200) return 0
  const t = (freq - 20) / (200 - 20)
  return lowGain * (1 - t)
}

function humFilterDbAt(freq: number, hum: string): number {
  if (hum === '50hz') {
    const octDiff = Math.log2(freq / 50)
    return -6 * Math.exp(-0.5 * Math.pow(octDiff / 0.1, 2))
  }
  if (hum === '60hz') {
    const octDiff = Math.log2(freq / 60)
    return -6 * Math.exp(-0.5 * Math.pow(octDiff / 0.1, 2))
  }
  return 0
}

export interface TotalCurvePoint { x: number; y: number; freq: number; db: number }

// ── グラフ座標系 (SVG viewBox 128x90 直描画 — 高解像度・細線仕様) ───────────
export const CURVE_VIEW = {
  MIN_FREQ: 20, MAX_FREQ: 20000,
  MIN_DB: -15, MAX_DB: 15,
  X0: 14, X1: 126,          // プロット領域 左→右 (周波数対数軸)
  Y0: 8, Y1: 76,            // プロット領域 上(+15dB)→下(-15dB)
  LABEL_Y: 85,              // 周波数軸ラベル行
} as const

export function freqToX(freq: number): number {
  const t = Math.log2(freq / CURVE_VIEW.MIN_FREQ) / Math.log2(CURVE_VIEW.MAX_FREQ / CURVE_VIEW.MIN_FREQ)
  return CURVE_VIEW.X0 + t * (CURVE_VIEW.X1 - CURVE_VIEW.X0)
}

export function dbToY(db: number): number {
  const t = (Math.max(CURVE_VIEW.MIN_DB, Math.min(CURVE_VIEW.MAX_DB, db)) - CURVE_VIEW.MIN_DB)
    / (CURVE_VIEW.MAX_DB - CURVE_VIEW.MIN_DB)
  return CURVE_VIEW.Y1 - t * (CURVE_VIEW.Y1 - CURVE_VIEW.Y0)
}

// 周波数軸: メジャー(ラベル付き) + マイナー(目盛りのみ)
const FREQ_MAJOR = [20, 100, 1000, 10000, 20000]
const FREQ_MINOR = [30, 50, 70, 200, 300, 500, 700, 2000, 3000, 5000, 7000]

function freqLabel(f: number): string {
  if (f === 20) return '20Hz'
  if (f >= 1000) return f === 20000 ? '20kHz' : `${f / 1000}k`
  return `${f}`
}

export function calculateTotalCurve(opts: {
  musicType: string
  eqOutput: string
  crossfeed: string
  crossfeedIntensity: number
  humNoise: string
  hpBands: { freq: number; q: number; gain: number; type?: string }[]
  hpIntensity: number
}): { points: TotalCurvePoint[]; maxAbsDb: number } {
  const { MIN_FREQ, MAX_FREQ } = CURVE_VIEW
  const NUM_STEPS = 240   // 42→240: 繊細なカーブ描画
  const srcBands = MUSIC_EQ_BANDS[opts.musicType] || []
  const outBands = OUTPUT_EQ_BANDS[opts.eqOutput] || []
  const calibScale = opts.hpIntensity / 100.0
  const points: TotalCurvePoint[] = []
  let maxAbsDb = 0
  for (let i = 0; i <= NUM_STEPS; i++) {
    const t = i / NUM_STEPS
    const freq = MIN_FREQ * Math.pow(MAX_FREQ / MIN_FREQ, t)
    let db = 0
    db += eqBandsDbAt(freq, srcBands)
    db += eqBandsDbAt(freq, outBands)
    db += crossfeedDbAt(freq, opts.crossfeed, opts.crossfeedIntensity)
    db += humFilterDbAt(freq, opts.humNoise)
    for (const band of opts.hpBands) {
      db += bandResponseAt(freq, band) * calibScale
    }
    maxAbsDb = Math.max(maxAbsDb, Math.abs(db))
    points.push({ x: freqToX(freq), y: dbToY(db), freq, db })
  }
  return { points, maxAbsDb }
}

// ── TotalCurveOverlay Component (Bisen AlbumArtFrame Total Mode 移植) ─────
interface OverlayProps {
  effects: { label: string; value: string }[]
  curvePoints: TotalCurvePoint[]
  maxAbsDb: number
  onTap: () => void
}

export const TotalCurveOverlay: React.FC<OverlayProps> = ({
  effects, curvePoints, maxAbsDb, onTap,
}) => {
  const showWarning = maxAbsDb > 3.0
  const path = curvePoints.map((p, i) =>
    `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

  return (
    <div
      className="w-full h-full rounded-lg bg-neutral-950/95 p-1.5 flex flex-col justify-between border border-cyan-500/40 relative select-none cursor-pointer"
      onClick={(e) => { e.stopPropagation(); onTap() }}
    >
      {/* Top Info Bar (Bisen: Activity icon + TOTAL EQ CURVE) */}
      <div className="flex items-center justify-between border-b border-cyan-900/40 pb-0.5 shrink-0">
        <div className="flex items-center gap-1">
          <Activity className="w-3 h-3 text-cyan-400 animate-pulse" />
          <span className="text-[7.5px] font-bold text-cyan-300 uppercase tracking-tight">
            TOTAL EQ CURVE
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[6.5px] text-cyan-400/60 font-mono">
            PEAK ±{maxAbsDb.toFixed(1)}dB · 240pt
          </span>
          <span className="text-[6.5px] text-cyan-400/70 uppercase">TAP FOR ARTWORK</span>
        </div>
      </div>

      {/* ±3 dB 過補正警告 (Bisen と同一) */}
      {showWarning && (
        <div className="mt-0.5 px-1 py-0.5 bg-red-950/80 border border-red-500/60 rounded text-[7px] font-bold text-red-300 leading-tight shrink-0">
          ⚠ TOTAL {maxAbsDb.toFixed(1)} dB EXCEEDS SAFE RANGE
        </div>
      )}

      {/* SVG Frequency Response Curve (128x90 直描画・周波数軸付き) */}
      <div className="w-full flex-1 flex items-center justify-center relative py-0.5 min-h-0">
        <svg viewBox="0 0 128 90" className="w-full h-full overflow-visible" preserveAspectRatio="xMidYMid meet">
          {/* 周波数マイナー目盛り (縦線) */}
          {FREQ_MINOR.map((f) => (
            <line key={`fm${f}`} x1={freqToX(f)} y1={CURVE_VIEW.Y0} x2={freqToX(f)} y2={CURVE_VIEW.Y1}
              stroke="#1e293b" strokeWidth="0.3" strokeDasharray="0.8 1.6" />
          ))}
          {/* dB 横グリッド: 0dB (強調) / ±5 / ±10 */}
          <line x1={CURVE_VIEW.X0} y1={dbToY(0)} x2={CURVE_VIEW.X1} y2={dbToY(0)} stroke="#334155" strokeWidth="0.5" strokeDasharray="2 2" />
          {[5, -5, 10, -10].map((db) => (
            <line key={`db${db}`} x1={CURVE_VIEW.X0} y1={dbToY(db)} x2={CURVE_VIEW.X1} y2={dbToY(db)}
              stroke="#1e293b" strokeWidth="0.35" strokeDasharray="1 2.5" />
          ))}
          {/* 周波数メジャー目盛り + 軸ラベル (Android 版相当) */}
          {FREQ_MAJOR.map((f) => (
            <line key={`fM${f}`} x1={freqToX(f)} y1={CURVE_VIEW.Y0} x2={freqToX(f)} y2={CURVE_VIEW.Y1}
              stroke="#334155" strokeWidth="0.4" strokeDasharray="1 2" />
          ))}
          <line x1={CURVE_VIEW.X0} y1={CURVE_VIEW.Y1} x2={CURVE_VIEW.X1} y2={CURVE_VIEW.Y1}
            stroke="#475569" strokeWidth="0.5" />
          {FREQ_MAJOR.map((f) => (
            <text key={`fl${f}`}
              x={f === 20 ? CURVE_VIEW.X0 + 1 : f === 20000 ? CURVE_VIEW.X1 - 1 : freqToX(f)}
              y={CURVE_VIEW.LABEL_Y}
              fill="#64748b" fontSize="4.5" fontFamily="monospace"
              textAnchor={f === 20 ? 'start' : f === 20000 ? 'end' : 'middle'}>
              {freqLabel(f)}
            </text>
          ))}
          {/* dB 軸ラベル (左) */}
          <text x="1" y={dbToY(0) + 1.8} fill="#64748b" fontSize="4.5" fontFamily="monospace">0dB</text>
          <text x="1" y={dbToY(5) + 1.8} fill="#475569" fontSize="4" fontFamily="monospace">+5</text>
          <text x="1" y={dbToY(-5) + 1.8} fill="#475569" fontSize="4" fontFamily="monospace">-5</text>
          {/* 合成カーブ — 細線 (glow 0.22 / main 0.85) */}
          <path d={path} fill="none" stroke="#06b6d4" strokeWidth="2.2" strokeOpacity="0.22"
            strokeLinecap="round" strokeLinejoin="round" />
          <path d={path} fill="none" stroke="#22d3ee" strokeWidth="0.85"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      {/* Active Effects List (Bisen と同一: cyan label + neutral value) */}
      <div className="flex flex-col gap-[2px] bg-black/40 rounded px-1 py-1 border border-cyan-900/30 max-h-[40%] shrink-0 overflow-y-auto">
        {effects.length === 0 ? (
          <span className="text-[7px] text-neutral-500 text-center py-1">NO EFFECTS ACTIVE</span>
        ) : (
          effects.map((eff, idx) => (
            <div key={idx} className="flex items-center justify-between gap-1 text-[7px] leading-tight">
              <span className="text-cyan-400/80 font-bold tracking-wider">{eff.label}</span>
              <span className="text-neutral-300 truncate text-right">{eff.value}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

