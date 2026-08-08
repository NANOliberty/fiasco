import { useGame, playersInTurnOrder } from '../lib/store'
import { DiceRow } from '../components/Dice'

function TallyRow({ playerId }: { playerId: string }) {
  const { state, nameOf, playerById } = useGame()
  const tally = state.twist?.tallies[playerId]
  const player = playerById(playerId)
  if (!tally || !player) return null
  const isChooser = state.twist?.choosers.includes(playerId)

  return (
    <div className="card" style={isChooser ? { borderColor: 'var(--accent)' } : undefined}>
      <div className="row row--between">
        <strong>{nameOf(playerId)}</strong>
        {isChooser && <span className="pill pill--accent">고를 사람</span>}
      </div>
      <div className="row small muted" style={{ marginTop: '0.3rem' }}>
        <span>검 {tally.black}</span>
        <span className="faint">−</span>
        <span>흰 {tally.white}</span>
        <span className="faint">=</span>
        <strong style={{ color: 'var(--text)' }}>
          {tally.value}
          {tally.color ? (tally.color === 'black' ? ' 검은색' : ' 흰색') : ' (동점)'}
        </strong>
      </div>
      <div style={{ marginTop: '0.4rem' }}>
        <DiceRow dice={player.dice} empty="주사위 없음" />
      </div>
    </div>
  )
}

export function Twist() {
  const { state, me, send, nameOf, twistTable } = useGame()
  const twist = state.twist
  if (!twist) return null

  const myQuota = me ? twist.choosers.filter((id) => id === me.id).length : 0
  const myPicks = twist.picks.filter((pick) => pick.chooserId === me?.id).length
  const myTurn = myQuota > myPicks
  const reference = me ? twist.reference[me.id] : undefined
  const remaining = twist.choosers.length - twist.picks.length

  return (
    <div className="layout__main">
      <section className="card stack">
        <h2>비틀기</h2>
        <p className="muted small">
          1막이 끝났습니다. 각자 앞의 주사위를 굴려 흑과 백의 차이를 냈고, 검은색 최고점자와 흰색 최고점자가 하나씩
          고릅니다. 고른 요소는 누구의 것도 아니어서 2막에서 누구나 쓸 수 있습니다.
        </p>
      </section>

      <section className="stack">
        <h3 className="card__title">합산 결과</h3>
        <div className="result-grid">
          {playersInTurnOrder(state).map((player) => (
            <TallyRow key={player.id} playerId={player.id} />
          ))}
        </div>
      </section>

      {twist.picks.length > 0 && (
        <section className="card stack">
          <h3 className="card__title">고른 비틀기 요소</h3>
          {twist.picks.map((pick) => (
            <div key={pick.id} className="detail-chip">
              <div className="entry__label">
                {pick.categoryName} · {pick.category}-{pick.element}
              </div>
              <div className="entry__text">{pick.text}</div>
              <div className="tiny faint">{nameOf(pick.chooserId)} 님이 고름</div>
            </div>
          ))}
        </section>
      )}

      <section className="card stack">
        <div className="row row--between">
          <h3 className="card__title" style={{ marginBottom: 0 }}>
            비틀기 표
          </h3>
          {myTurn ? (
            <button type="button" className="btn btn--small" onClick={() => send('twist_reference_roll')}>
              참고용으로 굴리기
            </button>
          ) : (
            <span className="pill">{remaining}개 남음</span>
          )}
        </div>

        {myTurn ? (
          <>
            {reference && (
              <div className="notice small">
                굴린 값 — 분류 {reference[0]}, 요소 {reference[1]}. 참고만 하고 원하는 걸 고르면 됩니다.
              </div>
            )}
            <p className="tiny faint">아래에서 하나를 고르세요.</p>
          </>
        ) : (
          <p className="muted small">
            {twist.choosers
              .filter((id) => twist.picks.filter((p) => p.chooserId === id).length < twist.choosers.filter((c) => c === id).length)
              .map((id) => nameOf(id))
              .join(', ')}{' '}
            님이 고르는 중입니다.
          </p>
        )}

        <div className="playset-table">
          {twistTable.map((category, categoryIndex) => {
            const categoryNumber = categoryIndex + 1
            const suggested = reference?.[0] === categoryNumber
            return (
              <div key={category.category} className="playset-category">
                <div className="playset-category__name">
                  <span className="playset-category__number">{categoryNumber}</span>
                  <span style={suggested ? { color: 'var(--accent)' } : undefined}>{category.category}</span>
                </div>
                <div className="stack stack--tight">
                  {category.elements.map((element, elementIndex) => {
                    const elementNumber = elementIndex + 1
                    const highlighted = suggested && reference?.[1] === elementNumber
                    return (
                      <button
                        key={element}
                        type="button"
                        className="option"
                        disabled={!myTurn}
                        onClick={() => send('twist_choose', { category: categoryNumber, element: elementNumber })}
                        style={highlighted ? { borderColor: 'var(--accent)', background: 'var(--accent-soft)' } : undefined}
                      >
                        <span className="option__tag">{elementNumber}</span>
                        <span className="option__main">
                          <span className="option__title">{element}</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
