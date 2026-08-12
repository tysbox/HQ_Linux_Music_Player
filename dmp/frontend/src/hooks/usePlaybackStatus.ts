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
  const positionTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastServerPositionRef = useRef<number>(0)
  const lastServerTimeRef = useRef<number>(Date.now())

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
        
        // サーバーからの正確な位置情報を保存
        const serverPosition = data.position ?? 0
        const serverDuration = data.duration ?? 0
        lastServerPositionRef.current = serverPosition
        lastServerTimeRef.current = Date.now()
        
        setStatus({
          state:         data.state         ?? 'stop',
          current_track: data.current_track ?? null,
          position:      serverPosition,
          duration:      serverDuration,
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

  // 再生中のみローカルタイマーで位置を補間（サーバー位置を基準に）
  useEffect(() => {
    if (status.state !== 'play') {
      if (positionTimerRef.current) {
        clearInterval(positionTimerRef.current)
        positionTimerRef.current = null
      }
      return
    }

    // サーバーからの位置を基準にローカルでインクリメント
    const id = setInterval(() => {
      setStatus(prev => {
        // サーバーからの更新があった場合はそれに従う
        const now = Date.now()
        const timeSinceServerUpdate = now - lastServerTimeRef.current
        
        // サーバー更新から5秒以上経過していればローカル補間を信頼
        // それ以外はサーバー位置を優先
        if (timeSinceServerUpdate > 5000) {
          const newPosition = Math.min(
            prev.duration,
            lastServerPositionRef.current + Math.floor(timeSinceServerUpdate / 1000)
          )
          lastServerPositionRef.current = newPosition
          lastServerTimeRef.current = now
          return { ...prev, position: newPosition }
        }
        return prev
      })
    }, 1000)

    positionTimerRef.current = id
    return () => {
      if (positionTimerRef.current) {
        clearInterval(positionTimerRef.current)
        positionTimerRef.current = null
      }
    }
  }, [status.state, status.duration])

  return { status, wsState }
}
