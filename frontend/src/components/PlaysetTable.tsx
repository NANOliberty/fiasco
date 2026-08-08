import { useState } from 'react'
import { useGame, detailsOf, relationshipSlots } from '../lib/store'
import { LIST_LABELS, type ListType, type Playset, type Slot } from '../types'

const TABS: ListType[] = ['relationship', 'desire', 'object', 'place']

/**
 * 플레이세트 표 뷰어. 주사위 눈이 곧 분류/요소 번호라 번호를 늘 같이 보여 준다.
 * highlight 를 주면 그 눈에 해당하는 줄을 강조한다.
 */
export function PlaysetTable({ playset, highlight }: { playset: Playset; highlight?: number | null }) {
  const [tab, setTab] = useState<ListType>('relationship')
  const categories = playset.lists[tab]

  return (
    <section className="card">
      <div className="row row--between" style={{ marginBottom: '0.6rem' }}>
        <h3 className="card__title" style={{ marginBottom: 0 }}>
          {playset.name}
        </h3>
        {highlight ? <span className="pill pill--accent">주사위 눈 {highlight} 강조</span> : null}
      </div>

      <div className="table-tabs" role="tablist">
        {TABS.map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`table-tab ${tab === key ? 'table-tab--active' : ''}`}
            onClick={() => setTab(key)}
          >
            {LIST_LABELS[key]}
          </button>
        ))}
      </div>

      <div className="playset-table">
        {categories.map((category) => (
          <div key={category.number} className="playset-category">
            <div className="playset-category__name">
              <span className="playset-category__number">{category.number}</span>
              <span style={highlight === category.number ? { color: 'var(--accent)' } : undefined}>
                {category.name}
              </span>
            </div>
            <ol>
              {category.elements.map((element) => (
                <li
                  key={element.number}
                  style={
                    highlight === element.number
                      ? { color: 'var(--text)', fontWeight: 550 }
                      : undefined
                  }
                >
                  {element.text}
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </section>
  )
}

function DetailEntry({ slot }: { slot: Slot }) {
  return (
    <div className="detail-chip">
      <div className="entry__label">
        {LIST_LABELS[slot.listType]} · {slot.categoryName}
      </div>
      {slot.text ? (
        <div className="entry__text">{slot.text}</div>
      ) : (
        <div className="entry__text entry__text--pending">요소를 정해야 합니다</div>
      )}
    </div>
  )
}

/** 관계 카드들. 인원수만큼 있고 인접한 두 사람을 잇는다. */
export function RelationshipBoard() {
  const { state, nameOf } = useGame()
  const slots = relationshipSlots(state)

  return (
    <div className="relationship-list">
      {state.derived.pairs.map((pair) => {
        const slot = slots.find((s) => s.pairIndex === pair.index)
        const details = slot ? detailsOf(state, slot.id) : []
        return (
          <article key={pair.index} className={`relationship ${slot ? '' : 'relationship--empty'}`}>
            <header className="relationship__who">
              <strong>{nameOf(pair.playerA)}</strong>
              <span className="faint">↔</span>
              <strong>{nameOf(pair.playerB)}</strong>
            </header>
            <div className="relationship__body">
              {!slot ? (
                <div className="entry__text entry__text--pending">아직 관계가 정해지지 않았습니다</div>
              ) : (
                <div>
                  <div className="entry__label">관계 · {slot.categoryName}</div>
                  {slot.text ? (
                    <div className="entry__text">{slot.text}</div>
                  ) : (
                    <div className="entry__text entry__text--pending">요소를 정해야 합니다</div>
                  )}
                </div>
              )}
              {details.map((detail) => (
                <DetailEntry key={detail.id} slot={detail} />
              ))}
              {slot && !details.length && (
                <div className="tiny faint">세부사항(욕망/물건/장소)이 하나 이상 필요합니다.</div>
              )}
            </div>
          </article>
        )
      })}
    </div>
  )
}
