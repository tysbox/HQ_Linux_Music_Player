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

  // Inline styles — only one face is visible at a time (the other is
  // backface-visibility:hidden + rotated away). No CSS file in this repo.
  const style = (
    <style dangerouslySetInnerHTML={{ __html: `
      :root { color-scheme: dark; }
      * { box-sizing: border-box; }
      html, body { margin: 0; padding: 0; height: 100%; background: #0b0b0f; color: #e6e6e6;
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; overflow: hidden; }
      .stage { position: fixed; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
      .corner-badge {
        position: fixed; top: 16px; left: 16px; z-index: 50;
        display: flex; align-items: center; gap: 8px;
        padding: 8px 14px; border-radius: 999px;
        background: rgba(0,0,0,0.55); border: 1px solid rgba(255,255,255,0.12);
        font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
      }
      .corner-badge .dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 8px #22c55e; }
      .corner-badge.is-dmp .dot { background: #3b82f6; box-shadow: 0 0 8px #3b82f6; }
      .card {
        position: relative; width: 100vw; height: 100vh; max-width: none; max-height: none;
        transform-style: preserve-3d; transition: transform 0.7s cubic-bezier(0.4, 0.0, 0.2, 1);
        border-radius: 0; box-shadow: none;
      }
      .card.is-flipped { transform: rotateY(180deg); }
      .face {
        position: absolute; inset: 0; border-radius: 0; overflow: auto;
        backface-visibility: hidden; -webkit-backface-visibility: hidden;
        background: #0b0b0f;
      }
      .face--front { transform: rotateY(0deg); }
      .face--back  { transform: rotateY(180deg); }
      .face iframe { width: 100%; height: 100%; border: 0; display: block; }
      .flip-btn {
        position: fixed; bottom: 28px; right: 28px; z-index: 50;
        display: flex; align-items: center; justify-content: center; gap: 10px;
        padding: 12px 22px; border-radius: 999px; cursor: pointer;
        background: linear-gradient(180deg, #d8c9a0, #b08d5f); color: #1a1207;
        border: 1px solid rgba(0,0,0,0.25); font-weight: 600; font-size: 14px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.5); transition: transform 0.15s ease;
      }
      .flip-btn:hover { transform: scale(1.04); }
      .flip-btn:active { transform: scale(0.97); }
      .flip-btn .glyph { font-size: 18px; }
      .corner-badge { z-index: 60; }
    ` }} />
  )

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
    <>
      {style}
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
    </>
  )
}