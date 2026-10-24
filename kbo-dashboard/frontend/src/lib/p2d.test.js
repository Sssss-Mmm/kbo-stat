import assert from 'node:assert/strict'
import {
  betterSide, commonSeasons, gameLine, leaguePool, percentile, playerLabel, recordPct, recordText, seasonLine, seasonSpan,
  toNumber, verificationSummary, latestCollected,
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

console.log('p2d ok')
