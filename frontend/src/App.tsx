import { useCallback, useEffect, useState } from 'react'
import { sessionStore } from './lib/api'
import { useConnection, type ConnectionStatus } from './lib/connection'
import { GameProvider, useGame } from './lib/store'
import {
  CentralPoolCard,
  LogPanel,
  PhaseBar,
  PlayerGrid,
  RulesCard,
  Toast,
  TwistDetailsCard,
} from './components/Panels'
import { Landing } from './screens/Landing'
import { Lobby } from './screens/Lobby'
import { Setup } from './screens/Setup'
import { SceneScreen } from './screens/Scene'
import { Twist } from './screens/Twist'
import { Aftermath } from './screens/Aftermath'
import type { Session } from './types'

const THEME_KEY = 'fiasco:theme'

function useTheme() {
  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => (localStorage.getItem(THEME_KEY) as 'dark' | 'light' | null) ?? 'dark',
  )
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])
  return { theme, toggle: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')) }
}

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting: '연결 중…',
  open: '',
  reconnecting: '다시 연결하는 중…',
  fatal: '연결 실패',
}

function TopBar({ onLeave }: { onLeave: () => void }) {
  const { state, status, isHost, send } = useGame()
  const { theme, toggle } = useTheme()
  return (
    <header className="topbar">
      <span className="topbar__brand">피아스코</span>
      <span className="topbar__code" title="방 코드">
        {state.roomCode}
      </span>
      {STATUS_LABEL[status] && <span className="pill pill--danger">{STATUS_LABEL[status]}</span>}
      <div className="spacer" />
      {isHost && (state.phase === 'act1' || state.phase === 'act2') && (
        <button
          type="button"
          className="btn btn--ghost btn--small"
          onClick={() => send('host_force_advance')}
          title="막혔을 때 방장이 한 칸 밀어 줍니다"
        >
          강제 진행
        </button>
      )}
      <button type="button" className="btn btn--ghost btn--small" onClick={toggle} aria-label="화면 밝기 전환">
        {theme === 'dark' ? '☀' : '☾'}
      </button>
      <button type="button" className="btn btn--ghost btn--small" onClick={onLeave}>
        나가기
      </button>
    </header>
  )
}

function Screen() {
  const { state } = useGame()
  switch (state.phase) {
    case 'lobby':
      return <Lobby />
    case 'setup':
      return <Setup />
    case 'act1':
    case 'act2':
      return <SceneScreen />
    case 'twist':
      return <Twist />
    case 'aftermath':
    case 'finished':
      return <Aftermath />
    default:
      return null
  }
}

function Room({ session, onLeave }: { session: Session; onLeave: () => void }) {
  const connection = useConnection(session)

  // 자리가 사라진 뒤에도 저장된 참가 정보를 들고 있으면 새로고침할 때마다 같은
  // 곳에서 막힌다. 거절당한 순간 지워서 다음 입장이 새로 시작되게 한다.
  useEffect(() => {
    if (connection.fatal) sessionStore.clear(session.roomCode)
  }, [connection.fatal, session.roomCode])

  if (connection.fatal) {
    return (
      <div className="landing">
        <div className="landing__inner">
          <div className="card stack">
            <h2>들어가지 못했습니다</h2>
            <p className="muted">{connection.fatal}</p>
            <button type="button" className="btn btn--primary" onClick={onLeave}>
              처음으로
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!connection.state) {
    return (
      <div className="landing">
        <div className="landing__inner">
          <p className="landing__tag">방에 들어가는 중…</p>
        </div>
      </div>
    )
  }

  const { state } = connection
  const showBoard = state.phase !== 'lobby'

  return (
    <GameProvider connection={connection} state={state}>
      <div className="app">
        <TopBar onLeave={onLeave} />
        <div className="layout">
          <Screen />
          <aside className="layout__side">
            {showBoard && <PhaseBar phase={state.phase} />}
            {showBoard && (
              <section className="card">
                <h3 className="card__title">플레이어</h3>
                <PlayerGrid />
              </section>
            )}
            {showBoard && <CentralPoolCard />}
            <TwistDetailsCard />
            <RulesCard />
            <LogPanel entries={state.log} />
          </aside>
        </div>
        {connection.error && <Toast message={connection.error} onDismiss={connection.dismissError} />}
      </div>
    </GameProvider>
  )
}

export default function App() {
  useTheme()
  const [session, setSession] = useState<Session | null>(() => {
    const roomFromUrl = new URLSearchParams(window.location.search).get('room')
    if (roomFromUrl) return sessionStore.get(roomFromUrl.toUpperCase())
    return sessionStore.latest()
  })

  const join = useCallback((next: Session) => {
    setSession(next)
    window.history.replaceState({}, '', `/?room=${next.roomCode}`)
  }, [])

  const leave = useCallback(() => {
    if (session) sessionStore.clear(session.roomCode)
    setSession(null)
    window.history.replaceState({}, '', '/')
  }, [session])

  if (!session) return <Landing onJoined={join} />
  return <Room key={session.roomCode + session.playerId} session={session} onLeave={leave} />
}
