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
  const retryRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  // Track previous song_id and state to detect actual changes
  const prevSongIdRef = useRef<string>('')
  const prevStateRef = useRef<string>('stop')
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

        // Payload shape (port 8002 /ws/now_playing — DSP compatible, flat keys):
        // { song_id, title, artist, album, file, state, audio, elapsed, duration }
        // Normalize to { current_track, position, duration, ... }
        const serverPosition = data.position ?? data.elapsed ?? 0
        const serverDuration = data.duration ?? 0
        const serverState    = data.state ?? 'stop'
        const serverSongId   = data.song_id ?? ''

        // Detect actual changes to avoid overwriting local position during play
        const songChanged = serverSongId !== prevSongIdRef.current
        const stateChanged = serverState !== prevStateRef.current
        // Detect user seek: if WS position differs significantly from our local interp,
        // the user must have seeked (or song just started), so trust the server.
        const prev = lastServerPositionRef.current
        const drift = Math.abs(serverPosition - prev)
        const seekDetected = drift > 2  // > 2s jump = seek

        // Always update refs to keep interpolation accurate
        lastServerPositionRef.current = serverPosition
        lastServerTimeRef.current = Date.now()
        if (songChanged || stateChanged) {
          prevSongIdRef.current = serverSongId
          prevStateRef.current = serverState
        }

        const track = (data.title || data.artist || data.file)
          ? {
              title:  data.title  ?? '',
              artist: data.artist ?? '',
              album:  data.album  ?? '',
              uri:    data.file   ?? '',
              song_id: data.song_id ?? '',
              artwork_url: data.artwork_url ?? null,
            }
          : (data.current_track ?? null)

        setStatus(prevState => {
          // Apply server position on song/state change OR on detected seek (drift > 2s)
          // This way the slider reflects the actual MPD position after user seeks.
          const applyServerPos = songChanged || stateChanged || seekDetected
          const newPosition = applyServerPos ? serverPosition : prevState.position
          return {
            state:         serverState,
            current_track: track,
            position:      newPosition,
            duration:      serverDuration || prevState.duration,
            queue_length:  data.queue_length  ?? prevState.queue_length,
            random:        data.random        ?? prevState.random,
            repeat:        data.repeat        ?? prevState.repeat,
          }
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

  // 再生中のみローカルタイマーで位置を補間（500ms ごとに lastServerPosition ベースで増分）
  useEffect(() => {
    if (status.state !== 'play') {
      if (positionTimerRef.current) {
        clearInterval(positionTimerRef.current)
        positionTimerRef.current = null
      }
      return
    }

    // 500ms ごとに 0.5 秒進める → UI が滑らかに追従
    const id = setInterval(() => {
      setStatus(prev => {
        const now = Date.now()
        const elapsedSinceServer = (now - lastServerTimeRef.current) / 1000
        const newPosition = Math.min(
          prev.duration,
          Math.floor(lastServerPositionRef.current + elapsedSinceServer)
        )
        return { ...prev, position: newPosition }
      })
    }, 500)

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
