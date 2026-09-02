// 시즌 판정 자체 점검. `node src/lib/season.test.js` 로 실행.
import assert from 'node:assert/strict'
import { seasonState, kstToday, ZONE_SEASONS } from './season.js'

// 2026 정규시즌 일정 흉내: 3/21 개막 ~ 10/3 종료.
// 과거 날짜의 취소 경기(status='scheduled', 재편성 안 됨)를 일부러 섞는다.
function schedule(season, opening, closing, playedUntil) {
  const rows = []
  const [y, m, d] = opening.split('-').map(Number)
  for (let i = 0; ; i++) {
    const dt = new Date(Date.UTC(y, m - 1, d + i))
    const date = dt.toISOString().slice(0, 10)
    if (date > closing) break
    // 5경기마다 1건은 취소된 채 status='scheduled'로 남아 있는 경기
    const cancelled = i % 5 === 0
    rows.push({ Season: season, Date: date, status: date <= playedUntil && !cancelled ? 'final' : 'scheduled' })
  }
  return rows
}

const s2026 = schedule(2026, '2026-03-21', '2026-10-03', '2026-10-03')  // 시즌 종료 상태
const inSeason = schedule(2026, '2026-03-21', '2026-10-03', '2026-08-30')
const s2027 = schedule(2027, '2027-03-27', '2027-10-05', '2027-03-26')  // 개막 전(전부 미소화)

// 1) 정규시즌
let r = seasonState('2026-08-31', inSeason)
assert.equal(r.state, 'regular')
assert.equal(r.dataSeason, 2026)
assert.equal(r.storyEnabled, true)
assert.equal(r.isFallback, false)
assert.equal(r.label, '2026 정규시즌')

// 2) 포스트시즌 (정규시즌 종료 + 10월)
r = seasonState('2026-10-15', s2026)
assert.equal(r.state, 'postseason')
assert.equal(r.dataSeason, 2026)
assert.equal(r.storyEnabled, true)
assert.equal(r.label, '2026 정규시즌 최종')

// 3) 오프시즌 (같은 해 12월) — AI 스토리 호출 금지
r = seasonState('2026-12-20', s2026)
assert.equal(r.state, 'offseason')
assert.equal(r.storyEnabled, false)
assert.equal(r.isFallback, false)

// 3-b) 오프시즌 + 활성 시즌 폴백 (2027년 1월인데 일정 데이터는 2026뿐)
r = seasonState('2027-01-10', s2026)
assert.equal(r.state, 'offseason')
assert.equal(r.isFallback, true)
assert.match(r.notice, /2027시즌 데이터가 없어/)

// 4) 개막전 (다음 시즌 일정 공개됨) — 직전 시즌 기록을 보여주고 스토리는 끈다
r = seasonState('2027-02-20', s2027)
assert.equal(r.state, 'preseason')
assert.equal(r.season, 2027)
assert.equal(r.dataSeason, 2026)
assert.equal(r.daysToOpening, 35)
assert.equal(r.storyEnabled, false)
assert.equal(r.label, '2027 시즌 개막 D-35')

// 함정 검증: 과거 취소 경기(status='scheduled')만 남았을 때 정규시즌으로 오판하지 않는다.
const onlyCancelled = s2026.filter((g) => g.status === 'scheduled')
assert.equal(onlyCancelled.length > 0, true)
assert.equal(seasonState('2026-12-01', onlyCancelled).state, 'offseason')

// 빈 일정(수집 실패)에서도 판정이 깨지지 않는다.
assert.equal(seasonState('2026-06-01', []).state, 'regular')
assert.equal(seasonState('2026-12-01', []).state, 'offseason')

// KST 기준: UTC 2026-08-30 20:00 = KST 2026-08-31
assert.equal(kstToday(new Date('2026-08-30T20:00:00Z')), '2026-08-31')

// 투구 데이터 커버리지는 내림차순이어야 한다 — Zones.jsx 의 폴백이 [0] = 최신에 기댄다.
assert.deepEqual([...ZONE_SEASONS].sort((a, b) => b - a), ZONE_SEASONS)

console.log('ok: season.js 자체 점검 통과')
