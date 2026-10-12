'use client'
// ─────────────────────────────────────────────────────────────────────────────
// HeadphoneCalibrationModal — Stage 8 (Bisen移植 Phase 1 / Step 1-6)
//
// Bisen-DSP-System (BiScene Audio) の HeadphoneCalibrationDrawer 相当の Popup。
// - variant='mobile' : ボトムシート型ドロワー (Android プレーヤーと同じ挙動)
// - variant='pc'     : 中央ワイド (横長 2 カラム) モーダル
//
// 機能:
//   1. インストール済みプロファイル一覧から選択 → 即時ホットリロード適用
//   2. 同梱 AutoEq 測定カタログ (2,810 機種) 検索・取込み
//   3. 補正強度スライダ (Bisen calibrationIntensity 相当)
//   4. 応答カーブ表示 (Bisen calculateProfileResponseCurve の移植)
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'

interface Band { type: string; freq: number; q: number; gain: number }

/** Bisen calculateProfileResponseCurve の移植 — SVG path 生成 (20Hz-20kHz / ±15dB) */
export function curvePath(bands: Band[] | undefined, width = 320, height = 88): string {
  const minF = 20, maxF = 20000, minDb = -15, maxDb = 15, steps = 42
  const list = bands || []
  const pts: string[] = []
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const freq = minF * Math.pow(maxF / minF, t)
    let db = 0
    for (const b of list) {
      const oct = Math.log2(freq / b.freq)
      let resp = 0
      if (b.type === 'lowshelf') resp = b.gain / (1 + Math.exp(oct * 3))
      else if (b.type === 'highshelf') resp = b.gain / (1 + Math.exp(-oct * 3))
      else {
        const bw = 1 / (b.q || 1)
        resp = b.gain * Math.exp(-0.5 * Math.pow(oct / (bw * 0.5), 2))
      }
      db += resp
    }
    const clamped = Math.max(minDb, Math.min(maxDb, db))
    const x = (Math.log2(freq / minF) / Math.log2(maxF / minF)) * (width - 8) + 4
    const y = height - 10 - ((clamped - minDb) / (maxDb - minDb)) * (height - 20)
    pts.push(`${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`)
  }
  return pts.join(' ')
}

interface Props {
  open: boolean
  variant: 'mobile' | 'pc'
  profile: string           // 現在の headphone_profile ID ('none' = OFF)
  intensity: number         // 現在の補正強度 0-100
  target: string             // 現在の headphone_target ('harman' 既定 / 'flat' / 'bypass' / 機種ID)
  onClose: () => void
  onApply: (profileId: string, intensity: number, targetId: string) => void
}

export function HeadphoneCalibrationModal({ open, variant, profile, intensity, target, onClose, onApply }: Props) {
  const [installed, setInstalled] = useState<any[]>([])
  const [detail, setDetail] = useState<any>(null)       // 選択中プロファイル詳細 (カーブ用)
  const [targetDetail, setTargetDetail] = useState<any>(null)  // ターゲット機種詳細
  const [showTargetCurve, setShowTargetCurve] = useState(false) // カーブ表示切替 (Bisen showingTarget)
  const [catQuery, setCatQuery] = useState('')
  const [catResults, setCatResults] = useState<any[]>([])
  const [catSearching, setCatSearching] = useState(false)
  const [catTotal, setCatTotal] = useState(0)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [localIntensity, setLocalIntensity] = useState(intensity)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 開くたび: インストール済み一覧 + 選択中プロファイル詳細を取得
  useEffect(() => {
    if (!open) return
    setLocalIntensity(intensity)
    api.dsp.profiles().then((list: any) => {
      setInstalled(Array.isArray(list) ? list.filter((p: any) => p.type === 'headphone') : [])
    }).catch(() => setInstalled([]))
  }, [open, intensity, profile])

  useEffect(() => {
    if (!open) return
    if (profile && profile !== 'none') {
      api.dsp.profile(profile).then(setDetail).catch(() => setDetail(null))
    } else {
      setDetail(null)
    }
  }, [open, profile])

  // ターゲット機種詳細 (リキャリブレーション先のカーブ表示用)
  useEffect(() => {
    if (!open) return
    if (target && target !== 'harman' && target !== 'flat' && target !== 'bypass') {
      api.dsp.profile(target).then(setTargetDetail).catch(() => setTargetDetail(null))
    } else {
      setTargetDetail(null)
    }
  }, [open, target])

  // カタログ検索 (300ms デバウンス — Bisen onlineAutoEq.ts の debounce と同様)
  useEffect(() => {
    if (!open) return
    if (searchTimer.current) clearTimeout(searchTimer.current)
    const q = catQuery.trim()
    if (q.length < 2) { setCatResults([]); setCatTotal(0); return }
    searchTimer.current = setTimeout(() => {
      setCatSearching(true)
      api.dsp.headphoneCatalog(q, 8).then((r: any) => {
        setCatResults(r?.entries || [])
        setCatTotal(r?.total || 0)
      }).catch(() => { setCatResults([]); setCatTotal(0) }).finally(() => setCatSearching(false))
    }, 300)
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current) }
  }, [catQuery, open])

  if (!open) return null

  const selectProfile = (id: string) => {
    onApply(id, localIntensity, target)
  }

  const selectTarget = (tid: string) => {
    setShowTargetCurve(true)
    onApply(profile, localIntensity, tid)
  }

  const doImport = async (entryId: string) => {
    setBusyId(entryId)
    try {
      const res = await api.dsp.importHeadphone(entryId)
      const list: any = await api.dsp.profiles()
      setInstalled(Array.isArray(list) ? list.filter((p: any) => p.type === 'headphone') : [])
      if (res?.profile_id) {
        onApply(res.profile_id, localIntensity, target)
        setCatQuery('')
        setCatResults([])
      }
    } catch (e) {
      console.error('catalog import failed', e)
    } finally {
      setBusyId(null)
    }
  }

  const commitIntensity = () => {
    if (profile && profile !== 'none') onApply(profile, localIntensity, target)
  }

  const isMobile = variant === 'mobile'
  const currentName = detail?.name
    || installed.find((p) => p.id === profile)?.name
    || (profile !== 'none' ? profile : '')
  const isOff = profile === 'none'
  const targetLabel = target === 'harman' ? 'HARMAN (DEFAULT)'
    : target === 'flat' ? 'FLAT'
    : target === 'bypass' ? 'BYPASS (素の音)'
    : (targetDetail?.name || target)

  /* ── 共有ブロック ─────────────────────────────────────────── */
  const header = (
    <div className="flex items-center justify-between border-b border-emerald-500/30 pb-2 shrink-0">
      <span className="text-[11px] sm:text-xs font-['Orbitron'] font-black tracking-widest text-emerald-400">
        🎧 HEADPHONE CALIBRATION
      </span>
      <button onClick={onClose} className="text-emerald-400/70 hover:text-emerald-300 text-lg leading-none cursor-pointer">✕</button>
    </div>
  )

  const statusBlock = (
    <div className="flex items-center justify-between gap-2 bg-black/60 border border-white/10 rounded px-3 py-2">
      <div className="min-w-0">
        <div className="text-[9px] text-white/50 font-mono tracking-widest">CURRENT PROFILE</div>
        <div className={`text-xs font-bold truncate ${isOff ? 'text-white/40' : 'text-emerald-300'}`}>
          {isOff ? 'OFF — 機種を選択してください' : currentName}
        </div>
        {!isOff && detail && (
          <div className="text-[9px] text-white/50 font-mono">
            PREAMP {Number(detail.preamp_db ?? 0).toFixed(1)} dB / {detail.bands?.length || 0} bands
          </div>
        )}
        <div className="text-[9px] text-white/50 font-mono">
          TARGET: <span className="text-amber-300 font-bold truncate">{targetLabel}</span>
        </div>
      </div>
      <button
        onClick={() => onApply('none', localIntensity, target)}
        disabled={isOff}
        className={`shrink-0 px-3 py-1.5 text-[10px] font-['Orbitron'] font-bold rounded border cursor-pointer ${
          isOff
            ? 'bg-black/40 text-white/30 border-white/10'
            : 'bg-red-950 hover:bg-red-900 text-red-300 border-red-500/50'
        }`}
      >OFF</button>
    </div>
  )

  const targetBlock = (
    <div className="bg-black/60 border border-white/10 rounded px-3 py-2 flex flex-col gap-2 shrink-0">
      <span className="text-[9px] text-white/50 font-mono tracking-widest">
        RE-CALIBRATION TARGET (リキャリブレーション先)
      </span>
      <div className="grid grid-cols-3 gap-1.5">
        {(['harman', 'flat', 'bypass'] as const).map((v) => (
          <button
            key={v}
            onClick={() => selectTarget(v)}
            className={`px-2 py-2 rounded border text-[10px] font-['Orbitron'] font-bold cursor-pointer shrink-0 min-h-[34px] leading-snug ${
              target === v
                ? 'bg-amber-500/20 border-amber-400 text-amber-300'
                : 'bg-black/30 border-white/10 text-white/70 hover:border-amber-400/50'
            }`}
          >
            {v === 'harman' ? 'HARMAN' : v === 'flat' ? 'FLAT' : 'BYPASS'}
          </button>
        ))}
      </div>
      <div className="text-[8px] text-white/40 font-mono leading-relaxed">
        HARMAN/FLAT = リスニング補正のみ (AutoEq ターゲット近似) / BYPASS = 素の音。
        一覧やカタログの「→TGT」で機種を指定すると、その機種の特性へ近づけます
        (リキャリブレーション = Android プレーヤーと同じ仕様)。
      </div>
    </div>
  )

  const intensityBlock = (
    <div className="bg-black/60 border border-white/10 rounded px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] text-white/50 font-mono tracking-widest">CALIBRATION INTENSITY</span>
        <span className="text-[11px] font-bold text-emerald-300 font-mono">{localIntensity}%</span>
      </div>
      <input
        type="range" min={0} max={100} step={5}
        value={localIntensity}
        disabled={isOff}
        onChange={(e) => setLocalIntensity(Number(e.target.value))}
        onPointerUp={commitIntensity}
        onKeyUp={commitIntensity}
        className="w-full accent-emerald-500 disabled:opacity-40 cursor-pointer"
      />
      <div className="text-[8px] text-white/40 font-mono mt-0.5">
        band ゲインのみスケール (preamp は維持 — Bisen 仕様) / 変更は即時ホットリロード
      </div>
    </div>
  )

  const showTargetView = showTargetCurve && !!targetDetail
  const curveBands = showTargetView ? targetDetail.bands : detail?.bands
  const curveColor = showTargetView ? '#fbbf24' : '#34d399'

  const curveBlock = (
    <div className="bg-black/60 border border-white/10 rounded px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] text-white/50 font-mono tracking-widest">
          RESPONSE CURVE — <span style={{ color: curveColor }}>{showTargetView ? 'TARGET' : 'LISTENING'}</span>
        </span>
        {targetDetail ? (
          <button
            onClick={() => setShowTargetCurve((v) => !v)}
            className="text-[8px] font-mono text-white/50 hover:text-white cursor-pointer shrink-0"
          >⇄ {showTargetView ? 'LISTENING' : 'TARGET'}</button>
        ) : (
          <span className="text-[8px] text-white/40 font-mono">20Hz – 20kHz / ±15dB</span>
        )}
      </div>
      <svg viewBox="0 0 320 88" className="w-full h-[88px]">
        <rect x="0" y="0" width="320" height="88" fill="#000" rx="4" />
        <line x1="4" y1="44" x2="316" y2="44" stroke="#ffffff15" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="4" y1="25" x2="316" y2="25" stroke="#ffffff08" strokeWidth="1" />
        <line x1="4" y1="63" x2="316" y2="63" stroke="#ffffff08" strokeWidth="1" />
        {curveBands?.length ? (
          <path d={curvePath(curveBands)} fill="none" stroke={curveColor} strokeWidth="2" strokeLinejoin="round" />
        ) : (
          <text x="160" y="48" textAnchor="middle" fill="#ffffff30" fontSize="9" fontFamily="monospace">
            NO PROFILE
          </text>
        )}
      </svg>
    </div>
  )

  const catalogBlock = (
    <div className="bg-black/60 border border-white/10 rounded px-3 py-2 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[9px] text-white/50 font-mono tracking-widest">CATALOG — 2,810 MODELS (AutoEq)</span>
        {catSearching && <span className="text-[9px] text-amber-400 font-mono animate-pulse">SEARCHING…</span>}
        {catTotal > 0 && !catSearching && (
          <span className="text-[9px] text-emerald-400/80 font-mono">{catTotal} hits</span>
        )}
      </div>
      <input
        type="text"
        value={catQuery}
        onChange={(e) => setCatQuery(e.target.value)}
        placeholder="機種名で検索 (例: sennheiser hd650 / moondrop)"
        className="w-full bg-black/80 text-white border border-neutral-600 rounded px-2 py-1.5 text-[11px] font-mono placeholder:text-white/30 focus:outline-none focus:border-emerald-500"
      />
      {catResults.length > 0 && (
        <div className="max-h-[150px] overflow-y-auto flex flex-col gap-1 pr-1">
          {catResults.map((e: any) => (
            <div key={e.id} className="flex items-center justify-between gap-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded px-2 py-1.5 shrink-0 min-h-[40px]">
              <div className="min-w-0">
                <div className="text-[11px] text-white font-bold truncate">{e.brand} {e.model}</div>
                <div className="text-[8px] text-white/40 font-mono truncate">
                  {e.form_factor || '—'} / {e.target_curve_label || ''} / pre {e.profile?.preamp_db ?? '?'} dB
                </div>
              </div>
              <div className="flex gap-1 shrink-0">
                <button
                  onClick={() => doImport(e.id)}
                  disabled={busyId === e.id}
                  className="shrink-0 px-2 py-1 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-[9px] font-['Orbitron'] font-bold rounded cursor-pointer"
                >{busyId === e.id ? '…' : 'IMPORT'}</button>
                <button
                  onClick={() => selectTarget(e.profile?.id || e.id)}
                  title="この機種の特性へリキャリブレート"
                  className="shrink-0 px-2 py-1 bg-amber-800 hover:bg-amber-700 text-amber-200 text-[9px] font-['Orbitron'] font-bold rounded cursor-pointer"
                >→TGT</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  const installedBlock = (
    <div className="bg-black/60 border border-white/10 rounded px-3 py-2 flex flex-col gap-2 min-h-0">
      <span className="text-[9px] text-white/50 font-mono tracking-widest">
        INSTALLED PROFILES ({installed.length})
      </span>
      <div className={`${isMobile ? 'max-h-[200px]' : 'max-h-[280px]'} overflow-y-auto flex flex-col gap-1 pr-1`}>
        <button
          onClick={() => onApply('none', localIntensity, target)}
          className={`shrink-0 min-h-[34px] text-left px-2 py-2 rounded border text-[11px] font-bold cursor-pointer leading-snug ${
            isOff ? 'bg-emerald-500/20 border-emerald-400 text-emerald-300' : 'bg-black/30 border-white/10 text-white/60 hover:border-emerald-500/50'
          }`}
        >— OFF (補正なし) —</button>
        {installed.map((p: any) => {
          const sel = p.id === profile
          const isTgt = p.id === target
          return (
            <div key={p.id} className="flex items-stretch gap-0.5 shrink-0 min-h-[34px]">
              <button
                onClick={() => selectProfile(p.id)}
                className={`flex-1 min-w-0 text-left px-2 py-2 rounded-l border text-[11px] font-bold cursor-pointer truncate leading-snug ${
                  sel
                    ? 'bg-emerald-500/20 border-emerald-400 text-emerald-300'
                    : 'bg-black/30 border-white/10 text-white/80 hover:border-emerald-500/50'
                }`}
              >
                {p.name || p.id}
              </button>
              <button
                onClick={() => selectTarget(p.id)}
                title="この機種の特性へリキャリブレート"
                className={`shrink-0 px-2 rounded-r border border-l-0 text-[9px] font-['Orbitron'] font-bold cursor-pointer ${
                  isTgt
                    ? 'bg-amber-500/30 border-amber-400 text-amber-300'
                    : 'bg-black/30 border-white/10 text-white/50 hover:text-amber-300 hover:border-amber-400/50'
                }`}
              >→TGT</button>
            </div>
          )
        })}
      </div>
    </div>
  )

  /* ── レイアウト ───────────────────────────────────────────── */
  return (
    <div
      className={`fixed inset-0 z-[110] bg-black/50 ${isMobile ? 'flex items-end' : 'flex items-center justify-center p-4'}`}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`bg-[#0d0f12] border border-emerald-500/40 shadow-2xl flex flex-col gap-3 p-4 overflow-y-auto ${
          isMobile
            ? 'w-full max-h-[85vh] rounded-t-2xl animate-shutter'
            : 'w-[min(94vw,880px)] max-h-[85vh] rounded-2xl'
        }`}
      >
        {header}
        {isMobile ? (
          /* モバイル: Android プレーヤー (Bisen) と同じ単列ボトムシート */
          <>
            {statusBlock}
            {targetBlock}
            {intensityBlock}
            {curveBlock}
            {catalogBlock}
            {installedBlock}
          </>
        ) : (
          /* PC: 横長 2 カラム — 左: 現状/ターゲット/強度/カーブ、右: カタログ検索 + 一覧 */
          <div className="grid grid-cols-2 gap-3 min-h-0">
            <div className="flex flex-col gap-3 min-w-0">{statusBlock}{targetBlock}{intensityBlock}{curveBlock}</div>
            <div className="flex flex-col gap-3 min-w-0 min-h-0">{catalogBlock}{installedBlock}</div>
          </div>
        )}
        <div className="text-[8px] text-white/30 font-mono text-center shrink-0">
          選択・強度変更は即時適用 (ホットリロード・音は途切れません) / 測定データ: AutoEq (oratory1990 / crinacle) — Bisen-DSP-System より移植
        </div>
      </div>
    </div>
  )
}

