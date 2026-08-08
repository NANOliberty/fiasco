import { useEffect, useState } from 'react'
import { DieView, colorLabel } from '../components/Dice'
import { RelationshipBoard } from '../components/PlaysetTable'
import { useGame, playersInTurnOrder } from '../lib/store'
import type { DieColor } from '../types'

function SceneNotes() {
  const { state, me, send } = useGame()
  const scene = state.scene!
  const [draft, setDraft] = useState(scene.notes)
  const canEdit = me?.id === scene.spotlightId || me?.id === state.hostId

  // 다른 사람이 메모를 고치면 내 화면에도 반영한다(내가 편집 중이 아닐 때만).
  useEffect(() => {
    setDraft(scene.notes)
  }, [scene.notes, scene.number, scene.act])

  if (!canEdit) {
    return scene.notes ? (
      <div className="stack stack--tight">
        <span className="entry__label">장면 메모</span>
        <p className="muted small" style={{ whiteSpace: 'pre-wrap' }}>
          {scene.notes}
        </p>
      </div>
    ) : null
  }

  return (
    <label className="stack stack--tight">
      <span className="entry__label">장면 메모 — 앱은 내용에 관여하지 않습니다</span>
      <textarea
        className="textarea"
        value={draft}
        placeholder="어디서, 누가, 무엇 때문에…"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => draft !== scene.notes && send('scene_set_notes', { notes: draft })}
      />
    </label>
  )
}

function ColorButtons({ onPick, disabled }: { onPick: (color: DieColor) => void; disabled?: boolean }) {
  const { state } = useGame()
  const available = (color: DieColor) => state.central.some((d) => d.color === color)
  return (
    <div className="color-buttons">
      {(['white', 'black'] as DieColor[]).map((color) => (
        <button
          key={color}
          type="button"
          className="color-button"
          onClick={() => onPick(color)}
          disabled={disabled || !available(color)}
        >
          <span className={`die die--${color}`} aria-hidden="true">
            ?
          </span>
          <span>
            {colorLabel(color)}
            <br />
            <span className="tiny faint">{color === 'white' ? '좋은 결말' : '나쁜 결말'}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

export function SceneScreen() {
  const { state, me, isHost, send, nameOf } = useGame()
  const scene = state.scene
  if (!scene) {
    return (
      <div className="layout__main">
        <section className="card">
          <p className="muted">다음 장면을 준비하는 중입니다…</p>
        </section>
      </div>
    )
  }

  const amSpotlight = me?.id === scene.spotlightId
  const spotlightName = nameOf(scene.spotlightId)
  const isAct1 = state.act === 1
  const lastDieAwarded = state.act === 2 && !state.central.length && !!scene.award

  return (
    <div className="layout__main">
      <section className="spotlight">
        <div className="entry__label">
          {scene.act}막 · {scene.number}번째 장면
        </div>
        <div className="spotlight__who">{spotlightName}</div>
        <div className="small muted">
          {amSpotlight ? '조명이 나에게 있습니다' : `${spotlightName} 님에게 조명이 있습니다`}
        </div>
      </section>

      <section className="card stack">
        {scene.status === 'choosing' && (
          <>
            <h3 className="card__title">설정할까요, 해결할까요? — 하나만 고릅니다</h3>
            <div className="choice-grid">
              <button
                type="button"
                className="choice"
                disabled={!amSpotlight}
                onClick={() => send('scene_choose_type', { sceneType: 'establish' })}
              >
                <div className="choice__title">설정</div>
                <div className="small muted">
                  내가 장면을 연다. 장소·등장인물·갈등을 정하고, 결말의 색은 <strong>다른 사람들</strong>이 정해 준다.
                </div>
              </button>
              <button
                type="button"
                className="choice"
                disabled={!amSpotlight}
                onClick={() => send('scene_choose_type', { sceneType: 'resolve' })}
              >
                <div className="choice__title">해결</div>
                <div className="small muted">
                  다른 사람들이 장면을 연다. 결말의 색은 <strong>내가</strong> 중앙에서 직접 고른다.
                </div>
              </button>
            </div>
            {!amSpotlight && <p className="tiny faint">{spotlightName} 님이 고르는 중입니다.</p>}
          </>
        )}

        {scene.status === 'playing' && (
          <>
            <div className="row row--between">
              <span className="pill pill--accent">{scene.type === 'establish' ? '설정' : '해결'}</span>
              {state.central.length === 1 && state.act === 2 && (
                <span className="pill">마지막 주사위</span>
              )}
            </div>
            <SceneNotes />

            {scene.type === 'resolve' ? (
              amSpotlight ? (
                <div className="stack stack--tight">
                  <span className="entry__label">장면이 끝나면 중앙에서 색을 골라 가져오세요</span>
                  <ColorButtons onPick={(color) => send('scene_award_die', { color })} />
                </div>
              ) : (
                <p className="notice">
                  다른 사람들이 장면을 만들어 주세요. 결말의 색은 {spotlightName} 님이 직접 고릅니다.
                </p>
              )
            ) : amSpotlight ? (
              <p className="notice">
                장면을 열어 주세요. 결말의 색은 다른 사람들이 상의해서 정합니다.
              </p>
            ) : (
              <div className="stack stack--tight">
                <span className="entry__label">
                  다 같이 상의해서 {spotlightName} 님의 결말을 정하세요 (한 명이 대표로 누르면 됩니다)
                </span>
                <ColorButtons onPick={(color) => send('scene_award_die', { color })} />
              </div>
            )}
          </>
        )}

        {(scene.status === 'handoff' || scene.status === 'resolved') && scene.award && (
          <>
            <div className="row">
              <DieView die={scene.award.die} size="large" />
              <div>
                <div style={{ fontWeight: 650 }}>
                  {colorLabel(scene.award.color)} — {scene.award.outcome === 'good' ? '좋은 결말' : '나쁜 결말'}
                  {scene.award.free && <span className="pill pill--accent tiny" style={{ marginLeft: '0.4rem' }}>임의 지정</span>}
                </div>
                <div className="small muted">{spotlightName} 님의 장면이 이렇게 끝났습니다.</div>
              </div>
            </div>

            <SceneNotes />

            {lastDieAwarded && amSpotlight && (
              <div className="stack stack--tight">
                <span className="entry__label">
                  마지막 주사위 — 색과 상관없이 결과를 정할 수 있습니다 (후기 계산에는 실제 색이 그대로 쓰입니다)
                </span>
                <div className="row">
                  <button
                    type="button"
                    className={`btn ${scene.award.outcome === 'good' ? 'btn--primary' : ''}`}
                    onClick={() => send('scene_set_free_outcome', { outcome: 'good' })}
                  >
                    좋은 결말로
                  </button>
                  <button
                    type="button"
                    className={`btn ${scene.award.outcome === 'bad' ? 'btn--primary' : ''}`}
                    onClick={() => send('scene_set_free_outcome', { outcome: 'bad' })}
                  >
                    나쁜 결말로
                  </button>
                </div>
              </div>
            )}

            {scene.status === 'handoff' ? (
              <div className="stack stack--tight">
                <span className="entry__label">
                  1막입니다 — 이 주사위는 반드시 다른 사람에게 넘겨야 합니다
                </span>
                {amSpotlight ? (
                  <div className="row">
                    {playersInTurnOrder(state)
                      .filter((player) => player.id !== scene.spotlightId)
                      .map((player) => (
                        <button
                          key={player.id}
                          type="button"
                          className="btn"
                          onClick={() => send('scene_hand_off', { targetPlayerId: player.id })}
                        >
                          {nameOf(player.id)} 에게
                        </button>
                      ))}
                  </div>
                ) : (
                  <p className="muted small">{spotlightName} 님이 누구에게 넘길지 고르는 중입니다.</p>
                )}
              </div>
            ) : (
              <div className="row">
                {isAct1 && scene.handoffTo && (
                  <span className="pill">→ {nameOf(scene.handoffTo)} 님에게 넘김</span>
                )}
                <div className="spacer" />
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => send('scene_end')}
                  disabled={!amSpotlight && !isHost}
                >
                  장면 마치고 다음으로
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {isHost && state.options.accelerator && state.act === 2 && (
        <button type="button" className="btn btn--small" onClick={() => send('host_end_act2')}>
          액셀 밟기 — 2막을 끝내고 남은 주사위를 후기용으로 나누기
        </button>
      )}

      {/* 장면을 즉흥으로 만들려면 관계와 세부사항이 늘 눈에 보여야 한다 */}
      <details className="card" open>
        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>관계와 세부사항</summary>
        <div style={{ marginTop: '0.8rem' }}>
          <RelationshipBoard />
        </div>
      </details>
    </div>
  )
}
