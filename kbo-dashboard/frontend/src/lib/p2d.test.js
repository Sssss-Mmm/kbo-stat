import assert from 'node:assert/strict'
import {
  betterSide, commonSeasons, gameLine, leaguePool, percentile, playerLabel, recordPct, recordText, seasonLine, seasonSpan,
  toNumber, verificationSummary, latestCollected, fmtAdvanced, comparableAdvanced, advancedPool, advancedPercentile,
  advancedOf, COMPARE_METRICS, MIN_ADVANCED_POOL, qualifiedSimpleMean,
  CHART_METRICS, chartMetrics, metricPercentile, compareWinner, chartRowLabel, missingReasons,
} from './p2d.js'

// 숫자: 이닝 '180 2/3' 은 1/3 단위, 없는 값은 null(0 이 아님)
assert.equal(toNumber('180 2/3'), 180 + 2 / 3)
assert.equal(toNumber('161'), 161)
assert.equal(toNumber('0.312'), 0.312)
assert.equal(toNumber(null), null)
assert.equal(toNumber(''), null)
assert.equal(toNumber('-'), null)

// 리그 모집단: 규정 충족 + 값 있는 선수만
const league = [{ 규정충족: true, OPS: 0.9 }, { 규정충족: true, OPS: 0.7 }, { 규정충족: false, OPS: 1.5 },
  { 규정충족: true, OPS: null }, { 규정충족: true, OPS: 0.8 }]
const pool = leaguePool(league, 'OPS')
assert.deepEqual(pool, [0.9, 0.7, 0.8])
assert.equal(percentile(pool, 0.9), 100)
assert.equal(percentile(pool, 0.7), 33)
assert.equal(percentile(pool, null), null)       // 미확정 값은 백분위 없음
assert.equal(percentile([], 0.9), null)          // 모집단 없음
// 낮을수록 좋은 지표(ERA)
assert.equal(percentile([2.0, 3.0, 4.0], 2.0, 'low'), 100)
assert.equal(percentile([2.0, 3.0, 4.0], 4.0, 'low'), 33)

assert.equal(betterSide(0.9, 0.8), 'a')
assert.equal(betterSide(2.5, 3.1, 'low'), 'a')
assert.equal(betterSide(3.1, 3.1, 'low'), 'tie')
assert.equal(betterSide(null, 3.1), null)

const prof = (lines) => ({ data: { seasons: lines } })
const a = prof([{ season: 2026, role: 'batter' }, { season: 2025, role: 'batter' }, { season: 2024, role: 'pitcher' }])
const b = prof([{ season: 2025, role: 'batter' }, { season: 2024, role: 'batter' }, { season: 2026, role: 'pitcher' }])
assert.deepEqual(commonSeasons(a, b, 'batter'), [2025])
assert.equal(seasonLine(a, 2024, 'pitcher').role, 'pitcher')
assert.equal(seasonLine(a, 2024, 'batter'), null)

// 동명이인 구분: 모르는 칸(생년월일)은 빼고 추측하지 않는다
assert.equal(playerLabel({ name: '홍길동', birth_date: '1990-01-01', seasons: [{ team: 'NC', position: '외야수' }] }),
  '홍길동 · NC 외야수 · 1990-01-01생')
assert.equal(playerLabel({ name: '홍길동', birth_date: null, seasons: [{ team: 'KIA', position: null }] }), '홍길동 · KIA')
assert.equal(seasonSpan([{ season: 2026 }, { season: 2009 }, { season: 2025 }]), '2009–2026 (3시즌)')
assert.equal(seasonSpan([{ season: 2025 }, { season: 2025 }]), '2025 (1시즌)')

assert.equal(recordText('41-1-29'), '41승 1무 29패')
assert.equal(recordText(null), null)
assert.equal(recordPct('41-1-29').toFixed(3), '0.586')
assert.equal(recordPct('0-2-0'), null)

assert.deepEqual(gameLine({ side: 'away', result: 'W', opponent: '두산', home: { score: 1 }, away: { score: 3 } }),
  { result: '승', score: '3:1', opponent: '두산', where: '원정' })

// 검증 요약: 한 경기라도 어긋나면 불일치, 대조 불가 상태는 따로
const body = { data: { roles: { pitcher: {
  verification: { SO: { observed_naver_match: 29 }, BB: { naver_verified: 2, observed_naver_match: 27 },
    H: { observed_naver_match: 28, naver_conflict: 1 }, Outs: { calc_missing: 3 } },
  kbo: { status: 'not_checked' } } } } }
assert.deepEqual(verificationSummary(body, 'pitcher'), { items: 4, agree: 2, conflict: 1, other: 1, kbo: 'not_checked' })
assert.equal(verificationSummary(body, 'batter'), null)
assert.equal(verificationSummary(null, 'pitcher'), null)

assert.equal(latestCollected([{ collected_at: '2026-09-13T00:00:00+00:00' }, {}, { collected_at: '2026-10-22T00:00:00+00:00' }]),
  '2026-10-22T00:00:00+00:00')
assert.equal(latestCollected([]), null)

// ---- P3-A 고급 지표 표시: 계산 불가·분모 0 은 '-'(0.000·0.0% 가 아님), 출처 값은 계산값과 다른 종류
const calc = (value, display = value) => ({ status: 'calculated', value, display, reason: null })
assert.deepEqual(fmtAdvanced('iso', calc(0.21428, 0.214)), { text: '.214', kind: 'calculated', note: '계산값' })
assert.equal(fmtAdvanced('bb_pct', calc(10.5263, 10.5)).text, '10.5%')
assert.equal(fmtAdvanced('k_pct', calc(0.25, 0.3)).text, '0.3%')       // 표시값(서버 ROUND_HALF_UP)을 쓴다
assert.equal(fmtAdvanced('babip', calc(1, 1)).text, '1.000')
const src = fmtAdvanced('babip_source', { status: 'source', value: 0.341, display: 0.341 })
assert.equal(src.kind, 'source'); assert.equal(src.text, '.341'); assert.match(src.note, /직접 계산 아님/)
const na = fmtAdvanced('babip', { status: 'unavailable', value: null, display: null, reason: 'SF 자료 없음' })
assert.deepEqual(na, { text: '-', kind: 'unavailable', note: 'SF 자료 없음' })
const zero = fmtAdvanced('iso', { status: 'zero_denominator', value: null, display: null, reason: '분모 0' })
assert.equal(zero.text, '-'); assert.equal(zero.kind, 'zero_denominator')
assert.equal(fmtAdvanced('iso', undefined).kind, 'missing')       // 고급 지표가 없는 시즌·옛 응답
for (const m of [na, zero]) assert.ok(!/0\.0/.test(m.text))

// 직접 비교: 같은 시즌·같은 상태만
const s = (status, value) => ({ status, value })
assert.equal(comparableAdvanced(s('calculated', 0.3), s('calculated', 0.2), 2025, 2025), true)
assert.equal(comparableAdvanced(s('calculated', 0.3), s('source', 0.2), 2025, 2025), false)   // 계산값 vs 출처 값
assert.equal(comparableAdvanced(s('calculated', 0.3), s('calculated', 0.2), 2025, 2024), false) // 다른 시즌
assert.equal(comparableAdvanced(s('unavailable', null), s('calculated', 0.2), 2025, 2025), false)

// 백분위 모집단: 같은 상태만, 최소 인원 미만이면 null
const rows = (n, status, key = 'iso') => Array.from({ length: n }, (_, i) => ({ metrics: { [key]: s(status, i / 100) } }))
assert.equal(advancedPool([...rows(3, 'calculated'), ...rows(2, 'source')], 'iso', 'source').length, 2)
assert.equal(advancedPercentile(rows(MIN_ADVANCED_POOL - 1, 'calculated'), 'iso', s('calculated', 0.1), 'high'), null)
assert.equal(typeof advancedPercentile(rows(MIN_ADVANCED_POOL, 'calculated'), 'iso', s('calculated', 0.1), 'high'), 'number')
assert.equal(advancedPercentile(rows(50, 'source'), 'iso', s('calculated', 0.1), 'high'), null)   // 다른 상태 모집단은 안 쓴다
assert.equal(advancedPercentile(rows(50, 'calculated'), 'iso', s('unavailable', null), 'high'), null)
assert.deepEqual(advancedOf({ advanced: { metrics: { iso: s('calculated', 0.2) } } }, 'iso'), s('calculated', 0.2))
assert.equal(advancedOf({ stats: {} }, 'iso'), undefined)
// 비교 지표: ISO 는 출처 열이 아니라 자체 계산(adv)
const iso = COMPARE_METRICS.batter.find((m) => m.label === 'ISO')
assert.equal(iso.adv, 'iso')
assert.deepEqual(COMPARE_METRICS.batter.filter((m) => m.adv).map((m) => m.adv), ['iso', 'babip', 'babip_source', 'bb_pct', 'k_pct'])

// 홈 '선수 BABIP 단순 평균': 규정 충족만, 결측 제외, 선수별 값의 평균(가중 아님)
const hitters = [{ 규정충족: true, BABIP: 0.3 }, { 규정충족: true, BABIP: 0.4 }, { 규정충족: false, BABIP: 0.9 },
  { 규정충족: true, BABIP: null }, { 규정충족: true }]
assert.ok(Math.abs(qualifiedSimpleMean(hitters, 'BABIP') - 0.35) < 1e-12)
assert.ok(Number.isNaN(qualifiedSimpleMean([{ 규정충족: false, BABIP: 0.3 }], 'BABIP')))
assert.ok(Number.isNaN(qualifiedSimpleMean([], 'BABIP')))
assert.ok(Math.abs(qualifiedSimpleMean([{ 규정충족: true, BABIP: 0.2, PA: 600 }, { 규정충족: true, BABIP: 0.4, PA: 10 }], 'BABIP') - 0.3) < 1e-12)  // 타석 가중이 아님

// ---- 선수 비교 양방향 막대
// 차트 지표: 승인된 7개·5개, 모두 COMPARE_METRICS 의 실제 키(순서도 그대로). 누적 지표·WAR 는 빠진다.
assert.deepEqual(chartMetrics('batter').map((m) => m.key), ['AVG', 'OBP', 'SLG', 'wRC+', 'iso', 'bb_pct', 'k_pct'])
assert.deepEqual(chartMetrics('pitcher').map((m) => m.key), ['ERA', 'WHIP', 'K/9', 'BB/9', 'K/BB'])
for (const role of ['batter', 'pitcher']) assert.equal(chartMetrics(role).length, CHART_METRICS[role].length)
assert.ok(!chartMetrics('batter').some((m) => ['WAR', 'HR', 'SB'].includes(m.key)))
assert.ok(!chartMetrics('pitcher').some((m) => ['WAR', 'IP', 'SO', 'QS'].includes(m.key)))

const M = (key, role = 'batter') => COMPARE_METRICS[role].find((m) => m.key === key)
const lg = [{ 규정충족: true, ERA: 2.5, AVG: 0.3 }, { 규정충족: true, ERA: 3.5, AVG: 0.28 }, { 규정충족: true, ERA: 4.5, AVG: 0.25 },
  { 규정충족: false, ERA: 9.0, AVG: 0.1 }]
// 수치표와 같은 계산: percentile(leaguePool) 결과·n 이 그대로
const avg = metricPercentile(M('AVG'), { stats: { AVG: 0.28 } }, lg, [])
assert.deepEqual(avg, { pct: percentile(leaguePool(lg, 'AVG'), 0.28, 'high'), n: 3, reason: null, short: null, text: '.280' })
// 낮을수록 좋은 지표(ERA): 낮은 값이 높은 백분위, n 은 규정 충족 3명
const era = metricPercentile(M('ERA', 'pitcher'), { stats: { ERA: 2.5 } }, lg, [])
assert.equal(era.pct, 100)
assert.equal(era.n, 3)
assert.equal(era.text, '2.50')
assert.equal(metricPercentile(M('ERA', 'pitcher'), { stats: { ERA: 4.5 } }, lg, []).pct, 33)
// 백분위 null: 0 이 아니라 null + 사유
const none = metricPercentile(M('AVG'), { stats: { AVG: null } }, lg, [])
assert.equal(none.pct, null)
assert.equal(none.reason, '기록 없음')
assert.equal(none.short, '데이터 없음')
assert.equal(none.text, '-')
const noPool = metricPercentile(M('AVG'), { stats: { AVG: 0.3 } }, [{ 규정충족: false, AVG: 0.3 }], [])  // 2007: 규정 충족 0명
assert.deepEqual([noPool.pct, noPool.n, noPool.reason, noPool.short], [null, 0, '그 시즌 규정 충족 선수가 없어 백분위 없음', '비교 불가'])
// 규정 미달 선수도 같은 규정 충족 모집단 기준(계산 그대로) — 화면은 빗금으로 '참고값' 표시
assert.equal(metricPercentile(M('AVG'), { qualified: false, stats: { AVG: 0.35 } }, lg, []).pct, 100)

// 고급 지표: advancedPercentile 그대로, n = 같은 상태 모집단 수, 20명 미만이면 null + 사유
const isoM = M('iso')
const advLine = (status, value) => ({ advanced: { metrics: { iso: s(status, value) } } })
const big = metricPercentile(isoM, advLine('calculated', 0.1), [], rows(30, 'calculated'))
assert.equal(big.pct, advancedPercentile(rows(30, 'calculated'), 'iso', s('calculated', 0.1), 'high'))
assert.equal(big.n, 30)
assert.equal(big.text, '.100')
const small = metricPercentile(isoM, advLine('calculated', 0.1), [], rows(MIN_ADVANCED_POOL - 1, 'calculated'))
assert.deepEqual([small.pct, small.n], [null, MIN_ADVANCED_POOL - 1])
assert.match(small.reason, /20명 미만/)
assert.equal(small.short, '비교 불가')   // 값은 있으나 모집단이 작다
const unavail = metricPercentile(isoM, advLine('unavailable', null), [], rows(30, 'calculated'))
assert.deepEqual([unavail.pct, unavail.n, unavail.text, unavail.short], [null, null, '-', '데이터 없음'])
assert.ok(unavail.reason)
// K% 는 낮을수록 좋음
assert.equal(M('k_pct').better, 'low')

// 우세: 기본 지표는 시즌이 달라도 값 비교, 고급 지표는 같은 시즌·같은 상태일 때만
const L = (avgV, isoV, status = 'calculated') => ({ stats: { AVG: avgV }, advanced: { metrics: { iso: s(status, isoV) } } })
assert.equal(compareWinner(M('AVG'), L(0.3, 0.2), L(0.28, 0.1), 2025, 2024), 'a')
assert.equal(compareWinner(isoM, L(0.3, 0.2), L(0.28, 0.1), 2025, 2025), 'a')
assert.equal(compareWinner(isoM, L(0.3, 0.2), L(0.28, 0.1), 2025, 2024), null)               // 다른 시즌
assert.equal(compareWinner(isoM, L(0.3, 0.2), L(0.28, 0.1, 'source'), 2025, 2025), null)     // 계산값 vs 출처 값
assert.equal(compareWinner(M('ERA', 'pitcher'), { stats: { ERA: 2.5 } }, { stats: { ERA: 3.1 } }, 2025, 2025), 'a')  // 낮을수록 좋음
assert.equal(compareWinner(M('AVG'), L(null, 0), L(0.28, 0), 2025, 2025), null)

// BB%·K%: 로컬 KBO 기록실 PA(2026 규정 충족 49명)로 계산되는 경로 — 계산값 49명 모집단이면 백분위가 나온다
const bbM = M('bb_pct')
const bbRows = Array.from({ length: 49 }, (_, i) => ({ metrics: { bb_pct: s('calculated', 5 + i * 0.2) } }))
const bb = metricPercentile(bbM, { advanced: { metrics: { bb_pct: s('calculated', 12.7) } } }, [], bbRows)
assert.equal(bb.n, 49)
assert.equal(bb.text, '12.7%')
assert.equal(bb.pct, advancedPercentile(bbRows, 'bb_pct', s('calculated', 12.7), 'high'))
const kRows = Array.from({ length: 49 }, (_, i) => ({ metrics: { k_pct: s('calculated', 10 + i * 0.3) } }))
assert.equal(metricPercentile(M('k_pct'), { advanced: { metrics: { k_pct: s('calculated', 10) } } }, [], kRows).pct, 100)  // 낮을수록 좋음

// 시즌이 다를 때 안내(Compare.jsx): 우세를 감추는 지표 = 차트의 adv 지표 — 타자 ISO·BB%·K%, 투수는 없음
assert.deepEqual(chartMetrics('batter').filter((m) => m.adv).map((m) => m.label), ['ISO', 'BB%', 'K%'])
assert.deepEqual(chartMetrics('pitcher').filter((m) => m.adv), [])
// 실제 동작과 일치: 시즌이 달라도 wRC+ 는 우세가 나오고, ISO 는 나오지 않는다
const W = (wrc, isoV) => ({ stats: { 'wRC+': wrc }, advanced: { metrics: { iso: s('calculated', isoV) } } })
assert.equal(compareWinner(M('wRC+'), W(150, 0.2), W(120, 0.1), 2026, 2025), 'a')
assert.equal(compareWinner(M('iso'), W(150, 0.2), W(120, 0.1), 2026, 2025), null)
assert.equal(compareWinner(M('ERA', 'pitcher'), { stats: { ERA: 2.5 } }, { stats: { ERA: 3.1 } }, 2026, 2025), 'a')  // 투수는 시즌이 달라도 비교

// 사유 목록: 같은 사유끼리 묶고, 백분위가 있는 칸은 넣지 않는다
const nul = (reason) => ({ pct: null, reason })
assert.deepEqual(missingReasons([
  { m: { label: 'BB%' }, a: nul('PA 없음'), b: nul('PA 없음') },
  { m: { label: 'K%' }, a: nul('PA 없음'), b: { pct: 50 } },
  { m: { label: '타율' }, a: { pct: 10 }, b: nul('기록 없음') },
], ['가 · 2026', '나 · 2025']), [
  { reason: 'PA 없음', items: ['BB% — 가 · 2026', 'BB% — 나 · 2025', 'K% — 가 · 2026'] },
  { reason: '기록 없음', items: ['타율 — 나 · 2025'] },
])
assert.deepEqual(missingReasons([{ m: { label: '타율' }, a: { pct: 1 }, b: { pct: 2 } }], ['가', '나']), [])

// 접근성 문장: 색·위치 없이 값·백분위·우세가 읽힌다
assert.equal(chartRowLabel(M('ERA', 'pitcher'), ['가', '나'], { text: '2.50', pct: 100 }, { text: '-', pct: null, reason: '기록 없음' }, null),
  '평균자책점(낮을수록 좋음): 가 2.50, 100백분위 / 나 - (백분위 없음: 기록 없음) · 우세 판정 없음')

console.log('p2d ok')

// 선수 기록 목록의 기본·상세 지표가 수치표에 모두 있다(차트에는 누적·출장량 지표를 올리지 않는다).
{
  const keys = (role) => COMPARE_METRICS[role].map((m) => m.key)
  for (const k of ['G', 'AVG', 'AB', 'H', '2B', '3B', 'HR', 'RBI', 'R', 'SB', 'BB', 'SO', 'OBP', 'SLG', 'OPS', 'wRC+', 'WAR'])
    assert.ok(keys('batter').includes(k), `batter ${k}`)
  for (const k of ['G', 'W', 'L', 'SV', 'HLD', 'IP', 'ERA', 'WHIP', 'SO', 'BB', 'H', 'HR', 'ER', 'QS', 'K/9', 'BB/9', 'K/BB', 'WAR'])
    assert.ok(keys('pitcher').includes(k), `pitcher ${k}`)
  for (const role of ['batter', 'pitcher']) {
    assert.equal(new Set(keys(role)).size, keys(role).length, `${role} 지표 중복 없음`)
    assert.ok(chartMetrics(role).every((m) => !['G', 'AB', 'H', 'HR', 'RBI', 'W', 'SV', 'ER'].includes(m.key)))
  }
  // 출장량 지표: 값은 그대로, 우세·백분위 없음. 값이 없으면 0 이 아니라 '-'.
  const g = COMPARE_METRICS.batter.find((m) => m.key === 'G')
  const line = (G) => ({ stats: { G } })
  assert.equal(compareWinner(g, line(140), line(30), 2026, 2026), null)
  const p = metricPercentile(g, line(140), [{ 규정충족: true, G: 100 }], [])
  assert.equal(p.pct, null)
  assert.equal(p.text, '140')
  assert.equal(metricPercentile(g, line(null), [], []).text, '-')
  // 낮을수록 좋은 상세 지표(타자 삼진, 투수 피안타)
  const so = COMPARE_METRICS.batter.find((m) => m.key === 'SO')
  assert.equal(compareWinner(so, { stats: { SO: 60 } }, { stats: { SO: 90 } }, 2026, 2025), 'a')
  assert.equal(compareWinner(COMPARE_METRICS.pitcher.find((m) => m.key === 'H'), { stats: { H: 150 } }, { stats: { H: 120 } }, 2026, 2026), 'b')
  assert.equal(compareWinner(so, { stats: { SO: null } }, { stats: { SO: 90 } }, 2026, 2026), null)
}
console.log('p2d detail metrics ok')

// 투수 세이브·홀드: 값은 그대로, 백분위·우세 없음(규정이닝 투수 모집단은 대부분 선발이라 0 세이브가 100백분위가 된다).
{
  const sv = COMPARE_METRICS.pitcher.find((m) => m.key === 'SV')
  const hld = COMPARE_METRICS.pitcher.find((m) => m.key === 'HLD')
  const pool = [{ 규정충족: true, SV: 0, HLD: 0 }, { 규정충족: true, SV: 0, HLD: 1 }]
  for (const m of [sv, hld]) {
    const line = (v) => ({ stats: { [m.key]: v } })
    assert.equal(metricPercentile(m, line(0), pool, []).pct, null, `${m.key} 백분위 없음`)
    assert.match(metricPercentile(m, line(0), pool, []).reason, /보직 지표/)
    assert.equal(metricPercentile(m, line(31), pool, []).text, '31', `${m.key} 값은 표시`)
    assert.equal(metricPercentile(m, line(null), pool, []).text, '-', `${m.key} 없는 값은 0 이 아니다`)
    assert.equal(compareWinner(m, line(31), line(0), 2026, 2026), null, `${m.key} 우세 없음`)
    assert.ok(!chartMetrics('pitcher').includes(m))
  }
  // 다른 투수 지표는 그대로 백분위·우세를 매긴다
  const w = COMPARE_METRICS.pitcher.find((m) => m.key === 'W')
  assert.equal(metricPercentile(w, { stats: { W: 11 } }, [{ 규정충족: true, W: 10 }, { 규정충족: true, W: 12 }], []).pct, 50)
  assert.equal(compareWinner(w, { stats: { W: 11 } }, { stats: { W: 15 } }, 2026, 2026), 'b')
  const era = COMPARE_METRICS.pitcher.find((m) => m.key === 'ERA')
  assert.equal(compareWinner(era, { stats: { ERA: 2.24 } }, { stats: { ERA: 3.28 } }, 2026, 2026), 'a')
  assert.deepEqual(chartMetrics('pitcher').map((m) => m.key), ['ERA', 'WHIP', 'K/9', 'BB/9', 'K/BB'])
}
console.log('p2d SV/HLD ok')
