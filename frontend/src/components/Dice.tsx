import type { Die, DieColor } from '../types'

const SIZE_CLASS = { small: 'die--small', normal: '', large: 'die--large' } as const

export function DieView({
  die,
  size = 'normal',
  selected,
  onClick,
  title,
}: {
  die: Die
  size?: keyof typeof SIZE_CLASS
  selected?: boolean
  onClick?: () => void
  title?: string
}) {
  const label = `${die.color === 'black' ? '검은' : '흰'} 주사위 ${die.value}`
  const className = [
    'die',
    `die--${die.color}`,
    SIZE_CLASS[size],
    onClick ? 'die--button' : '',
    selected ? 'die--selected' : '',
  ]
    .filter(Boolean)
    .join(' ')

  if (!onClick) {
    return (
      <span className={className} title={title ?? label} aria-label={label} role="img">
        {die.value}
      </span>
    )
  }
  return (
    <button type="button" className={className} onClick={onClick} title={title ?? label} aria-pressed={selected}>
      {die.value}
      <span className="visually-hidden">{label}</span>
    </button>
  )
}

export function DiceRow({ dice, size = 'small', empty = '없음' }: { dice: Die[]; size?: keyof typeof SIZE_CLASS; empty?: string }) {
  if (!dice.length) return <div className="dice-row dice-row--empty">{empty}</div>
  return (
    <div className="dice-row">
      {dice.map((die) => (
        <DieView key={die.id} die={die} size={size} />
      ))}
    </div>
  )
}

export function ColorSwatch({ color }: { color: DieColor }) {
  return (
    <span className={`die die--${color} die--small`} aria-hidden="true" style={{ fontSize: 0 }}>
      ·
    </span>
  )
}

export function colorLabel(color: DieColor): string {
  return color === 'black' ? '검은색' : '흰색'
}

/** 흑/백 개수를 "검 3 · 흰 5" 식으로 짧게 요약한다. */
export function DiceSummary({ dice }: { dice: Die[] }) {
  const black = dice.filter((d) => d.color === 'black').length
  const white = dice.length - black
  return (
    <span className="tiny faint">
      검 {black} · 흰 {white}
    </span>
  )
}
