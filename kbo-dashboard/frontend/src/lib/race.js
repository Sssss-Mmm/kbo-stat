// 가을야구 레이스 계산 (IDEAS #1) + 순위표 확장 지표 (G-01).
// 전부 결정론적 산수다. 승부 예측·확률 시뮬레이션은 비목표(PLAN 3절)이므로 여기 없다.
// React 를 import 하지 않는다 — `node src/lib/race.test.js` 로 그대로 돌린다.

export const SEASON_GAMES = 144      // KBO 정규시즌 팀당 경기 수
export const PLAYOFF_CUT = 5         // 가을야구 진출선(5위)
export const MAGIC_MAX_REMAINING = 60  // 잔여가 이보다 많으면 매직넘버는 무의미(AC3)

// 잔여 경기. 취소 경기가 재편성되면 미래 일정 개수는 흔들리므로 항상 144 - 경기수로 센다.
export const remainingGames = (games) => Math.max(0, SEASON_GAMES - (games || 0))

// 피타고리안 기대승률. 지수 1.83은 야구에서 통용되는 값.
export function pythagorean(runsFor, runsAgainst, exponent = 1.83) {
  if (!(runsFor > 0) && !(runsAgainst > 0)) return null
  const f = Math.pow(runsFor, exponent)
  const a = Math.pow(runsAgainst, exponent)
  return f + a ? f / (f + a) : null
}

// 게임차 = ((상대승 - 내승) + (내패 - 상대패)) / 2. 무승부는 양쪽 모두 제외(KBO 규정).
export function gamesBehind(target, team) {
  if (!target || !team) return null
  return ((target.wins - team.wins) + (team.losses - target.losses)) / 2
}

// /api/team-games 를 팀별로 누적. 승·패·무는 순위표와 일치하고, 득·실점은 피타고리안 입력이다.
export function teamRunTotals(teamGames = []) {
  const acc = {}
  teamGames.forEach((g) => {
    const t = acc[g.Team] || (acc[g.Team] = { team: g.Team, games: 0, wins: 0, losses: 0, draws: 0, runsFor: 0, runsAgainst: 0 })
    t.games += 1
    t.wins += g.Win || 0
    t.losses += g.Loss || 0
    t.draws += g.Draw || 0
    t.runsFor += g.RunsFor || 0
    t.runsAgainst += g.RunsAgainst || 0
  })
  return acc
}

/**
 * 레이스 표 한 행씩 계산한다.
 * @param standings /api/standings 응답 (순위·승패무가 공식 기록)
 * @param totals    teamRunTotals() 결과 (득실점 전용. 없으면 피타고리안만 비고 나머지는 그대로)
 * @param cutRank   진출선 순위(기본 5위)
 *
 * 매직넘버 M — 진출선 안쪽 팀 기준. "진출선 밖 팀이 전승했을 때의 승수" 를 넘기까지 필요한
 *   (내 승리 + 그 팀 패배) 횟수 = 상대최대승수 - 내승수 + 1. 0이면 확정.
 * 트래직넘버 T — 진출선 밖 팀 기준. 내가 전승해도 진출선 팀의 현재 승수에 못 미치면 탈락이므로
 *   T = 내최대승수 - 진출선팀승수 + 1. 0이면 탈락 확정.
 * 둘 다 상대 한 팀만 보는 표준 단순화다(다팀 동시 경쟁은 반영하지 않는다). 화면에 명시한다.
 */
export function raceRows(standings = [], totals = {}, cutRank = PLAYOFF_CUT) {
  const base = [...standings].sort((a, b) => a.rank - b.rank).map((s) => {
    const t = totals[s.team]
    const remaining = remainingGames(s.games)
    return {
      ...s,
      remaining,
      maxWins: s.wins + remaining,
      runsFor: t ? t.runsFor : null,
      runsAgainst: t ? t.runsAgainst : null,
      pyth: t ? pythagorean(t.runsFor, t.runsAgainst) : null,
    }
  })
  if (!base.length) return []

  const cutTeam = base[Math.min(cutRank, base.length) - 1]
  const outsiders = base.filter((r) => r.rank > cutRank)
  // 진출선 밖에서 가장 위협적인 팀 = 전승 시 승수가 가장 많은 팀(6위라는 보장이 없다).
  const rivalMaxWins = outsiders.length ? Math.max(...outsiders.map((r) => r.maxWins)) : null

  return base.map((r) => {
    const inside = r.rank <= cutRank
    // 탈락 확정: 이미 내 최대 승수보다 승수가 많은 팀이 진출선 수만큼 있으면 전승해도 못 들어간다.
    const ahead = base.filter((o) => o.team !== r.team && o.wins > r.maxWins).length
    const eliminated = ahead >= cutRank
    // 자력 진출: 전승했을 때 나보다 최대 승수가 많은 팀이 진출선 미만이면 남의 결과와 무관하게 들어간다.
    const better = base.filter((o) => o.team !== r.team && o.maxWins > r.maxWins).length
    const selfPower = !eliminated && better < cutRank

    const magic = inside && rivalMaxWins != null ? Math.max(0, rivalMaxWins - r.wins + 1) : null
    const tragic = inside ? null : Math.max(0, r.maxWins - cutTeam.wins + 1)
    return {
      ...r,
      inside,
      eliminated,
      selfPower,
      magic,
      tragic,
      // win_rate 는 DB 컬럼이 비면 null 로 온다. null - 0.52 는 NaN 이 아니라 -0.52 라
      // ?? null 가드가 무력했고, 없는 피타고리안 차이를 -.520 으로 단정해 그렸다.
      pythDiff: Number.isFinite(r.pyth) && Number.isFinite(r.win_rate) ? r.win_rate - r.pyth : null,
      gbCut: r.team === cutTeam.team ? 0 : gamesBehind(cutTeam, r),
      cutTeam: cutTeam.team,
    }
  })
}

// 매직넘버를 보여줄 시점인가 (AC3). 시즌 초반에는 산수는 되지만 의미가 없다.
export const showMagicNumbers = (rows = []) =>
  rows.length > 0 && rows.every((r) => r.remaining <= MAGIC_MAX_REMAINING)

// 진출선 다툼 중인 팀들. 진출선 팀과 5게임차 이내 + 진출선 앞뒤 순위는 항상 포함한다.
export function contenders(rows, cutRank = PLAYOFF_CUT, band = 5) {
  const near = rows.filter((r) => Math.abs(r.gbCut ?? 99) <= band || (r.rank >= cutRank - 1 && r.rank <= cutRank + 1))
  return near.map((r) => r.team)
}

/**
 * 경기 결과를 날짜순으로 누적해 일별 순위를 복원한다.
 * 공식 순위 스냅샷은 6/9 이후뿐이라 시즌 전반부 곡선은 이 재구성으로만 그린다.
 * 순위는 승률(무승부 제외) 내림차순, 동률이면 승수 → 팀명 순으로 가른다.
 * @returns {{series: [{team, points:[{index,rank}]}], dates: string[]}}
 */
export function dailyRanks(teamGames = []) {
  const byDate = {}
  teamGames.forEach((g) => { (byDate[g.Date] || (byDate[g.Date] = [])).push(g) })
  const dates = Object.keys(byDate).sort()

  const acc = {}
  const series = {}
  dates.forEach((date, index) => {
    byDate[date].forEach((g) => {
      const t = acc[g.Team] || (acc[g.Team] = { w: 0, l: 0 })
      t.w += g.Win || 0
      t.l += g.Loss || 0
    })
    Object.entries(acc)
      .sort(([ta, a], [tb, b]) => {
        const pa = a.w + a.l ? a.w / (a.w + a.l) : 0
        const pb = b.w + b.l ? b.w / (b.w + b.l) : 0
        return pb - pa || b.w - a.w || ta.localeCompare(tb, 'ko')
      })
      .forEach(([team], i) => { (series[team] || (series[team] = [])).push({ index, rank: i + 1 }) })
  })

  return { series: Object.entries(series).map(([team, points]) => ({ team, points })), dates }
}

/**
 * 경쟁팀끼리 남은 맞대결. /api/schedule-games 에는 Note 컬럼이 없으므로
 * 취소 경기(과거 날짜인데 status='scheduled')는 날짜 조건으로 걸러낸다 — 결과는 Note 필터와 같다.
 */
export function remainingMatchups(schedule = [], teams = [], today = '') {
  const set = new Set(teams)
  const pairs = {}
  schedule
    .filter((g) => g.status !== 'final' && g.Date >= today && set.has(g.home_team) && set.has(g.away_team))
    .forEach((g) => {
      const [a, b] = [g.away_team, g.home_team].sort((x, y) => x.localeCompare(y, 'ko'))
      const p = pairs[`${a}|${b}`] || (pairs[`${a}|${b}`] = { a, b, games: [] })
      p.games.push({ date: g.Date, ballpark: g.Ballpark, home: g.home_team })
    })
  return Object.values(pairs)
    .map((p) => ({ ...p, games: p.games.sort((x, y) => x.date.localeCompare(y.date)) }))
    .sort((x, y) => y.games.length - x.games.length || x.a.localeCompare(y.a, 'ko'))
}
