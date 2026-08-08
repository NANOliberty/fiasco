import { useState, type ChangeEvent } from 'react'
import { api } from '../lib/api'
import { LIST_LABELS, type ListType, type Playset } from '../types'

const LIST_ORDER: ListType[] = ['relationship', 'desire', 'object', 'place']
const JSON_KEYS: Record<ListType, string> = {
  relationship: 'relationships',
  desire: 'desires',
  object: 'objects',
  place: 'places',
}

interface DraftCategory {
  name: string
  elements: string
}

function emptyCategories(): DraftCategory[] {
  return Array.from({ length: 6 }, () => ({ name: '', elements: '' }))
}

function emptyDraft(): Record<ListType, DraftCategory[]> {
  return {
    relationship: emptyCategories(),
    desire: emptyCategories(),
    object: emptyCategories(),
    place: emptyCategories(),
  }
}

function toPayload(name: string, draft: Record<ListType, DraftCategory[]>) {
  const payload: Record<string, unknown> = { name: name.trim() }
  for (const list of LIST_ORDER) {
    const table: Record<string, string[]> = {}
    draft[list].forEach((category, index) => {
      const categoryName = category.name.trim() || `${LIST_LABELS[list]}${index + 1}`
      const elements = category.elements
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      table[categoryName] = elements
    })
    payload[JSON_KEYS[list]] = table
  }
  return payload
}

/** 분류 6개 × 요소 6개가 다 찼는지 훑어보고 부족한 곳을 알려 준다. */
function findGaps(draft: Record<ListType, DraftCategory[]>): string[] {
  const gaps: string[] = []
  for (const list of LIST_ORDER) {
    draft[list].forEach((category, index) => {
      const lines = category.elements.split('\n').map((line) => line.trim()).filter(Boolean)
      if (lines.length !== 6) {
        gaps.push(`${LIST_LABELS[list]} ${index + 1}번 분류: 요소가 ${lines.length}개 (6개 필요)`)
      }
    })
    const names = new Set(draft[list].map((c, i) => c.name.trim() || `#${i}`))
    if (names.size !== 6) gaps.push(`${LIST_LABELS[list]}: 분류 이름이 겹칩니다`)
  }
  return gaps
}

export function PlaysetEditor({ onCreated }: { onCreated: (playset: Playset) => void }) {
  const [mode, setMode] = useState<'form' | 'json'>('form')
  const [name, setName] = useState('')
  const [draft, setDraft] = useState(emptyDraft)
  const [tab, setTab] = useState<ListType>('relationship')
  const [json, setJson] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const gaps = findGaps(draft)

  const update = (list: ListType, index: number, patch: Partial<DraftCategory>) => {
    setDraft((prev) => {
      const next = { ...prev, [list]: [...prev[list]] }
      next[list][index] = { ...next[list][index], ...patch }
      return next
    })
  }

  const submit = async (payload: unknown) => {
    setBusy(true)
    setError(null)
    try {
      const created = await api.createPlayset(payload)
      onCreated(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : '플레이세트를 만들지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const submitForm = () => {
    if (!name.trim()) {
      setError('플레이세트 이름을 입력하세요.')
      return
    }
    if (gaps.length) {
      setError(gaps[0])
      return
    }
    void submit(toPayload(name, draft))
  }

  const submitJson = () => {
    try {
      void submit(JSON.parse(json))
    } catch {
      setError('JSON 형식이 올바르지 않습니다.')
    }
  }

  const loadFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    file
      .text()
      .then((text) => {
        setJson(text)
        setMode('json')
      })
      .catch(() => setError('파일을 읽지 못했습니다.'))
  }

  return (
    <div className="card stack" style={{ background: 'var(--bg-sunken)' }}>
      <div className="table-tabs">
        <button
          type="button"
          className={`table-tab ${mode === 'form' ? 'table-tab--active' : ''}`}
          onClick={() => setMode('form')}
        >
          표 채우기
        </button>
        <button
          type="button"
          className={`table-tab ${mode === 'json' ? 'table-tab--active' : ''}`}
          onClick={() => setMode('json')}
        >
          JSON 불러오기
        </button>
      </div>

      {mode === 'form' ? (
        <>
          <label className="stack stack--tight">
            <span className="entry__label">플레이세트 이름</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="우리 동네 이야기" />
          </label>

          <div className="table-tabs">
            {LIST_ORDER.map((list) => (
              <button
                key={list}
                type="button"
                className={`table-tab ${tab === list ? 'table-tab--active' : ''}`}
                onClick={() => setTab(list)}
              >
                {LIST_LABELS[list]}
              </button>
            ))}
          </div>

          <p className="tiny faint">
            분류 6개, 분류마다 요소 6개가 필요합니다. 요소는 한 줄에 하나씩 적으세요. 주사위 눈 1~6이 곧 그 순서입니다.
          </p>

          <div className="stack">
            {draft[tab].map((category, index) => (
              <div key={index} className="stack stack--tight">
                <div className="row">
                  <span className="pill">{index + 1}</span>
                  <input
                    className="input"
                    style={{ flex: 1 }}
                    value={category.name}
                    onChange={(e) => update(tab, index, { name: e.target.value })}
                    placeholder={`${LIST_LABELS[tab]} 분류 이름`}
                  />
                </div>
                <textarea
                  className="textarea"
                  rows={6}
                  value={category.elements}
                  onChange={(e) => update(tab, index, { elements: e.target.value })}
                  placeholder={'요소 1\n요소 2\n요소 3\n요소 4\n요소 5\n요소 6'}
                />
              </div>
            ))}
          </div>

          {gaps.length > 0 && (
            <div className="notice">
              아직 {gaps.length}곳이 비었습니다.
              <br />
              <span className="tiny">{gaps[0]}</span>
            </div>
          )}

          <button type="button" className="btn btn--primary" onClick={submitForm} disabled={busy}>
            플레이세트 만들기
          </button>
        </>
      ) : (
        <>
          <p className="tiny faint">
            {'{ name, relationships, desires, objects, places }'} 형태의 JSON. 각 목록은 분류 6개, 분류마다 요소 6개입니다.
          </p>
          <input type="file" accept="application/json,.json" onChange={loadFile} />
          <textarea
            className="textarea"
            rows={10}
            value={json}
            onChange={(e) => setJson(e.target.value)}
            placeholder='{"name": "우리 동네", "relationships": {...}, "desires": {...}, "objects": {...}, "places": {...}}'
          />
          <button type="button" className="btn btn--primary" onClick={submitJson} disabled={busy || !json.trim()}>
            불러와서 만들기
          </button>
        </>
      )}

      {error && <div className="notice notice--danger">{error}</div>}
    </div>
  )
}
