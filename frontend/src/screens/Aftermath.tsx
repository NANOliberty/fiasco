import { useState } from 'react'
import { DieView, DiceRow } from '../components/Dice'
import { useGame, playersInTurnOrder } from '../lib/store'
import type { AftermathResult } from '../types'

function ResultCard({ playerId, result }: { playerId: string; result: AftermathResult }) {
  const { nameOf, playerById } = useGame()
  const player = playerById(playerId)
  const tone = result.color ?? 'none'
  return (
    <article className={`result result--${tone}`}>
      <div className="row row--between">
        <strong>{nameOf(playerId)}</strong>
        <span className="result__score">
          검 {result.black} · 흰 {result.white}
        </span>
      </div>
      <div className="result__title">{result.outcome.title}</div>
      <div className="small muted" style={{ marginTop: '0.2rem' }}>
        {result.outcome.text}
      </div>
      <div className="row small faint" style={{ marginTop: '0.5rem' }}>
        <span className="pill">
          {result.color === 'black' ? '검은색' : result.color === 'white' ? '흰색' : '동점'} {result.outcome.value}
        </span>
        <span>구간 {result.outcome.range}</span>
      </div>
      {player && (
        <div style={{ marginTop: '0.5rem' }}>
          <DiceRow dice={player.dice} empty="다 내려놓음" />
        </div>
      )}
    </article>
  )
}

function Montage() {
  const { state, me, isHost, send, nameOf } = useGame()
  const aftermath = state.aftermath!
  const currentId = state.derived.currentPlayerId
  const isMine = me?.id === currentId
  const [text, setText] = useState('')
  const [selectedDie, setSelectedDie] = useState<string | null>(null)

  const myDice = me?.dice ?? []
  const place = () => {
    send('montage_place', { text, dieId: selectedDie ?? undefined })
    setText('')
    setSelectedDie(null)
  }

  return (
    <section className="card stack">
      <div className="row row--between">
        <h3 className="card__title" style={{ marginBottom: 0 }}>
          몽타주
        </h3>
        <span className={`pill ${isMine ? 'pill--accent' : ''}`}>
          {isMine ? '내 차례' : `${nameOf(currentId)} 님 차례`}
        </span>
      </div>
      <p className="tiny faint">
        주사위를 하나씩 중앙에 내려놓으며 &ldquo;이것은 ○○입니다…&rdquo; 하고 마지막 모습을 그립니다.
        {state.options.goodBadDice && ' 흰색은 좋은 일, 검은색은 나쁜 일로 말해 주세요.'}
      </p>

      {isMine && myDice.length > 0 && (
        <div className="stack stack--tight">
          <span className="entry__label">내려놓을 주사위</span>
          <div className="row">
            {myDice.map((die) => (
              <DieView
                key={die.id}
                die={die}
                size="large"
                selected={selectedDie === die.id}
                onClick={() => setSelectedDie(selectedDie === die.id ? null : die.id)}
              />
            ))}
          </div>
          <textarea
            className="textarea"
            rows={2}
            value={text}
            placeholder={`이것은 ${me?.characterName || me?.name}입니다. …`}
            onChange={(event) => setText(event.target.value)}
          />
          <div className="row">
            <button type="button" className="btn btn--primary" onClick={place}>
              내려놓기
            </button>
            <button type="button" className="btn btn--ghost" onClick={() => send('montage_pass')}>
              넘기기
            </button>
          </div>
        </div>
      )}

      {!isMine && <p className="muted small">{nameOf(currentId)} 님이 말하는 중입니다.</p>}

      {(me?.dice.length ?? 0) > 0 && (
        <div className="stack stack--tight">
          <span className="entry__label">주사위가 부족한 사람에게 넘겨주기</span>
          <div className="row">
            {state.players
              .filter((player) => player.id !== me?.id)
              .map((player) => (
                <button
                  key={player.id}
                  type="button"
                  className="btn btn--small"
                  onClick={() => send('montage_gift', { targetPlayerId: player.id, dieId: selectedDie ?? undefined })}
                >
                  {nameOf(player.id)} 에게 ({player.dice.length}개)
                </button>
              ))}
          </div>
        </div>
      )}

      {isHost && (
        <button type="button" className="btn btn--ghost btn--small" onClick={() => send('host_force_advance')}>
          차례 넘기기 (방장)
        </button>
      )}

      {aftermath.entries.length > 0 && (
        <div className="stack stack--tight" style={{ marginTop: '0.4rem' }}>
          <span className="entry__label">지금까지의 몽타주</span>
          {aftermath.entries.map((entry) => (
            <div key={entry.id} className="montage-entry">
              <DieView die={{ id: entry.id, color: entry.color, value: entry.value }} size="small" />
              <div>
                <strong className="small">{nameOf(entry.playerId)}</strong>
                <div className="small muted">{entry.text || <span className="faint">(말없이 내려놓음)</span>}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function Aftermath() {
  const { state, isHost, send } = useGame()
  const aftermath = state.aftermath
  if (!aftermath) return null
  const finished = state.phase === 'finished'

  return (
    <div className="layout__main">
      <section className="card stack">
        <h2>{finished ? '파국' : '후기'}</h2>
        <p className="muted small">
          2막이 끝났습니다. 각자 가진 주사위를 전부 굴려 흑과 백의 차이로 결말을 봤습니다.
          <br />
          2막 마지막 주사위를 임의로 지정했더라도, 이 계산에는 주사위의 실제 색이 그대로 들어갔습니다.
        </p>
      </section>

      <section className="stack">
        <h3 className="card__title">각자의 결말</h3>
        <div className="result-grid">
          {playersInTurnOrder(state).map((player) => {
            const result = aftermath.results[player.id]
            return result ? <ResultCard key={player.id} playerId={player.id} result={result} /> : null
          })}
        </div>
      </section>

      {finished ? (
        <section className="card stack">
          <h3 className="card__title">몽타주 기록</h3>
          {aftermath.entries.map((entry) => (
            <div key={entry.id} className="montage-entry">
              <DieView die={{ id: entry.id, color: entry.color, value: entry.value }} size="small" />
              <div className="small">{entry.text || <span className="faint">(말없이 내려놓음)</span>}</div>
            </div>
          ))}
          {isHost && (
            <button type="button" className="btn btn--primary" onClick={() => send('new_game')}>
              같은 사람들로 새 게임
            </button>
          )}
        </section>
      ) : (
        <Montage />
      )}
    </div>
  )
}
