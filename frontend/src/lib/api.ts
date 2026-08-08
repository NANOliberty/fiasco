import type { Playset, PlaysetSummary, RulesSection, Session, TwistTableEntry } from '../types'

const SESSION_KEY = 'fiasco:session'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    let detail = `요청이 실패했습니다 (${response.status})`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* 본문이 JSON이 아니면 기본 메시지를 쓴다 */
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  createRoom: () => request<{ roomCode: string }>('/api/rooms', { method: 'POST' }),

  roomInfo: (code: string) =>
    request<{
      roomCode: string
      phase: string
      playerCount: number
      maxPlayers: number
      playsetId: string | null
      joinable: boolean
    }>(`/api/rooms/${encodeURIComponent(code)}`),

  join: (code: string, name: string) =>
    request<Session>(`/api/rooms/${encodeURIComponent(code)}/join`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  playsets: () => request<{ playsets: PlaysetSummary[] }>('/api/playsets').then((r) => r.playsets),

  playset: (id: string) => request<Playset>(`/api/playsets/${encodeURIComponent(id)}`),

  createPlayset: (playset: unknown) =>
    request<Playset>('/api/playsets', { method: 'POST', body: JSON.stringify({ playset }) }),

  reference: () => request<{ twistTable: TwistTableEntry[]; rules: RulesSection[] }>('/api/reference'),
}

// 세션은 방마다 따로 저장한다. 새로고침하거나 링크를 다시 열어도 자리를 지킨다.
type SessionStore = Record<string, Session>

function readStore(): SessionStore {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as SessionStore) : {}
  } catch {
    return {}
  }
}

function writeStore(store: SessionStore): void {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(store))
  } catch {
    /* 사생활 보호 모드 등으로 저장이 막혀도 게임은 계속 돌아간다 */
  }
}

export const sessionStore = {
  get(code: string): Session | null {
    return readStore()[code.toUpperCase()] ?? null
  },
  save(session: Session): void {
    const store = readStore()
    store[session.roomCode.toUpperCase()] = session
    writeStore(store)
  },
  clear(code: string): void {
    const store = readStore()
    delete store[code.toUpperCase()]
    writeStore(store)
  },
  latest(): Session | null {
    const values = Object.values(readStore())
    return values.length ? values[values.length - 1] : null
  },
}

export function roomLink(code: string): string {
  return `${window.location.origin}/?room=${code}`
}
