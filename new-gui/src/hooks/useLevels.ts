'use client'
// ─────────────────────────────────────────────────────────────────────────────
// useLevels — CamillaDSP 実レベル受信フック (Bisen移植 Phase 2 / Step 2-2)
//
// hq_api の /ws/levels (10Hz) から playback peak/rms [dB] を受信し、
// ref に保持する。ref のみ更新 (= 再レンダリングなし) なので
// VU の rAF アニメーションが 60fps で最新値を読める。
//
// CamillaDSP 切断時は {"error": "dsp_disconnected"} が流れる →
// レベルを -100dB に落として VU がゼロに向かう。再接続は自動 (3 秒)。
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useRef, useState } from 'react'
import { LEVELS_WS_URL } from '@/lib/http'

export interface CdspLevels {
  peakL: number
  peakR: number
  rmsL: number
  rmsR: number
}

const SILENCE: CdspLevels = { peakL: -100, peakR: -100, rmsL: -100, rmsR: -100 }

export function useLevels() {
  const levelsRef = useRef<CdspLevels>(SILENCE)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let closed = false

    const connect = () => {
      if (closed) return
      ws = new WebSocket(LEVELS_WS_URL)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data)
          if (d && d.error) {
            levelsRef.current = SILENCE
            return
          }
          const [pl, pr] = Array.isArray(d.peak) ? d.peak : [-100, -100]
          const [rl, rr] = Array.isArray(d.rms) ? d.rms : [-100, -100]
          levelsRef.current = {
            peakL: Number(pl), peakR: Number(pr),
            rmsL: Number(rl), rmsR: Number(rr),
          }
        } catch { /* 不正パケットは無視 */ }
      }
      ws.onclose = () => {
        setConnected(false)
        levelsRef.current = SILENCE
        if (!closed) retry = setTimeout(connect, 3000)
      }
      ws.onerror = () => ws?.close()
    }

    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [])

  return { levelsRef, connected }
}
