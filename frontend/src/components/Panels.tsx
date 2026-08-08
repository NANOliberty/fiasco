import { useMemo, useState } from 'react'
import { DiceRow } from './Dice'
import { useGame, playersInTurnOrder } from '../lib/store'
import { PHASE_LABELS, PHASE_ORDER, type LogEntry, type Phase, type Player } from '../types'

export function PhaseBar({ phase }: { phase: Phase }) {
  const currentIndex = PHASE_ORDER.indexOf(phase)
  return (
    <nav className="phase-bar" aria-label="진행 단계">
      {PHASE_ORDER.map((step, i) => {
        const done = currentIndex > i || phase === 'finished'
        const current = currentIndex === i
        return (
          <div
            key={step}
            className={`phase-bar__step ${current ? 'phase-bar__step--current' : done ? 'phase-bar__step--done' : ''}`}
            aria-current={current ? 'step' : undefined}
          >
            {PHASE_LABELS[step]}
          </div>
        )
      })}
    </nav>
  )
}

export function PlayerCard({ player, spotlight }: { player: Player; spotlight?: boolean }) {
  const { state, me, nameOf } = useGame()
  const relationships = useMemo(() => {
    const slots = state.setup?.slots ?? []
    const pairs = state.derived.pairs.filter((p) => p.playerA === player.id || p.playerB === player.id)
    return pairs.map((pair) => {
      const slot = slots.find((s) => s.kind === 'relationship' && s.pairIndex === pair.index)
      const other = pair.playerA === player.id ? pair.playerB : pair.playerA
      return { other, text: slot?.text ?? null, categoryName: slot?.categoryName ?? null }
    })
  }, [state.setup, state.derived.pairs, player.id])

  return (
    <article
      className={[
        'player-card',
        spotlight ? 'player-card--spotlight' : '',
        player.connected ? '' : 'player-card--offline',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="player-card__name">
        <span className={`dot ${player.connected ? '' : 'dot--off'}`} title={player.connected ? '접속 중' : '접속 끊김'} />
        <span>{player.characterName || player.name}</span>
        {player.isHost && <span className="pill tiny">방장</span>}
        {player.id === me?.id && <span className="pill pill--accent tiny">나</span>}
      </div>
      {player.characterName && <div className="player-card__sub">{player.name}</div>}

      {relationships.length > 0 && (
        <div className="stack stack--tight">
          {relationships.map((rel) => (
            <div key={rel.other} className="tiny">
              <span className="faint">↔ {nameOf(rel.other)}: </span>
              {rel.text ? (
                <span>{rel.text}</span>
              ) : (
                <span className="faint">{rel.categoryName ? `${rel.categoryName} (요소 미정)` : '미정'}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <DiceRow dice={player.dice} empty="주사위 없음" />
    </article>
  )
}

export function PlayerGrid() {
  const { state } = useGame()
  const players = playersInTurnOrder(state)
  const spotlightId = state.derived.currentPlayerId
  return (
    <div className="player-grid">
      {players.map((player) => (
        <PlayerCard key={player.id} player={player} spotlight={player.id === spotlightId} />
      ))}
    </div>
  )
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
}

export function LogPanel({ entries }: { entries: LogEntry[] }) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? entries : entries.slice(-40)
  return (
    <section className="card">
      <div className="row row--between">
        <h3 className="card__title" style={{ marginBottom: 0 }}>
          진행 기록
        </h3>
        {entries.length > 40 && (
          <button type="button" className="btn btn--ghost btn--small" onClick={() => setExpanded((v) => !v)}>
            {expanded ? '접기' : `전체 ${entries.length}건`}
          </button>
        )}
      </div>
      <div className="log" style={{ marginTop: '0.6rem' }}>
        {/* column-reverse 라 최신 항목이 위에 온다 */}
        {shown.map((entry) => (
          <div key={entry.id} className={`log__entry log__entry--${entry.kind}`}>
            <span className="log__time">{formatTime(entry.ts)}</span>
            {entry.text}
          </div>
        ))}
        {!shown.length && <p className="faint small">아직 기록이 없습니다.</p>}
      </div>
    </section>
  )
}

export function RulesCard() {
  const { rules } = useGame()
  const [open, setOpen] = useState(false)
  if (!rules.length) return null
  return (
    <section className="card">
      <div className="row row--between">
        <h3 className="card__title" style={{ marginBottom: 0 }}>
          규칙 요약
        </h3>
        <button type="button" className="btn btn--ghost btn--small" onClick={() => setOpen((v) => !v)}>
          {open ? '접기' : '펼치기'}
        </button>
      </div>
      {open && (
        <div className="stack" style={{ marginTop: '0.7rem' }}>
          {rules.map((section) => (
            <div key={section.title}>
              <div className="entry__label">{section.title}</div>
              <ul className="small muted" style={{ margin: '0.2rem 0 0', paddingLeft: '1.1rem' }}>
                {section.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function TwistDetailsCard() {
  const { state, nameOf } = useGame()
  if (!state.twistDetails.length) return null
  return (
    <section className="card">
      <h3 className="card__title">비틀기 요소 — 누구나 쓸 수 있음</h3>
      <div className="stack stack--tight">
        {state.twistDetails.map((detail) => (
          <div key={detail.id} className="detail-chip">
            <div className="entry__label">{detail.categoryName}</div>
            <div className="entry__text">{detail.text}</div>
            <div className="tiny faint">{nameOf(detail.chosenBy)} 님이 고름</div>
          </div>
        ))}
      </div>
    </section>
  )
}

export function CentralPoolCard() {
  const { state } = useGame()
  const { centralByColor, halfway } = state.derived
  const remaining = state.central.length
  const hint =
    state.phase === 'act1'
      ? `절반(${halfway}개)이 되면 1막이 끝납니다.`
      : state.phase === 'act2'
        ? '다 떨어지면 2막이 끝납니다.'
        : null

  return (
    <section className="card">
      <div className="row row--between">
        <h3 className="card__title" style={{ marginBottom: 0 }}>
          중앙 주사위
        </h3>
        <span className="pill">
          {remaining} / {state.totalDice}
        </span>
      </div>
      <div className="row small muted" style={{ marginTop: '0.5rem' }}>
        <span>검 {centralByColor.black}</span>
        <span className="faint">·</span>
        <span>흰 {centralByColor.white}</span>
      </div>
      <div style={{ marginTop: '0.6rem' }}>
        <DiceRow dice={state.central} empty="중앙이 비었습니다" />
      </div>
      {hint && <p className="tiny faint" style={{ marginTop: '0.6rem' }}>{hint}</p>}
    </section>
  )
}

export function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="toast" role="alert">
      <span>{message}</span>
      <button type="button" onClick={onDismiss} aria-label="닫기">
        ✕
      </button>
    </div>
  )
}
