// 3인 전체 플레이를 브라우저로 끝까지 돌려 보는 스모크 테스트.
//
//   node smoke.mjs            # 서버가 127.0.0.1:8000 에 떠 있어야 한다
//
// 여러 화면이 웹소켓으로 같은 상태를 보고 있어서, 무언가를 누른 직후에는
// 화면마다 반영 시점이 조금씩 다르다. 그 사이에 다음 행위자를 찾으면 방금
// 차례가 끝난 사람이 잘못 걸린다. 그래서 행동할 때마다 세 화면 모두에
// 반영된 것을 확인하고 나서 다음으로 넘어간다.
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8000'
const SHOTS = process.env.SHOT_DIR ?? './smoke-shots'
const CHROME = process.env.CHROME_PATH ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

fs.mkdirSync(SHOTS, { recursive: true })

const log = (...args) => console.log('•', ...args)
let shotIndex = 0
async function shot(page, name) {
  await page.screenshot({ path: `${SHOTS}/${String(++shotIndex).padStart(2, '0')}-${name}.png`, fullPage: true })
}

const browser = await chromium.launch({ executablePath: CHROME })
const errors = []
let pages = []

async function newPlayer(label) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } })
  const page = await context.newPage()
  page.on('pageerror', (e) => errors.push(`[${label}] pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[${label}] console: ${m.text()}`)
  })
  return page
}

/** 사이드바에는 주사위와 진행 기록이 모여 있어서 어떤 행동이든 여기 글이 바뀐다. */
const sidebar = (page) => page.locator('.layout__side').innerText()

/** 무언가를 누르고, 세 화면 전부에 반영될 때까지 기다린다. */
async function doAction(run) {
  const before = await Promise.all(pages.map(sidebar))
  await run()
  for (let i = 0; i < 200; i += 1) {
    const now = await Promise.all(pages.map(sidebar))
    if (now.every((text, index) => text !== before[index])) return
    await pages[0].waitForTimeout(80)
  }
  throw new Error('누른 결과가 모든 화면에 반영되지 않았습니다')
}

/** 그 선택자를 가진(=지금 행동할 수 있는) 화면을 찾는다. */
async function findActor(selector, timeout = 10000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    for (const page of pages) {
      if (await page.locator(selector).count()) return page
    }
    await pages[0].waitForTimeout(100)
  }
  throw new Error(`"${selector}" 를 누를 수 있는 화면이 없습니다.`)
}

try {
  // --- 방 만들기와 입장 ---------------------------------------------------
  const a = await newPlayer('가')
  await a.goto(BASE)
  await a.fill('input[placeholder="화면에 표시될 이름"]', '가')
  await shot(a, 'landing')
  await a.click('button:has-text("새 방 만들기")')
  await a.waitForSelector('.topbar__code')
  const code = (await a.textContent('.topbar__code')).trim()
  log('방 코드', code)

  const b = await newPlayer('나')
  const c = await newPlayer('다')
  for (const [page, name] of [
    [b, '나'],
    [c, '다'],
  ]) {
    await page.goto(`${BASE}/?room=${code}`)
    await page.fill('input[placeholder="화면에 표시될 이름"]', name)
    await page.click('button:has-text("입장")')
    await page.waitForSelector('.topbar__code')
  }
  pages = [a, b, c]
  await a.waitForSelector('text=참가자 3 / 5')
  log('3명 입장 완료')

  // --- 로비 ---------------------------------------------------------------
  await a.click('.option:has-text("예쁜 남부 마을")')
  await a.waitForSelector('text=선택됨')
  await shot(a, 'lobby')
  await a.click('button:has-text("준비 단계 시작")')
  for (const page of pages) await page.waitForSelector('text=중앙 주사위 12개')
  log('준비 단계 진입')
  await shot(a, 'setup')

  // --- 준비: 손으로 한 수 두고 되돌린 뒤, 간편 준비로 마무리 --------------
  const first = await findActor('.pool .die--button')
  await first.click('.pool .die--button >> nth=0')
  await first.waitForSelector('.option-list .option')
  log('첫 주사위로 가능한 선택지', await first.locator('.option-list .option').count(), '개')
  await doAction(() => first.click('.option-list .option >> nth=0'))
  await a.waitForSelector('text=중앙 주사위 11개')
  await doAction(() => a.click('button:has-text("되돌리기")'))
  await a.waitForSelector('text=중앙 주사위 12개')
  log('수동 준비 1수 → 되돌리기 확인')

  await doAction(() => a.click('button:has-text("간편 준비")'))
  await a.waitForSelector('text=주사위를 모두 썼습니다')
  for (const [page, name] of [
    [a, '엘리스'],
    [b, '보니'],
    [c, '칼'],
  ]) {
    await page.fill('input[placeholder="텐트카드에 적을 이름"]', name)
    await doAction(() => page.click('button:has-text("저장")'))
  }
  await a.waitForSelector('button:has-text("준비 마치고 1막 시작"):not([disabled])')
  await shot(a, 'setup-done')
  await doAction(() => a.click('button:has-text("준비 마치고 1막 시작")'))
  await a.waitForSelector('text=1막 · 1번째 장면')
  log('1막 시작')

  // --- 장면 --------------------------------------------------------------
  async function playScene(useEstablish) {
    const star = await findActor('.choice:not([disabled])')
    const others = pages.filter((page) => page !== star)
    await doAction(() => star.click(useEstablish ? '.choice:has-text("설정")' : '.choice:has-text("해결")'))

    // 설정이면 다른 사람들이, 해결이면 본인이 결말의 색을 고른다.
    const chooser = useEstablish ? others[0] : star
    await doAction(() => chooser.click('.color-button:not([disabled]) >> nth=0'))

    // 1막이면 결말 주사위를 반드시 남에게 넘겨야 한다.
    const handoff = star.locator('button:has-text("에게")')
    if (await handoff.count()) await doAction(() => handoff.first().click())

    await doAction(() => star.click('button:has-text("장면 마치고 다음으로")'))
  }

  async function playAct(label, endMarker, establishAt) {
    let scenes = 0
    while (!(await pages[0].locator(endMarker).count())) {
      await playScene(scenes === establishAt)
      if (++scenes > 12) throw new Error(`${label}이 끝나지 않습니다`)
    }
    log(`${label} 종료 —`, scenes, '장면')
    return scenes
  }

  const act1Scenes = await playAct('1막', 'h2:has-text("비틀기")', 1)
  if (act1Scenes !== 6) throw new Error(`1막은 6장면이어야 하는데 ${act1Scenes}장면`)
  await shot(a, 'twist')

  // --- 비틀기 -------------------------------------------------------------
  let picks = 0
  while (!(await pages[0].locator('text=2막 · 1번째 장면').count())) {
    const chooser = await findActor('button:has-text("참고용으로 굴리기")')
    await doAction(() => chooser.click('button:has-text("참고용으로 굴리기")'))
    await chooser.waitForSelector('text=굴린 값')
    await doAction(() => chooser.click('.playset-table .option:not([disabled]) >> nth=0'))
    if (++picks > 4) throw new Error('비틀기가 끝나지 않습니다')
  }
  log('2막 시작 — 비틀기 선택', picks, '회')
  await a.waitForSelector('text=비틀기 요소 — 누구나 쓸 수 있음')
  await shot(a, 'act2')

  const act2Scenes = await playAct('2막', 'h2:has-text("후기")', -1)
  if (act2Scenes !== 6) throw new Error(`2막은 6장면이어야 하는데 ${act2Scenes}장면`)

  // --- 후기 ---------------------------------------------------------------
  await shot(a, 'aftermath')
  let placed = 0
  while (!(await pages[0].locator('h2:has-text("파국")').count())) {
    const speaker = await findActor('button:has-text("내려놓기")')
    await speaker.fill('.textarea', '그리고 아무도 행복하지 않았다.')
    await doAction(() => speaker.click('button:has-text("내려놓기")'))
    if (++placed > 20) throw new Error('몽타주가 끝나지 않습니다')
  }
  if (placed !== 12) throw new Error(`몽타주는 12번이어야 하는데 ${placed}번`)
  log('게임 종료 — 몽타주', placed, '회')
  await shot(a, 'finished')

  // --- 새로고침으로 상태가 복구되는지 --------------------------------------
  await b.reload()
  await b.waitForSelector('h2:has-text("파국")')
  log('새로고침 후 상태 복구 확인')

  // --- 모바일 폭 -----------------------------------------------------------
  await a.setViewportSize({ width: 390, height: 844 })
  await a.waitForTimeout(300)
  const overflow = await a.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  if (overflow > 0) errors.push(`모바일에서 가로로 ${overflow}px 넘칩니다`)
  log('모바일(390px) 가로 넘침:', overflow, 'px')
  await shot(a, 'mobile')

  if (errors.length) {
    console.log('\n브라우저 오류:')
    errors.forEach((e) => console.log('  ', e))
    process.exitCode = 1
  } else {
    console.log('\n✅ 전체 플레이 통과, 브라우저 오류 없음')
  }
} catch (err) {
  console.error('\n❌ 실패:', err.message)
  errors.forEach((e) => console.log('  ', e))
  process.exitCode = 1
} finally {
  await browser.close()
}
