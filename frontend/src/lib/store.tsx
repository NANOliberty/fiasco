import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from './api'
import type { Connection } from './connection'
import type { GameState, Player, Playset, RulesSection, Slot, TwistTableEntry } from '../types'

interface GameContextValue extends Connection {
  state: GameState
  me: Player | null
  isHost: boolean
  isMyTurn: boolean
  playset: Playset | null
  playsetLoading: boolean
  twistTable: TwistTableEntry[]
  rules: RulesSection[]
  playerById: (id: string | null | undefined) => Player | null
  nameOf: (id: string | null | undefined) => string
}

const GameContext = createContext<GameContextValue | null>(null)

export function GameProvider({
  connection,
  state,
  children,
}: {
  connection: Connection
  state: GameState
  children: ReactNode
}) {
  const playset = usePlayset(state.playsetId)
  const reference = useReference()

  const value = useMemo<GameContextValue>(() => {
    const me = state.players.find((p) => p.id === connection.you) ?? null
    const playerById = (id: string | null | undefined) =>
      id ? (state.players.find((p) => p.id === id) ?? null) : null
    return {
      ...connection,
      state,
      me,
      isHost: !!me && me.id === state.hostId,
      isMyTurn: !!me && state.derived.currentPlayerId === me.id,
      playset: playset.data,
      playsetLoading: playset.loading,
      twistTable: reference.twistTable,
      rules: reference.rules,
      playerById,
      nameOf: (id) => {
        const player = playerById(id)
        if (!player) return '???'
        return player.characterName || player.name
      },
    }
  }, [connection, state, playset.data, playset.loading, reference])

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>
}

export function useGame(): GameContextValue {
  const value = useContext(GameContext)
  if (!value) throw new Error('useGame 은 GameProvider 안에서만 쓸 수 있습니다.')
  return value
}

/** 플레이세트 표는 한 번만 받아 두고 재사용한다. 상태 브로드캐스트에는 싣지 않는다. */
const playsetCache = new Map<string, Playset>()

export function usePlayset(id: string | null): { data: Playset | null; loading: boolean } {
  const [data, setData] = useState<Playset | null>(() => (id ? (playsetCache.get(id) ?? null) : null))
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!id) {
      setData(null)
      return
    }
    const cached = playsetCache.get(id)
    if (cached) {
      setData(cached)
      return
    }
    let cancelled = false
    setLoading(true)
    api
      .playset(id)
      .then((playset) => {
        playsetCache.set(id, playset)
        if (!cancelled) setData(playset)
      })
      .catch(() => {
        if (!cancelled) setData(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  return { data, loading }
}

let referenceCache: { twistTable: TwistTableEntry[]; rules: RulesSection[] } | null = null

export function useReference() {
  const [data, setData] = useState(referenceCache ?? { twistTable: [], rules: [] })
  useEffect(() => {
    if (referenceCache) return
    api
      .reference()
      .then((result) => {
        referenceCache = result
        setData(result)
      })
      .catch(() => undefined)
  }, [])
  return data
}

// --- 상태에서 자주 뽑아 쓰는 것들 ------------------------------------------

export function relationshipSlots(state: GameState): Slot[] {
  return (state.setup?.slots ?? []).filter((s) => s.kind === 'relationship')
}

export function detailSlots(state: GameState): Slot[] {
  return (state.setup?.slots ?? []).filter((s) => s.kind === 'detail')
}

export function detailsOf(state: GameState, relationshipSlotId: string): Slot[] {
  return detailSlots(state).filter((s) => s.relationshipSlotId === relationshipSlotId)
}

export function playersInTurnOrder(state: GameState): Player[] {
  return state.derived.turnOrder
    .map((seat) => state.players.find((p) => p.seat === seat))
    .filter((p): p is Player => !!p)
}
