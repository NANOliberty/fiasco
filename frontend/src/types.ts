export type DieColor = 'black' | 'white'
export type Phase = 'lobby' | 'setup' | 'act1' | 'twist' | 'act2' | 'aftermath' | 'finished'
export type ListType = 'relationship' | 'desire' | 'object' | 'place'
export type DetailType = Exclude<ListType, 'relationship'>
export type SceneType = 'establish' | 'resolve'
export type SceneStatus = 'choosing' | 'playing' | 'handoff' | 'resolved'

export interface Die {
  id: string
  color: DieColor
  value: number
}

export interface Player {
  id: string
  name: string
  characterName: string
  seat: number
  connected: boolean
  dice: Die[]
  isHost: boolean
}

export interface Slot {
  id: string
  kind: 'relationship' | 'detail'
  listType: ListType
  pairIndex: number | null
  relationshipSlotId: string | null
  category: number
  categoryName: string
  element: number | null
  text: string | null
  claimedBy: string | null
  resolvedBy: string | null
  dice: Die[]
}

export interface Pair {
  index: number
  seatA: number
  seatB: number
  playerA: string
  playerB: string
}

export interface Scene {
  act: number
  number: number
  spotlightId: string
  type: SceneType | null
  notes: string
  status: SceneStatus
  handoffTo: string | null
  pendingDie?: Die
  award: {
    die: Die
    color: DieColor
    outcome: 'good' | 'bad'
    free: boolean
    chosenBy: string
  } | null
}

export interface Tally {
  black: number
  white: number
  value: number
  color: DieColor | null
}

export interface TwistPick {
  id: string
  chooserId: string
  category: number
  element: number
  categoryName: string
  text: string
}

export interface TwistState {
  tallies: Record<string, Tally>
  choosers: string[]
  picks: TwistPick[]
  reference: Record<string, number[]>
}

export interface AftermathOutcome {
  color: DieColor | null
  value: number
  range: string
  title: string
  text: string
}

export interface AftermathResult extends Tally {
  diceCount: number
  outcome: AftermathOutcome
}

export interface MontageEntry {
  id: string
  playerId: string
  text: string
  color: DieColor
  value: number
}

export interface AftermathState {
  results: Record<string, AftermathResult>
  order: string[]
  turnIdx: number
  entries: MontageEntry[]
}

export interface LogEntry {
  id: string
  ts: number
  kind: string
  text: string
  playerId: string | null
  phase: Phase
}

export interface GameOptions {
  dicePerPlayer: number
  blackRatio: number
  freeLastSetupDie: boolean
  accelerator: boolean
  goodBadDice: boolean
}

export interface SetupValidation {
  errors: string[]
  warnings: string[]
  canFinish: boolean
}

export interface Derived {
  pairs: Pair[]
  turnOrder: number[]
  centralCount: number
  centralByColor: { black: number; white: number }
  halfway: number
  currentPlayerId: string | null
  setupValidation?: SetupValidation
  setupDiceRequired?: number
}

export interface GameState {
  roomCode: string
  phase: Phase
  hostId: string | null
  options: GameOptions
  playsetId: string | null
  players: Player[]
  startingSeat: number
  turnSeat: number
  central: Die[]
  totalDice: number
  act: number
  setup: { slots: Slot[]; history: unknown[] } | null
  scene: Scene | null
  twist: TwistState | null
  twistDetails: { id: string; categoryName: string; text: string; chosenBy: string }[]
  aftermath: AftermathState | null
  log: LogEntry[]
  derived: Derived
}

export interface PlaysetElement {
  number: number
  text: string
}

export interface PlaysetCategory {
  number: number
  name: string
  elements: PlaysetElement[]
}

export interface Playset {
  id: string
  name: string
  custom: boolean
  lists: Record<ListType, PlaysetCategory[]>
  quickSetup: Record<string, unknown>
}

export interface PlaysetSummary {
  id: string
  name: string
  custom: boolean
  hasQuickSetup: boolean
}

export interface TwistTableEntry {
  category: string
  elements: string[]
}

export interface RulesSection {
  title: string
  lines: string[]
}

export interface Session {
  roomCode: string
  playerId: string
  token: string
}

export const LIST_LABELS: Record<ListType, string> = {
  relationship: '관계',
  desire: '욕망',
  object: '물건',
  place: '장소',
}

export const DETAIL_TYPES: DetailType[] = ['desire', 'object', 'place']

export const PHASE_LABELS: Record<Phase, string> = {
  lobby: '로비',
  setup: '준비',
  act1: '1막',
  twist: '비틀기',
  act2: '2막',
  aftermath: '후기',
  finished: '종료',
}

export const PHASE_ORDER: Phase[] = ['setup', 'act1', 'twist', 'act2', 'aftermath']
