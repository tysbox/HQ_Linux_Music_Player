'use client'

import { useEffect, useState, useCallback } from 'react'

type Face = 'dsp' | 'dmp'

// unified-shell は DSP/DMP フロントエンドの切替 UI として機能する。
// iframe で 3000/3001 を表示し、背後の DSP:8000/DMP:8001 バックエンドが動く。
// 注: hq_api:8002 は unified-shell とは別系統（将来的に SPA 化する選択肢あり）。
const DSP_URL  = 'http://localhost:3000'
const DMP_URL  = 'http://localhost:3001'

export default function Page() {
  const [face, setFace] = useState<Face>('dsp')
  const [flipped, setFlipped] = useState(false)

  // Start the card in the DSP-up orientation. After the page is mounted,
  // request the flip animation. The `flipped` state controls the rotation,
  // so `flipped === false` means DSP face is in front.
  useEffect(() => {
    if (face === 'dmp') setFlipped(true)
    else setFlipped(false)
  }, [face])

  const toggle = useCallback(() => {
    setFace((f) => (f === 'dsp' ? 'dmp' : 'dsp'))
  }, [])

  // Keyboard shortcut: F key toggles faces
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') toggle()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  return (
    <main className="stage">
      {/* Top-left status badge */}
      <div className={`corner-badge${face === 'dmp' ? ' is-dmp' : ''}`}>
        <span className="dot" />
        {face === 'dsp' ? 'DSP MODE' : 'DMP MODE'} · port {face === 'dsp' ? '3000' : '3001'}
      </div>

      {/* 3D flipping card holding two iframes */}
      <div className={`card${flipped ? ' is-flipped' : ''}`}>
        {/* FRONT face — DSP (port 3000) */}
        <div className="face face--front">
          <iframe
            src={DSP_URL}
            title="DSP"
            allow="autoplay; clipboard-read; clipboard-write"
          />
        </div>
        {/* BACK face — DMP (port 3001) */}
        <div className="face face--back">
          <iframe
            src={DMP_URL}
            title="DMP"
            allow="autoplay; clipboard-read; clipboard-write"
          />
        </div>
      </div>

      {/* Floating flip button — oak-framed, aluminum-plated revolving-door */}
      <button
        type="button"
        className="flip-btn"
        onClick={toggle}
        aria-label={`Switch to ${face === 'dsp' ? 'DMP' : 'DSP'}`}
        title="Flip (F)"
      >
        <span className="flip-btn-inner">
          <span className="glyph">⇋</span>
          <span className="label">{face === 'dsp' ? 'DMP' : 'DSP'}</span>
        </span>
      </button>
    </main>
  )
}