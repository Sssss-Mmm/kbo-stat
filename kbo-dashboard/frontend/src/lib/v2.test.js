import assert from 'node:assert/strict'
import {
  cleanParams, fmtKst, fmtLeaderValue, fmtStat, inningsFromOuts, intParam, kboLabel, kstInputToIso, recentTrend,
  notFoundMessage, playerGamesParams, qualifiedBattingRanking, UNKNOWN, verificationInfo,
  emptyScheduleMessage, toStandingsTableRow, dateOnly, RANK_CHECK,
} from './v2.js'

// 이닝: 정수 아웃 → 1/3 단위. 미확정은 null 그대로(0 이닝으로 바꾸지 않는다).
assert.equal(inningsFromOuts(0), '0')
assert.equal(inningsFromOuts(1), '0 1/3')
assert.equal(inningsFromOuts(17), '5 2/3')
assert.equal(inningsFromOuts(542), '180 2/3')
assert.equal(inningsFromOuts(null), null)
assert.equal(inningsFromOuts(undefined), null)

// null 은 0 이 아니라 '미확정'. 0 은 0.
assert.equal(fmtStat(null), UNKNOWN)
assert.equal(fmtStat(0), '0')
assert.equal(fmtStat(0.3374, { rate: true }), '.337')
assert.equal(fmtStat(1.888, { digits: 2 }), '1.89')
assert.equal(fmtLeaderValue('outs', 542), '180 2/3')
assert.equal(fmtLeaderValue('era', null), UNKNOWN)
assert.equal(fmtLeaderValue('avg', 0.337), '.337')

// KBO 직접 검증은 kbo_verified 일 때만 '일치'. 그 밖(현재 전부 not_checked)은 '검증 전'.
assert.equal(kboLabel({ status: 'not_checked' }), 'KBO 직접 검증 전')
assert.equal(kboLabel(undefined), 'KBO 직접 검증 전')
assert.equal(kboLabel({ status: 'kbo_verified' }), 'KBO 원본 직접 검증 일치')
for (const status of ['observed_naver_match', 'naver_verified']) {
  assert.ok(!verificationInfo(status).label.includes('KBO'), status)  // 네이버 대조를 KBO 검증처럼 쓰지 않는다
}
assert.equal(verificationInfo('없는상태').short, '—')

// 쿼리: 빈 값·false 는 보내지 않는다(서버 기본값 사용).
assert.deepEqual(cleanParams({ season: 2025, role: '', as_of: null, qualified: false, min_ab: 0 }), { season: 2025, min_ab: 0 })

// datetime-local → KST ISO
assert.equal(kstInputToIso('2026-10-24T09:00'), '2026-10-24T09:00:00+09:00')
assert.equal(kstInputToIso(''), null)
assert.equal(fmtKst('2026-10-23T14:15:42.843350+00:00'), '2026-10-23 23:15 KST')

// URL 숫자 파라미터
const q = new URLSearchParams('id=55730&season=abc&limit=')
assert.equal(intParam(q, 'id'), 55730)
assert.equal(intParam(q, 'season', 2025), 2025)
assert.equal(intParam(q, 'limit', 50), 50)

// 추세: 외부 기록 없는 경기는 건너뛰고, 모르는 값은 0 이 아니라 NaN(그래프에서 빠짐).
const games = [
  { role: 'pitcher', date: '2025-04-01', official: { outs: 17, so: 5 } },
  { role: 'pitcher', date: '2025-04-07', official: null },
  { role: 'pitcher', date: '2025-04-13', official: { outs: null, so: 3 } },
]
const pt = recentTrend(games, 'pitcher')
assert.equal(pt.innings.length, 2)
assert.ok(Math.abs(pt.innings[0].y - 17 / 3) < 1e-9)
assert.ok(Number.isNaN(pt.innings[1].y))
const bat = recentTrend([
  { role: 'batter', date: '1', official: { h: 2, ab: 4 } },
  { role: 'batter', date: '2', official: { h: null, ab: null } },
  { role: 'batter', date: '3', official: { h: 1, ab: 4 } },
], 'batter')
assert.deepEqual(bat.avg.map((p) => p.y), [0.5, 3 / 8])  // 모르는 경기는 누적 타율에 넣지 않는다
assert.ok(Number.isNaN(bat.hits[1].y))

// 404 문구: as_of 가 있으면 '그때 확보하지 않음', 없으면 '찾지 못함'
assert.ok(notFoundMessage('player', '2025-10-01T00:00:00+09:00').includes('확보하지 않았습니다'))
assert.ok(notFoundMessage('game', null).includes('찾지 못했습니다'))

// 경기 기록·추세는 시즌 합계와 같은 기간(through_date → date_to)
assert.equal(playerGamesParams({ season: 2025, role: 'pitcher', through: '2025-06-30', limit: 15 }).dateTo, '2025-06-30')
assert.equal(playerGamesParams({ season: 2025, role: 'pitcher', through: '', limit: 15 }).dateTo, null)

// 공식 규정타석 순위: 규정충족만, 타율 내림차순, 표기 기준 동률은 같은 순위
const season = [
  { PlayerId: 1, 선수명: '타자A', 팀명: 'SSG', G: 96, AVG: 0.339, 규정충족: false },
  { PlayerId: 2, 선수명: '타자B', 팀명: '두산', G: 130, AVG: 0.337004, 규정충족: true },
  { PlayerId: 3, 선수명: '타자C', 팀명: 'KT', G: 112, AVG: 0.334177, 규정충족: true },
  { PlayerId: 4, 선수명: '동률', 팀명: 'KT', G: 120, AVG: 0.3341, 규정충족: true },
  { PlayerId: 5, 선수명: '기록없음', 팀명: 'LG', G: 1, AVG: null, 규정충족: true },
]
const official = qualifiedBattingRanking(season)
assert.deepEqual(official.map((r) => [r.rank, r.name]), [[1, '타자B'], [2, '타자C'], [2, '동률']])

console.log('v2 ok')

// P2-C: 빈 일정 이유 구분 · 표 행 변환
assert.equal(emptyScheduleMessage('no_games'), '이 날은 경기가 없습니다.')
assert.match(emptyScheduleMessage('out_of_range', { first_date: '2026-03-28', last_date: '2026-10-12' }), /범위 밖.*2026-10-12/)
assert.notEqual(emptyScheduleMessage('out_of_range'), emptyScheduleMessage('no_games'))
assert.equal(emptyScheduleMessage(null), null)
const tr = toStandingsTableRow({ rank: 2, team: '롯데', games: 133, wins: 72, losses: 56, draws: 5, pct: 0.563,
  games_behind: 1, last10: '5승0무5패', streak: '1승', home: '36-3-27', away: '36-2-29' })
assert.deepEqual([tr.win_rate, tr.last_10_games, tr.home_record], [0.563, '5승0무5패', '36-3-27'])
assert.equal(dateOnly('2026-10-22T02:00:06+00:00'), '2026-10-22')
// 원본 순위가 다른 사유(포스트시즌 반영)는 추정이다 — 확정처럼 쓰지 않는다
assert.match(RANK_CHECK.differs, /미확정/)
assert.ok(!/반영한 최종 순위(이다|다)/.test(RANK_CHECK.differs))
console.log('v2 p2c ok')
