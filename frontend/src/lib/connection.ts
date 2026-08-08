import { useCallback, useEffect, useRef, useState } from 'react'
import type { GameState, Session } from '../types'

export type ConnectionStatus = 'connecting' | 'open' | 'reconnecting' | 'fatal'

const PING_INTERVAL = 25_000
const BACKOFF_MS = [500, 1_000, 2_000, 4_000, 8_000, 15_000]

export interface Connection {
  state: GameState | null
  you: string | null
  status: ConnectionStatus
  fatal: string | null
  error: string | null
  dismissError: () => void
  send: (action: string, payload?: Record<string, unknown>) => void
}

function socketUrl(session: Session): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const params = new URLSearchParams({ playerId: session.playerId, token: session.token })
  return `${protocol}//${window.location.host}/ws/${session.roomCode}?${params}`
}

/**
 * 방 하나에 붙어 상태를 받아 오는 훅.
 *
 * 서버가 변경 때마다 전체 상태를 보내 주므로 클라이언트는 마지막 것만 그리면 된다.
 * 연결이 끊기면 점점 간격을 늘려 가며 다시 붙는다.
 */
export function useConnection(session: Session | null): Connection {
  const [state, setState] = useState<GameState | null>(null)
  const [you, setYou] = useState<string | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [fatal, setFatal] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const socketRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const closedByUs = useRef(false)

  useEffect(() => {
    if (!session) return
    closedByUs.current = false
    let reconnectTimer: number | undefined
    let pingTimer: number | undefined

    const connect = () => {
      setStatus(attemptRef.current === 0 ? 'connecting' : 'reconnecting')
      const socket = new WebSocket(socketUrl(session))
      socketRef.current = socket

      socket.onopen = () => {
        attemptRef.current = 0
        setStatus('open')
        pingTimer = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ping' }))
        }, PING_INTERVAL)
      }

      socket.onmessage = (event) => {
        let message: { type: string; [key: string]: unknown }
        try {
          message = JSON.parse(event.data as string)
        } catch {
          return
        }
        if (message.type === 'state') {
          setState(message.state as GameState)
          setYou(message.you as string)
        } else if (message.type === 'error') {
          setError(message.message as string)
        } else if (message.type === 'fatal') {
          closedByUs.current = true
          setFatal(message.message as string)
          setStatus('fatal')
        }
      }

      socket.onclose = () => {
        window.clearInterval(pingTimer)
        if (closedByUs.current) return
        const delay = BACKOFF_MS[Math.min(attemptRef.current, BACKOFF_MS.length - 1)]
        attemptRef.current += 1
        setStatus('reconnecting')
        reconnectTimer = window.setTimeout(connect, delay)
      }

      socket.onerror = () => socket.close()
    }

    connect()
    return () => {
      closedByUs.current = true
      window.clearTimeout(reconnectTimer)
      window.clearInterval(pingTimer)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [session])

  // 오류 메시지는 잠깐 보여 주고 스스로 사라진다.
  useEffect(() => {
    if (!error) return
    const timer = window.setTimeout(() => setError(null), 6_000)
    return () => window.clearTimeout(timer)
  }, [error])

  const send = useCallback((action: string, payload: Record<string, unknown> = {}) => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError('서버와 연결이 끊겼습니다. 다시 연결하는 중입니다…')
      return
    }
    socket.send(JSON.stringify({ type: 'action', action, payload }))
  }, [])

  const dismissError = useCallback(() => setError(null), [])

  return { state, you, status, fatal, error, dismissError, send }
}
