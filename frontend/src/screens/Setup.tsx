import { useMemo, useState } from 'react'
import { DieView } from '../components/Dice'
import { PlaysetTable, RelationshipBoard } from '../components/PlaysetTable'
import { useGame, relationshipSlots } from '../lib/store'
import { DETAIL_TYPES, LIST_LABELS, type Die, type DetailType, type ListType, type Slot } from '../types'

interface Option {
  key: string
  tag: string
  title: string
  sub: string
  action: () => void
}

function CharacterNameField() {
  const { me, send } = useGame()
  const [draft, setDraft] = useState(me?.characterName ?? '')
  if (!me) return null
  return (
    <label className="stack stack--tight">
      <span className="entry__label">내 캐릭터 이름</span>
      <div className="row">
        <input
          className="input"
          style={{ flex: 1 }}
          value={draft}
          maxLength={30}
          placeholder="텐트카드에 적을 이름"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button
          type="button"
          className="btn"
          onClick={() => send('set_character_name', { name: draft })}
          disabled={!draft.trim() || draft === me.characterName}
        >
          저장
        </button>
      </div>
    </label>
  )
}

export function Setup() {
  const { state, playset, isHost, isMyTurn, send, nameOf } = useGame()
  const [selectedDie, setSelectedDie] = useState<Die | null>(null)
  const [override, setOverride] = useState<number | null>(null)

  const validation = state.derived.setupValidation
  const relSlots = relationshipSlots(state)
  const openSlots = (state.setup?.slots ?? []).filter((s) => s.element === null)
  const currentName = nameOf(state.derived.currentPlayerId)

  // 중앙에서 사라진 주사위를 계속 들고 있지 않게 한다.
  const liveSelection = selectedDie && state.central.some((d) => d.id === selectedDie.id) ? selectedDie : null
  const isLastDie = state.central.length === 1
  const canOverride = isLastDie && state.options.freeLastSetupDie
  const value = (canOverride ? override : null) ?? liveSelection?.value ?? null

  const pairLabel = (slot: Slot): string => {
    const pair = state.derived.pairs.find((p) => p.index === slot.pairIndex)
    return pair ? `${nameOf(pair.playerA)} ↔ ${nameOf(pair.playerB)}` : ''
  }

  const relationshipLabel = (relationshipSlotId: string | null): string => {
    const rel = relSlots.find((s) => s.id === relationshipSlotId)
    return rel ? pairLabel(rel) : ''
  }

  const options = useMemo<Option[]>(() => {
    if (!playset || !liveSelection || !value) return []
    const dieId = liveSelection.id
    const valueOverride = canOverride && override !== null ? override : undefined
    const list: Option[] = []

    // 1) 이미 차지한 분류 안에서 요소를 정한다.
    for (const slot of openSlots) {
      const category = playset.lists[slot.listType][slot.category - 1]
      const element = category.elements[value - 1]
      list.push({
        key: `assign-${slot.id}`,
        tag: '요소 정하기',
        title: element.text,
        sub: `${LIST_LABELS[slot.listType]} · ${category.name} — ${
          slot.kind === 'relationship' ? pairLabel(slot) : relationshipLabel(slot.relationshipSlotId)
        }`,
        action: () => send('setup_assign_element', { dieId, slotId: slot.id, valueOverride }),
      })
    }

    // 2) 아직 관계가 없는 옆자리 쌍에 관계 분류를 차지한다.
    for (const pair of state.derived.pairs) {
      if (relSlots.some((s) => s.pairIndex === pair.index)) continue
      const category = playset.lists.relationship[value - 1]
      list.push({
        key: `claim-rel-${pair.index}`,
        tag: '관계',
        title: `${category.name} 분류를 차지`,
        sub: `${nameOf(pair.playerA)} ↔ ${nameOf(pair.playerB)}`,
        action: () =>
          send('setup_claim_category', {
            dieId,
            listType: 'relationship' satisfies ListType,
            pairIndex: pair.index,
            valueOverride,
          }),
      })
    }

    // 3) 이미 있는 관계에 세부사항 분류를 차지한다.
    for (const rel of relSlots) {
      for (const type of DETAIL_TYPES as DetailType[]) {
        const category = playset.lists[type][value - 1]
        list.push({
          key: `claim-${type}-${rel.id}`,
          tag: LIST_LABELS[type],
          title: `${category.name} 분류를 차지`,
          sub: `${pairLabel(rel)} 관계에 붙임`,
          action: () =>
            send('setup_claim_category', {
              dieId,
              listType: type,
              relationshipSlotId: rel.id,
              valueOverride,
            }),
        })
      }
    }

    return list
  }, [playset, liveSelection, value, override, canOverride, openSlots, relSlots, state.derived.pairs, send, nameOf])

  const pick = (option: Option) => {
    option.action()
    setSelectedDie(null)
    setOverride(null)
  }

  return (
    <div className="layout__main">
      <section className="card stack">
        <div className="row row--between">
          <h2>준비</h2>
          <span className={`pill ${isMyTurn ? 'pill--accent' : ''}`}>
            {isMyTurn ? '내 차례' : `${currentName} 님 차례`}
          </span>
        </div>
        <p className="muted small">
          주사위를 하나 집어 분류를 차지하거나, 이미 차지한 분류 안에서 요소를 정합니다. 주사위 눈이 곧 번호입니다.
          <br />
          옆자리끼리 관계 하나씩, 관계마다 세부사항 하나씩이 필요합니다.
        </p>
        <CharacterNameField />
      </section>

      <section className="card stack">
        <div className="row row--between">
          <h3 className="card__title" style={{ marginBottom: 0 }}>
            중앙 주사위 {state.central.length}개
          </h3>
          {state.derived.setupDiceRequired !== undefined && (
            <span className="pill">앞으로 최소 {state.derived.setupDiceRequired}개 필요</span>
          )}
        </div>

        {state.central.length === 0 ? (
          <p className="notice">주사위를 모두 썼습니다. 방장이 준비를 마치면 1막이 시작됩니다.</p>
        ) : (
          <>
            <div className="pool">
              {state.central.map((die) => (
                <DieView
                  key={die.id}
                  die={die}
                  size="large"
                  selected={liveSelection?.id === die.id}
                  onClick={
                    isMyTurn
                      ? () => {
                          setSelectedDie(liveSelection?.id === die.id ? null : die)
                          setOverride(null)
                        }
                      : undefined
                  }
                />
              ))}
            </div>
            {!isMyTurn && <p className="tiny faint">{currentName} 님이 고르는 중입니다.</p>}
          </>
        )}

        {liveSelection && canOverride && (
          <div className="stack stack--tight">
            <span className="entry__label">마지막 주사위 — 눈을 원하는 값으로 정할 수 있습니다</span>
            <div className="row">
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`btn btn--small ${(override ?? liveSelection.value) === n ? 'btn--primary' : ''}`}
                  onClick={() => setOverride(n)}
                >
                  {n}
                </button>
              ))}
              <button type="button" className="btn btn--ghost btn--small" onClick={() => setOverride(null)}>
                굴린 값({liveSelection.value})으로
              </button>
            </div>
          </div>
        )}

        {liveSelection && (
          <div className="stack stack--tight">
            <span className="entry__label">
              눈 {value} 으로 할 수 있는 일
            </span>
            <div className="option-list">
              {options.map((option) => (
                <button key={option.key} type="button" className="option" onClick={() => pick(option)}>
                  <span className="option__tag">{option.tag}</span>
                  <span className="option__main">
                    <span className="option__title">{option.title}</span>
                    <span className="option__sub">{option.sub}</span>
                  </span>
                </button>
              ))}
              {!options.length && <p className="faint small">이 주사위로 할 수 있는 일이 없습니다.</p>}
            </div>
          </div>
        )}
      </section>

      <section className="card stack">
        <h3 className="card__title">관계 카드</h3>
        <RelationshipBoard />
      </section>

      {isHost && (
        <section className="card stack">
          <h3 className="card__title">방장 진행</h3>
          {validation?.errors.map((error) => (
            <div key={error} className="notice notice--danger small">
              {error}
            </div>
          ))}
          {validation?.warnings.map((warning) => (
            <div key={warning} className="notice small">
              {warning}
            </div>
          ))}
          <div className="row">
            <button
              type="button"
              className="btn"
              onClick={() => send('quick_setup')}
              disabled={(state.setup?.slots.length ?? 0) > 0}
              title="인원수별로 미리 정해진 세트를 그대로 깔아 줍니다"
            >
              간편 준비
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => send('setup_undo')}
              disabled={!(state.setup?.history.length ?? 0)}
            >
              되돌리기
            </button>
            <div className="spacer" />
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => send('finish_setup')}
              disabled={!validation?.canFinish}
            >
              준비 마치고 1막 시작
            </button>
          </div>
        </section>
      )}

      {playset && <PlaysetTable playset={playset} highlight={value} />}
    </div>
  )
}
