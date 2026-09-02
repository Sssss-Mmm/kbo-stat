// 시즌 상태 판정 (FR-12). 날짜 조건문은 이 파일에만 둔다.
// 판정 근거는 오늘 날짜(KST) + /api/schedule-games 응답뿐이다. 새 API를 만들지 않는다.

// 오늘 날짜를 KST 기준 'YYYY-MM-DD'로 (NFR-15: 브라우저 로컬 타임존을 믿지 않는다).
export function kstToday(now = new Date()) {
  return now.toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' })
}

// 'YYYY-MM-DD' 두 날짜의 일수 차이 (b - a).
function daysBetween(a, b) {
  const t = (s) => { const [y, m, d] = s.split('-').map(Number); return Date.UTC(y, m - 1, d) }
  return Math.round((t(b) - t(a)) / 86400000)
}

const LABEL = {
  regular: (s) => `${s} 정규시즌`,
  postseason: (s) => `${s} 정규시즌 최종`,
  offseason: (s) => `${s} 정규시즌 최종`,
}

/**
 * 시즌 상태를 판정한다.
 * @param today  'YYYY-MM-DD' (KST). 테스트를 위해 반드시 인자로 받는다.
 * @param games  /api/schedule-games 응답 배열 (Season/Date/status)
 * @returns {{state, season, dataSeason, label, notice, opening, closing, daysToOpening, isFallback, storyEnabled}}
 *   season     = 일정 데이터의 시즌(= 백엔드 활성 시즌)
 *   dataSeason = 순위·기록 화면이 보여줄 시즌(개막전이면 직전 시즌)
 */
export function seasonState(today, games = []) {
  const dates = games.map((g) => g.Date).filter(Boolean).sort()
  const month = Number(today.slice(5, 7))
  const todayYear = Number(today.slice(0, 4))

  // 일정 데이터가 아예 없을 때만 달력으로 판정한다(수집 실패·초기 상태).
  if (!dates.length) {
    const state = month >= 3 && month <= 9 ? 'regular' : month === 10 ? 'postseason' : 'offseason'
    return build(state, todayYear, todayYear, today, null, null, null, false)
  }

  const season = Number(games[0].Season) || Number(dates[0].slice(0, 4))
  const opening = dates[0]
  const closing = dates[dates.length - 1]
  // 잔여 경기: 미종료 + 오늘 이후. 과거 날짜의 취소 경기(status='scheduled' 69건)가
  // 섞여 있으므로 날짜 조건을 반드시 함께 건다 — 이게 없으면 오프시즌이 정규시즌으로 보인다.
  const remaining = games.filter((g) => g.status !== 'final' && g.Date >= today).length

  let state
  // preseason 은 '다음 시즌 일정이 공개됐고 개막일이 아직 미래'일 때만이다.
  // 1~2월에 활성 시즌 폴백(DR-06)으로 직전 시즌 일정만 오는 동안은 개막일을 알 수 없어
  // D-n 을 말할 수 없다 — 그건 offseason 으로 두고 폴백 사실만 notice 로 알린다.
  if (today < opening) state = 'preseason'
  else if (remaining > 0) state = 'regular'
  // ponytail: 정규시즌 종료 후 10월이면 포스트시즌, 그 외는 오프시즌.
  // 한국시리즈가 11월로 넘어가는 해는 이 경계를 넘길 수 있다 — 필요해지면 종료일 + n일로 바꾼다.
  else state = month === 10 ? 'postseason' : 'offseason'

  const dataSeason = state === 'preseason' ? season - 1 : season
  const isFallback = state !== 'preseason' && dataSeason < todayYear
  return build(state, season, dataSeason, today, opening, closing,
    state === 'preseason' ? daysBetween(today, opening) : null, isFallback)
}

function build(state, season, dataSeason, today, opening, closing, daysToOpening, isFallback) {
  const label = state === 'preseason'
    ? `${season} 시즌 개막 D-${daysToOpening}`
    : LABEL[state](dataSeason)

  const notes = []
  if (state === 'preseason') notes.push(`${dataSeason} 시즌 최종 기록을 표시합니다`)
  if (state === 'postseason') notes.push('포스트시즌 진행 중 · 표시 기록은 정규시즌 최종')
  if (state === 'offseason') notes.push('시즌 종료 · 정규시즌 최종 기록')
  // DR-06 AC2: 활성 시즌이 직전 시즌으로 폴백된 사실을 화면에 알린다.
  if (isFallback) notes.push(`${Number(today.slice(0, 4))}시즌 데이터가 없어 직전 시즌으로 표시합니다`)

  return {
    state, season, dataSeason, label,
    notice: notes.join(' · '),
    opening, closing, daysToOpening, isFallback,
    // FR-12 AC3: 오프시즌·개막전에는 AI 스토리를 아예 호출하지 않는다.
    storyEnabled: state === 'regular' || state === 'postseason',
  }
}

// --- 투구 데이터 시즌 커버리지 ------------------------------------------------
// 사용자가 실제로 고를 게 있는 도메인은 투구 데이터(존·구종·볼카운트)뿐이다.
// 없는 시즌을 고를 수 있게 두면 화면은 404 나 빈 표를 내놓는다 — 고를 수 없는 편이 정직하다.
// 나머지 화면(순위·일정·관중·기록)은 시즌이 하나뿐이고, 그 하나는 백엔드가 파일을
// 글롭해 판정한 값(seasonInfo.dataSeason)이다. 여기에 연도를 적으면 새 시즌에
// 백엔드만 따라가고 프런트는 멈춘다.
// 투구 데이터를 백필하면 여기를 고친다(내림차순 유지, 최신이 [0]).
export const ZONE_SEASONS = [2026, 2025]
