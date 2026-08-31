// 이동거리 계산 자체 점검. `node src/lib/travel.test.js` 로 실행.
// 구장 좌표는 크롤링 데이터가 아니라 손으로 박은 상수라 오타가 나도 조용히 틀린 거리가 나온다.
// 그래서 알려진 구장(도시) 간 직선거리와 ±10% 로 대조하는 게 이 파일의 본체다.
import assert from 'node:assert/strict'
import { BALLPARKS, haversine, parkDistance, teamTravel } from './travel.js'

// 1) 좌표가 한반도 범위 안에 있는가 (위도/경도를 뒤집어 넣는 실수를 잡는다)
Object.entries(BALLPARKS).forEach(([name, [lat, lon]]) => {
  assert.ok(lat > 33 && lat < 39, `${name} 위도 이상: ${lat}`)
  assert.ok(lon > 125 && lon < 130, `${name} 경도 이상: ${lon}`)
})

// 2) 알려진 구장 간 직선거리 대조 (기준값은 도시 간 대권거리 통념치, 허용 오차 ±10%)
const REF = [
  ['잠실', '사직', 325],  // 서울~부산
  ['잠실', '광주', 268],  // 서울~광주
  ['잠실', '대구', 237],  // 서울~대구
  ['잠실', '대전', 140],  // 서울~대전
  ['잠실', '창원', 295],  // 서울~창원
  ['광주', '사직', 200],  // 광주~부산
  ['잠실', '문학', 33],   // 잠실~인천 문학
  ['잠실', '수원', 25],   // 잠실~수원
  ['고척', '문학', 17],   // 고척~문학
  ['사직', '창원', 42],   // 부산~창원
  ['대구', '포항', 65],   // 대구~포항
  ['대전', '청주', 36],   // 대전~청주
  ['사직', '울산', 45],   // 부산~울산
]
REF.forEach(([a, b, ref]) => {
  const d = parkDistance(a, b)
  const err = Math.abs(d - ref) / ref
  assert.ok(err <= 0.10, `${a}~${b} ${d.toFixed(1)}km, 기준 ${ref}km (오차 ${(err * 100).toFixed(1)}%)`)
})

// 3) Haversine 자체 — 같은 점은 0, 위도 1도는 약 111km
assert.equal(haversine([37.5, 127], [37.5, 127]), 0)
assert.ok(Math.abs(haversine([36, 127], [37, 127]) - 111.2) < 0.5)

// 4) 좌표를 모르는 구장은 null (0km 와 구분한다)
assert.equal(parkDistance('잠실', '잠실'), 0)
assert.equal(parkDistance('잠실', '도쿄돔'), null)

// 5) 이동 누적: 첫 경기 이전 이동은 세지 않고, 같은 구장 연전은 0km, 홈 복귀도 이동이다
const rows = [
  { Team: '롯데', Date: '2026-04-03', GameId: 'g1', Ballpark: '사직', HomeAway: 'home' },
  { Team: '롯데', Date: '2026-04-04', GameId: 'g2', Ballpark: '사직', HomeAway: 'home' },  // 연전 → 0km
  { Team: '롯데', Date: '2026-04-07', GameId: 'g3', Ballpark: '잠실', HomeAway: 'away' },  // 사직→잠실
  { Team: '롯데', Date: '2026-04-10', GameId: 'g4', Ballpark: '사직', HomeAway: 'home' },  // 잠실→사직(복귀)
]
const t = teamTravel(rows).teams[0]
assert.equal(t.games, 4)
assert.equal(t.legs, 3)
assert.equal(t.moves, 2)
assert.equal(t.stays, 1)
assert.ok(Math.abs(t.km - parkDistance('사직', '잠실') * 2) < 0.001)
assert.equal(t.longest.from, '사직')
assert.equal(t.longest.to, '잠실')

// 6) 날짜가 뒤섞여 들어와도 정렬해서 계산한다
const shuffled = [rows[2], rows[0], rows[3], rows[1]]
assert.ok(Math.abs(teamTravel(shuffled).teams[0].km - t.km) < 0.001)

// 7) 좌표 없는 구장의 경기는 제외하고 앞뒤를 이어 붙인다 + 미매칭 비율을 보고한다
const withUnknown = [
  rows[0],
  { Team: '롯데', Date: '2026-04-05', GameId: 'gx', Ballpark: '도쿄돔', HomeAway: 'away' },
  rows[2],
]
const u = teamTravel(withUnknown)
assert.deepEqual(u.unknownParks, ['도쿄돔'])
assert.equal(u.unknownGames, 1)
assert.ok(Math.abs(u.ratioUnknown - 1 / 3) < 1e-9)
assert.ok(Math.abs(u.teams[0].km - parkDistance('사직', '잠실')) < 0.001)  // 사직→잠실 한 구간

// 8) 빈 배열에서도 깨지지 않는다
assert.deepEqual(teamTravel([]), { teams: [], total: 0, unknownParks: [], unknownGames: 0, ratioUnknown: 0 })
assert.deepEqual(teamTravel().teams, [])

console.log('ok: travel.js 자체 점검 통과 (좌표 대조 %d쌍)', REF.length)
