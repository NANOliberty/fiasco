import { useEffect, useState, type FormEvent } from 'react'
import { api, sessionStore } from '../lib/api'
import type { Session } from '../types'

const NAME_KEY = 'fiasco:name'

export function Landing({ onJoined }: { onJoined: (session: Session) => void }) {
  const [name, setName] = useState(() => localStorage.getItem(NAME_KEY) ?? '')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [prefilled, setPrefilled] = useState(false)

  // 링크에 ?room=CODE 가 붙어 있으면 코드를 채워 준다.
  useEffect(() => {
    const roomFromUrl = new URLSearchParams(window.location.search).get('room')
    if (roomFromUrl) {
      setCode(roomFromUrl.toUpperCase())
      setPrefilled(true)
    }
  }, [])

  const enter = async (roomCode: string) => {
    const trimmed = roomCode.trim().toUpperCase()
    if (!trimmed) {
      setError('방 코드를 입력하세요.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      localStorage.setItem(NAME_KEY, name.trim())
      // 이 방에 이미 자리가 있으면 그 자리로 돌아간다.
      const existing = sessionStore.get(trimmed)
      if (existing) {
        onJoined(existing)
        return
      }
      const session = await api.join(trimmed, name.trim())
      sessionStore.save(session)
      onJoined(session)
    } catch (err) {
      setError(err instanceof Error ? err.message : '입장하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const createRoom = async () => {
    setBusy(true)
    setError(null)
    try {
      const { roomCode } = await api.createRoom()
      await enter(roomCode)
    } catch (err) {
      setError(err instanceof Error ? err.message : '방을 만들지 못했습니다.')
      setBusy(false)
    }
  }

  const submitJoin = (event: FormEvent) => {
    event.preventDefault()
    void enter(code)
  }

  return (
    <div className="landing">
      <div className="landing__inner">
        <header>
          <h1 className="landing__title">피아스코</h1>
          <p className="landing__tag">
            주사위와 차례를 대신 세어 주는 온라인 보드.
            <br />
            이야기는 여러분이, 계산은 이 화면이 합니다.
          </p>
        </header>

        <div className="card stack">
          <label className="stack stack--tight">
            <span className="entry__label">닉네임</span>
            <input
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="화면에 표시될 이름"
              maxLength={20}
              autoComplete="nickname"
            />
          </label>

          <button type="button" className="btn btn--primary btn--block" onClick={createRoom} disabled={busy}>
            새 방 만들기
          </button>

          <div className="divider">또는</div>

          <form className="stack stack--tight" onSubmit={submitJoin}>
            <span className="entry__label">방 코드로 입장</span>
            <input
              className="input code-input"
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
              placeholder="ABC123"
              maxLength={6}
              inputMode="text"
              autoCapitalize="characters"
              spellCheck={false}
              aria-label="방 코드"
            />
            <button type="submit" className="btn btn--block" disabled={busy || !code.trim()}>
              {prefilled ? '초대받은 방에 입장' : '입장하기'}
            </button>
          </form>

          {error && <div className="notice notice--danger">{error}</div>}
        </div>

        <p className="tiny faint" style={{ textAlign: 'center' }}>
          3~5명이 필요합니다. 음성 통화는 디스코드 같은 걸 따로 켜 두세요 — 여기는 상태 공유용 보드입니다.
        </p>
      </div>
    </div>
  )
}
