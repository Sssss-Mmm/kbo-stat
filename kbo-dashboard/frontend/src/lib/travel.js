// 팀별 이동거리 계산 (G-02). 날짜순으로 이어지는 경기 사이의 구장 이동을 누적한다.
//
// 정의 (숫자를 믿으려면 정의가 보여야 한다):
//  - 이동 = 직전 경기 구장 -> 다음 경기 구장. 원정/홈 복귀 모두 이동으로 센다.
//  - 같은 구장 연전은 0km(이동 없음)로 센다.
//  - 시즌 첫 경기 이전의 이동(스프링캠프/연고지 -> 개막 구장)은 직전 위치를 알 수 없어 세지 않는다.
//  - 거리는 Haversine 대권거리(직선). 실제 이동은 도로·항공이라 이보다 길지만,
//    임의의 보정 계수를 곱하지 않고 직선거리임을 화면에 명시한다.
//  - 휴식일/올스타 브레이크로 며칠 떠 있어도 "직전 경기 -> 다음 경기" 한 구간으로 센다.

// 구장 좌표(WGS84 위도, 경도). 우리 수집 데이터에 좌표가 없어 외부 지식을 상수로 박아 둔다.
// 오타가 나면 조용히 틀린 거리가 나오므로 travel.test.js 에서 알려진 구장 간 거리와 ±10% 로 대조한다.
export const BALLPARKS = {
  잠실: [37.5122, 127.0719],  // 서울 잠실야구장 (LG·두산 공용)
  고척: [37.4982, 126.8672],  // 서울 고척스카이돔 (키움)
  문학: [37.4370, 126.6932],  // 인천 SSG랜더스필드 (SSG)
  수원: [37.2997, 127.0097],  // 수원 KT위즈파크 (KT)
  대전: [36.3172, 127.4292],  // 대전 한화생명볼파크 (한화) — 구 한밭야구장과 같은 부지
  청주: [36.6394, 127.4700],  // 청주야구장 (한화 제2구장)
  대구: [35.8410, 128.6816],  // 대구 삼성라이온즈파크 (삼성)
  포항: [36.0083, 129.3597],  // 포항야구장 (삼성 제2구장)
  광주: [35.1682, 126.8890],  // 광주-기아 챔피언스필드 (KIA)
  사직: [35.1940, 129.0615],  // 부산 사직야구장 (롯데)
  울산: [35.5430, 129.2657],  // 울산 문수야구장 (롯데 제2구장)
  창원: [35.2225, 128.5822],  // 창원NC파크 (NC)
}

const R = 6371  // 지구 평균 반지름 km
const rad = (d) => (d * Math.PI) / 180

// 두 좌표([lat, lon]) 사이 대권거리 km.
export function haversine([lat1, lon1], [lat2, lon2]) {
  const dLat = rad(lat2 - lat1)
  const dLon = rad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

// 구장 이름 두 개 사이 거리 km. 좌표를 모르는 구장이면 null(계산 불가와 0km 를 구분한다).
export function parkDistance(from, to) {
  if (from === to) return 0
  const a = BALLPARKS[from]
  const b = BALLPARKS[to]
  return a && b ? haversine(a, b) : null
}

/**
 * /api/team-games 응답으로 팀별 이동거리를 집계한다.
 * @param rows [{Team, Date, GameId, Ballpark, HomeAway}]
 * @returns {{teams, total, unknownParks, unknownGames, ratioUnknown}}
 *   teams: [{team, km, games, legs, moves, stays, perGame, longest}] — 이동거리 내림차순
 *   legs = 이동 구간 수(경기수-1), moves = 실제로 구장이 바뀐 횟수, stays = 같은 구장 연전
 */
export function teamTravel(rows = []) {
  const known = (r) => r && r.Date && r.Ballpark && BALLPARKS[r.Ballpark]
  const unknownParks = [...new Set(rows.filter((r) => r.Ballpark && !BALLPARKS[r.Ballpark]).map((r) => r.Ballpark))]
  const unknownGames = rows.filter((r) => !known(r)).length

  const byTeam = {}
  // 좌표를 모르는 구장의 경기는 건너뛴다. 앞뒤 경기는 그대로 이어 붙여 이동을 센다
  // (구간이 통째로 사라져 이동거리가 과소집계되는 것보다 낫다).
  rows.filter(known).forEach((r) => { (byTeam[r.Team] ||= []).push(r) })

  const teams = Object.entries(byTeam).map(([team, list]) => {
    // 같은 날 더블헤더는 GameId 끝자리(0/1)로 순서를 잡는다.
    const g = [...list].sort((a, b) => (a.Date.localeCompare(b.Date) || String(a.GameId).localeCompare(String(b.GameId))))
    let km = 0
    let moves = 0
    let longest = null
    for (let i = 1; i < g.length; i += 1) {
      const d = parkDistance(g[i - 1].Ballpark, g[i].Ballpark)
      if (d === null) continue
      km += d
      if (d > 0) moves += 1
      if (!longest || d > longest.km) longest = { km: d, from: g[i - 1].Ballpark, to: g[i].Ballpark, date: g[i].Date }
    }
    const legs = Math.max(0, g.length - 1)
    return { team, km, games: g.length, legs, moves, stays: legs - moves, perGame: g.length ? km / g.length : 0, longest }
  }).sort((a, b) => b.km - a.km)

  return {
    teams,
    total: teams.reduce((s, t) => s + t.km, 0),
    unknownParks,
    unknownGames,
    ratioUnknown: rows.length ? unknownGames / rows.length : 0,
  }
}
