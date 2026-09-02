// 가을야구 레이스 계산 자체 점검. `node src/lib/race.test.js` 로 실행.
// 매직넘버·잔여경기·피타고리안은 조용히 틀리기 쉬워서 손으로 계산한 값을 박아 둔다.
import assert from 'node:assert/strict'
import {
  remainingGames, pythagorean, gamesBehind, teamRunTotals,
  raceRows, contenders, dailyRanks, remainingMatchups, showMagicNumbers,
} from './race.js'

// 2026-08-31 실제 /api/standings 스냅샷 (games, wins, losses, draws)
const S = [
  [1, '삼성', 115, 68, 44, 3, 0.607],
  [2, 'KT', 112, 66, 43, 3, 0.606],
  [3, 'KIA', 115, 63, 50, 2, 0.558],
  [4, 'LG', 116, 64, 51, 1, 0.557],
  [5, '두산', 117, 61, 52, 4, 0.540],
  [6, 'NC', 111, 51, 58, 2, 0.468],
  [7, '롯데', 113, 50, 61, 2, 0.450],
  [8, '한화', 114, 49, 62, 3, 0.441],
  [9, 'SSG', 118, 48, 65, 5, 0.425],
  [10, '키움', 121, 42, 76, 3, 0.356],
].map(([rank, team, games, wins, losses, draws, win_rate]) => ({ rank, team, games, wins, losses, draws, win_rate }))

// 1) 잔여 경기 = 144 - 경기수 (미래 일정 개수로 세지 않는다)
assert.equal(remainingGames(115), 29)
assert.equal(remainingGames(144), 0)
assert.equal(remainingGames(150), 0)  // 데이터가 이상해도 음수는 내지 않는다

// 2) 피타고리안
assert.equal(pythagorean(500, 500).toFixed(3), '0.500')
assert.equal(pythagorean(600, 500).toFixed(3), '0.583')
assert.equal(pythagorean(0, 0), null)

// 3) 게임차 (무승부는 양쪽 모두 제외)
assert.equal(gamesBehind({ wins: 61, losses: 52 }, { wins: 68, losses: 44 }), -7.5)  // 음수 = 앞서 있음
assert.equal(gamesBehind({ wins: 61, losses: 52 }, { wins: 51, losses: 58 }), 8)

// 4) team-games 누적 = 공식 순위표 (승·패·무·경기수)
const games = [
  { Date: '2026-03-28', Team: '삼성', Win: 0, Loss: 1, Draw: 0, RunsFor: 3, RunsAgainst: 6 },
  { Date: '2026-03-28', Team: '롯데', Win: 1, Loss: 0, Draw: 0, RunsFor: 6, RunsAgainst: 3 },
  { Date: '2026-03-29', Team: '삼성', Win: 1, Loss: 0, Draw: 0, RunsFor: 5, RunsAgainst: 1 },
  { Date: '2026-03-29', Team: '롯데', Win: 0, Loss: 1, Draw: 0, RunsFor: 1, RunsAgainst: 5 },
  { Date: '2026-03-30', Team: '삼성', Win: 0, Loss: 0, Draw: 1, RunsFor: 2, RunsAgainst: 2 },
  { Date: '2026-03-30', Team: '롯데', Win: 0, Loss: 0, Draw: 1, RunsFor: 2, RunsAgainst: 2 },
]
const totals = teamRunTotals(games)
assert.deepEqual(totals['삼성'], { team: '삼성', games: 3, wins: 1, losses: 1, draws: 1, runsFor: 10, runsAgainst: 9 })

// 5) 매직/트래직 넘버 — 손으로 계산한 값
const rows = raceRows(S, {}, 5)
const by = Object.fromEntries(rows.map((r) => [r.team, r]))
// 진출선 밖 최대 승수 = NC 51 + 33 = 84
assert.equal(by['NC'].maxWins, 84)
assert.equal(by['삼성'].magic, 84 - 68 + 1)   // 17
assert.equal(by['두산'].magic, 84 - 61 + 1)   // 24
assert.equal(by['삼성'].tragic, null)         // 진출선 안쪽은 트래직을 계산하지 않는다
// 진출선(5위 두산) 61승 기준 트래직
assert.equal(by['NC'].tragic, 84 - 61 + 1)    // 24
assert.equal(by['키움'].tragic, 65 - 61 + 1)  // 5
assert.equal(by['키움'].magic, null)

// 자력(전승하면 남의 결과와 무관하게 5위 이내) / 탈락 확정
assert.equal(by['두산'].selfPower, true)   // 최대승수 88 위로 4팀뿐
assert.equal(by['NC'].selfPower, false)    // 최대승수 84 위로 5팀
assert.equal(rows.every((r) => r.eliminated === false), true)  // 8/31 시점 수학적 탈락 팀 없음

// 5위와의 승차
assert.equal(by['삼성'].gbCut, -7.5)
assert.equal(by['두산'].gbCut, 0)
assert.equal(by['NC'].gbCut, 8)

// 진출선을 1위(우승 레이스)로 바꾸면 기준 팀도 바뀐다
const top = Object.fromEntries(raceRows(S, {}, 1).map((r) => [r.team, r]))
assert.equal(top['삼성'].magic, 98 - 68 + 1)  // 밖 최대승수 = KT 98
assert.equal(top['KT'].tragic, 98 - 68 + 1)   // 1위 삼성 68승 기준

// 5-b) 매직넘버 표시 시점 (AC3): 시즌 초반(잔여 60 초과)에는 열 자체를 그리지 않는다
assert.equal(showMagicNumbers(rows), true)  // 8/31 잔여 23~33
const early = S.map((s) => ({ ...s, games: 30, wins: 15, losses: 15, draws: 0 }))
assert.equal(raceRows(early, {}, 5)[0].remaining, 114)
assert.equal(showMagicNumbers(raceRows(early, {}, 5)), false)
assert.equal(showMagicNumbers([]), false)

// 6) 경쟁팀: 5위 ±5게임차 + 4~6위는 항상
assert.deepEqual(contenders(rows, 5).sort(), ['KIA', 'LG', 'NC', '두산'].sort())

// 7) 피타고리안 열이 순위표 승률과 나란히 붙는지 (totals 있을 때만)
const withRuns = raceRows(S.slice(0, 1), { 삼성: { runsFor: 600, runsAgainst: 500 } }, 5)[0]
assert.equal(withRuns.pyth.toFixed(3), '0.583')
assert.equal(withRuns.pythDiff.toFixed(3), '0.024')  // 실제 .607 - 기대 .583
assert.equal(raceRows(S.slice(0, 1), {}, 5)[0].pyth, null)  // 득실점이 없으면 빈 값

// 8) 일별 순위 복원 — 마지막 날 순위가 누적 승률 순
const race = dailyRanks(games)
assert.deepEqual(race.dates, ['2026-03-28', '2026-03-29', '2026-03-30'])
const last = (t) => race.series.find((s) => s.team === t).points.at(-1).rank
assert.equal(last('롯데'), 1)  // 1승1패1무로 동률 → 승수도 같으면 팀명(가나다) 순
assert.equal(last('삼성'), 2)
assert.equal(race.series.find((s) => s.team === '삼성').points[0].rank, 2)  // 개막일 패배
assert.equal(race.series.every((s) => s.points.length === 3), true)  // 안 뛴 날도 순위가 이어진다

// 9) 남은 맞대결 — 과거 날짜의 취소 경기(status='scheduled')는 제외된다
const sched = [
  { Date: '2026-08-20', status: 'scheduled', away_team: '두산', home_team: 'NC', Ballpark: '창원' },  // 우천취소
  { Date: '2026-08-30', status: 'final', away_team: '두산', home_team: 'NC', Ballpark: '창원' },
  { Date: '2026-09-03', status: 'scheduled', away_team: 'NC', home_team: '두산', Ballpark: '잠실' },
  { Date: '2026-09-12', status: 'scheduled', away_team: '두산', home_team: 'NC', Ballpark: '창원' },
  { Date: '2026-09-05', status: 'scheduled', away_team: '키움', home_team: '두산', Ballpark: '잠실' },  // 경쟁팀 아님
]
const m = remainingMatchups(sched, ['두산', 'NC'], '2026-08-31')
assert.equal(m.length, 1)
assert.equal(m[0].games.length, 2)
assert.deepEqual(m[0].games.map((g) => g.date), ['2026-09-03', '2026-09-12'])

// 10) 빈 응답에서도 깨지지 않는다
assert.deepEqual(raceRows([], {}, 5), [])
assert.deepEqual(dailyRanks([]), { series: [], dates: [] })
assert.deepEqual(remainingMatchups([], [], '2026-08-31'), [])

// 11) win_rate 가 null 이면 피타고리안 차이는 null 이다.
//     null - 0.52 는 NaN 이 아니라 -0.52 라, 예전엔 없는 차이를 -.520 으로 그렸다.
const nullRate = [{ rank: 1, team: '삼성', games: 115, wins: 68, losses: 44, draws: 3, win_rate: null }]
const nullTotals = { 삼성: { runsFor: 600, runsAgainst: 500 } }
const [nullRow] = raceRows(nullRate, nullTotals, 5)
assert.ok(Number.isFinite(nullRow.pyth), '득실점이 있으면 피타고리안은 계산된다')
assert.equal(nullRow.pythDiff, null, 'win_rate 가 null 이면 차이는 null 이어야 한다')

// 득실점이 없으면 피타고리안이 없으므로 차이도 null.
const [noRuns] = raceRows([{ rank: 1, team: 'LG', games: 116, wins: 64, losses: 51, draws: 1, win_rate: 0.557 }], {}, 5)
assert.equal(noRuns.pythDiff, null)

// 양쪽 다 있으면 실제 차이가 나온다.
const [ok] = raceRows([{ rank: 1, team: 'LG', games: 116, wins: 64, losses: 51, draws: 1, win_rate: 0.557 }], { LG: { runsFor: 600, runsAgainst: 500 } }, 5)
assert.ok(Math.abs(ok.pythDiff - (0.557 - ok.pyth)) < 1e-9)

console.log('ok: race.js 자체 점검 통과')
