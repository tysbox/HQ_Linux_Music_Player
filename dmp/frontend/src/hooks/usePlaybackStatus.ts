'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { PlaybackStatus } from '@/lib/types'
import { WS_URL } from '@/lib/api'

type WsState = 'connecting' | 'connected' | 'disconnected'

export function usePlaybackStatus() {
  const [status, setStatus] = useState<PlaybackStatus>({
    state: 'stop',
    current_track: null,
    position: 0,
    duration: 0,
    queue_length: 0,
    random: false,
    repeat: false,
  })
  const [wsState, setWsState] = useState<WsState>('connecting')
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout>>()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    setWsState('connecting')
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => setWsState('connected')

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'error') return
        setStatus({
          state:         data.state         ?? 'stop',
          current_track: data.current_track ?? null,
          position:      data.position      ?? 0,
          duration:      data.duration      ?? 0,
          queue_length:  data.queue_length  ?? 0,
          random:        data.random        ?? false,
          repeat:        data.repeat        ?? false,
        })
      } catch {}
    }

    ws.onclose = () => {
      setWsState('disconnected')
      retryRef.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  useEffect(() => {
    if (status.state !== 'play') return

    const id = setInterval(() => {
      setStatus(prev => ({
        ...prev,
        position: prev.duration > 0 && prev.position < prev.duration
          ? prev.position + 1
          : prev.position,
      }))
    }, 1000)

    return () => clearInterval(id)
  }, [status.state])

  return { status, wsState }
}
