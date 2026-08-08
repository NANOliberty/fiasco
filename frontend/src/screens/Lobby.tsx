import { useEffect, useState } from 'react'
import { api, roomLink } from '../lib/api'
import { useGame } from '../lib/store'
import { PlaysetEditor } from './PlaysetEditor'
import type { PlaysetSummary } from '../types'

function InviteRow({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  const link = roomLink(code)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt('이 링크를 복사해서 친구들에게 보내세요', link)
    }
  }

  return (
    <div className="row">
      <input className="input" readOnly value={link} onFocus={(e) => e.target.select()} style={{ flex: 1 }} />
      <button type="button" className="btn" onClick={copy}>
        {copied ? '복사됨' : '링크 복사'}
      </button>
    </div>
  )
}

function SeatOrder() {
  const { state, isHost, send, nameOf } = useGame()
  if (state.players.length < 2) return null

  const move = (index: number, delta: number) => {
    const order = [...state.players].sort((a, b) => a.seat - b.seat).map((p) => p.id)
    const target = index + delta
    if (target < 0 || target >= order.length) return
    ;[order[index], order[target]] = [order[target], order[index]]
    send('set_seat_order', { order })
  }

  return (
    <div className="stack stack--tight">
      <span className="entry__label">자리 순서 — 관계는 옆자리끼리 맺습니다</span>
      {[...state.players]
        .sort((a, b) => a.seat - b.seat)
        .map((player, index, all) => (
          <div key={player.id} className="row">
            <span className="pill">{index + 1}</span>
            <span style={{ flex: 1 }}>{nameOf(player.id)}</span>
            {state.startingSeat === player.seat && <span className="pill pill--accent tiny">시작</span>}
            {isHost && (
              <>
                <button
                  type="button"
                  className="btn btn--ghost btn--small"
                  onClick={() => move(index, -1)}
                  disabled={index === 0}
                  aria-label={`${nameOf(player.id)} 위로`}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--small"
                  onClick={() => move(index, 1)}
                  disabled={index === all.length - 1}
                  aria-label={`${nameOf(player.id)} 아래로`}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--small"
                  onClick={() => send('set_starting_player', { playerId: player.id })}
                  disabled={state.startingSeat === player.seat}
                >
                  먼저
                </button>
              </>
            )}
          </div>
        ))}
      {isHost && (
        <p className="tiny faint">
          가장 작은 동네에서 온 사람이 먼저 시작합니다. 해당하는 사람에게 &lsquo;먼저&rsquo;를 눌러 주세요.
        </p>
      )}
    </div>
  )
}

function OptionRules() {
  const { state, isHost, send } = useGame()
  const [open, setOpen] = useState(false)
  const options = state.options

  const toggle = (key: string) => send('set_options', { options: { [key]: !options[key as keyof typeof options] } })

  return (
    <section className="card">
      <div className="row row--between">
        <h3 className="card__title" style={{ marginBottom: 0 }}>
          선택 규칙
        </h3>
        <button type="button" className="btn btn--ghost btn--small" onClick={() => setOpen((v) => !v)}>
          {open ? '접기' : '펼치기'}
        </button>
      </div>
      {open && (
        <div className="stack" style={{ marginTop: '0.7rem' }}>
          <label className="stack stack--tight">
            <span className="entry__label">주사위 개수 조절 — 인당 {options.dicePerPlayer}개</span>
            <select
              className="select"
              value={options.dicePerPlayer}
              disabled={!isHost}
              onChange={(e) => send('set_options', { options: { dicePerPlayer: Number(e.target.value) } })}
            >
              <option value={2}>인당 2개 — 아주 짧게</option>
              <option value={4}>인당 4개 — 기본</option>
              <option value={6}>인당 6개 — 길게</option>
              <option value={8}>인당 8개 — 아주 길게</option>
            </select>
            <span className="tiny faint">
              총 {state.players.length * options.dicePerPlayer}개. 막마다{' '}
              {(state.players.length * options.dicePerPlayer) / 2}개의 장면이 나옵니다.
            </span>
          </label>

          <label className="stack stack--tight">
            <span className="entry__label">흑백 불균형 — 검은 주사위 {Math.round(options.blackRatio * 100)}%</span>
            <input
              type="range"
              min={0.2}
              max={0.8}
              step={0.05}
              value={options.blackRatio}
              disabled={!isHost}
              onChange={(e) => send('set_options', { options: { blackRatio: Number(e.target.value) } })}
            />
            <span className="tiny faint">검은색이 많을수록 더 험한 이야기가 됩니다.</span>
          </label>

          {(
            [
              ['freeLastSetupDie', '마지막 주사위 자유화', '준비의 마지막 주사위 눈을 원하는 값으로 정합니다.'],
              ['accelerator', '액셀 밟기', '2막을 일찍 끝내고 남은 주사위를 후기용으로 나눕니다.'],
              ['goodBadDice', '좋은 주사위/나쁜 주사위', '몽타주에서 흰색은 긍정, 검은색은 부정으로 선언합니다.'],
            ] as const
          ).map(([key, title, description]) => (
            <label key={key} className="row" style={{ alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                checked={options[key]}
                disabled={!isHost}
                onChange={() => toggle(key)}
                style={{ marginTop: '0.35rem' }}
              />
              <span style={{ flex: 1 }}>
                <span style={{ fontWeight: 550 }}>{title}</span>
                <br />
                <span className="tiny faint">{description}</span>
              </span>
            </label>
          ))}
        </div>
      )}
    </section>
  )
}

export function Lobby() {
  const { state, isHost, me, send, nameOf } = useGame()
  const [playsets, setPlaysets] = useState<PlaysetSummary[]>([])
  const [editorOpen, setEditorOpen] = useState(false)
  const [nickname, setNickname] = useState(me?.name ?? '')

  const loadPlaysets = () => {
    api.playsets().then(setPlaysets).catch(() => undefined)
  }
  useEffect(loadPlaysets, [])

  const count = state.players.length
  const canStart = count >= 3 && count <= 5 && !!state.playsetId

  return (
    <div className="layout__main">
      <section className="card stack">
        <h2>로비</h2>
        <p className="muted small">
          방 코드 <strong className="topbar__code">{state.roomCode}</strong> — 링크를 보내면 친구들이 바로 들어옵니다.
        </p>
        <InviteRow code={state.roomCode} />
      </section>

      <section className="card stack">
        <div className="row row--between">
          <h3 className="card__title" style={{ marginBottom: 0 }}>
            참가자 {count} / 5
          </h3>
          {count < 3 && <span className="pill pill--danger">{3 - count}명 더 필요</span>}
        </div>

        <div className="stack stack--tight">
          {state.players.map((player) => (
            <div key={player.id} className="row">
              <span className={`dot ${player.connected ? '' : 'dot--off'}`} />
              <span style={{ flex: 1 }}>{nameOf(player.id)}</span>
              {player.isHost && <span className="pill tiny">방장</span>}
              {player.id === me?.id && <span className="pill pill--accent tiny">나</span>}
            </div>
          ))}
        </div>

        <label className="stack stack--tight">
          <span className="entry__label">내 닉네임</span>
          <div className="row">
            <input
              className="input"
              value={nickname}
              maxLength={20}
              onChange={(e) => setNickname(e.target.value)}
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="btn"
              onClick={() => send('set_name', { name: nickname })}
              disabled={!nickname.trim() || nickname === me?.name}
            >
              바꾸기
            </button>
          </div>
        </label>

        <SeatOrder />
      </section>

      <section className="card stack">
        <div className="row row--between">
          <h3 className="card__title" style={{ marginBottom: 0 }}>
            플레이세트
          </h3>
          <button type="button" className="btn btn--ghost btn--small" onClick={() => setEditorOpen((v) => !v)}>
            {editorOpen ? '닫기' : '직접 만들기'}
          </button>
        </div>

        <div className="stack stack--tight">
          {playsets.map((playset) => (
            <button
              key={playset.id}
              type="button"
              className="option"
              disabled={!isHost}
              onClick={() => send('set_playset', { playsetId: playset.id })}
              style={
                state.playsetId === playset.id
                  ? { borderColor: 'var(--accent)', background: 'var(--accent-soft)' }
                  : undefined
              }
            >
              <span className="option__tag">{playset.custom ? '직접' : '내장'}</span>
              <span className="option__main">
                <span className="option__title">{playset.name}</span>
                {state.playsetId === playset.id && <span className="option__sub">선택됨</span>}
              </span>
            </button>
          ))}
          {!playsets.length && <p className="faint small">플레이세트를 불러오는 중…</p>}
        </div>

        {!isHost && <p className="tiny faint">방장이 플레이세트를 고릅니다.</p>}

        {editorOpen && (
          <PlaysetEditor
            onCreated={(playset) => {
              loadPlaysets()
              if (isHost) send('set_playset', { playsetId: playset.id })
              setEditorOpen(false)
            }}
          />
        )}
      </section>

      <OptionRules />

      {isHost ? (
        <button type="button" className="btn btn--primary btn--block" onClick={() => send('start_game')} disabled={!canStart}>
          {canStart ? '준비 단계 시작' : count < 3 ? '3명 이상 모여야 합니다' : '플레이세트를 고르세요'}
        </button>
      ) : (
        <p className="notice">방장이 시작하기를 기다리는 중입니다.</p>
      )}
    </div>
  )
}
