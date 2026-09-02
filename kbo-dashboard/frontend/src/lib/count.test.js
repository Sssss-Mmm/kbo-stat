// 볼카운트 파생 계산 자체 점검. `node src/lib/count.test.js` 로 실행.
// 투구 단위/타석 단위 분모를 섞으면 조용히 틀리므로 실제 응답 일부를 박아 둔다.
import assert from 'node:assert/strict'
import { indexRows, matrixRows, bucketTable, paEnough, pitchEnough, MIN_PA } from './count.js'

// 2026-09-01 /api/count-baseball?season=2026 응답에서 발췌(값은 실제 CSV 그대로).
const ROWS = [
  { Scope: '리그', PlayerId: 0, Player: '리그 전체', Bucket: '전체', PA: 41078, PaShare: 1, Pitches: 160124, SwingRate: 0.4495, FoulRate: 0.1702, KRate: 0.1915, OnBaseRate: 0.336, Days: 111, FirstDate: '2026-03-28', LastDate: '2026-08-30' },
  { Scope: '리그', PlayerId: 0, Player: '리그 전체', Bucket: '초구', PA: 41078, PaShare: 1, Pitches: 41081, SwingRate: 0.2659, FoulRate: 0.0944, KRate: 0.1915, OnBaseRate: 0.336 },
  { Scope: '리그', PlayerId: 0, Player: '리그 전체', Bucket: '2S', PA: 21059, PaShare: 0.5127, Pitches: 46039, SwingRate: 0.6149, FoulRate: 0.2439, KRate: 0.3735, OnBaseRate: 0.2652 },
  { Scope: '리그', PlayerId: 0, Player: '리그 전체', Bucket: '0-0', PA: 41078, PaShare: 1, Pitches: 41081, SwingRate: 0.2659, KRate: 0.1915, OnBaseRate: 0.336 },
  { Scope: '리그', PlayerId: 0, Player: '리그 전체', Bucket: '3-0', PA: 1980, PaShare: 0.0482, Pitches: 1980, SwingRate: 0.0298, KRate: 0.0646, OnBaseRate: 0.7551 },
  { Scope: '리그', PlayerId: 0, Player: '리그 전체', Bucket: '0-2', PA: 8207, PaShare: 0.1998, Pitches: 10175, SwingRate: 0.4963, KRate: 0.4155, OnBaseRate: 0.2106 },
  { Scope: '선수', PlayerId: 1, Player: '많이본타자', Team: 'LG', Side: 'L', Bucket: '전체', PA: 400, PaShare: 1, Pitches: 1600, SwingRate: 0.4, KRate: 0.15, OnBaseRate: 0.4 },
  { Scope: '선수', PlayerId: 1, Player: '많이본타자', Team: 'LG', Side: 'L', Bucket: '초구', PA: 400, PaShare: 1, Pitches: 400, SwingRate: 0.1, KRate: 0.15, OnBaseRate: 0.4 },
  { Scope: '선수', PlayerId: 1, Player: '많이본타자', Team: 'LG', Side: 'L', Bucket: '타자유리', PA: 15, PaShare: 0.0375, Pitches: 25, SwingRate: 0.32, KRate: 0.0667, OnBaseRate: 0.6 },
  { Scope: '선수', PlayerId: 2, Player: '표본적은타자', Team: 'KT', Side: 'R', Bucket: '전체', PA: 12, PaShare: 1, Pitches: 40, SwingRate: 0.5, KRate: 0.25, OnBaseRate: 0.25 },
]

const { league, players, coverage } = indexRows(ROWS)

// 리그/선수가 Scope 로 정확히 갈린다. 리그 행은 선수 목록에 섞이면 안 된다.
assert.equal(players.length, 2)
assert.equal(players[0].id, 1, '타석 많은 순 정렬')
assert.equal(players[0].pa, 400)
assert.equal(league['3-0'].OnBaseRate, 0.7551)

// 커버리지는 행마다 같은 값 — 첫 행에서 읽는다(부분 수집 배지의 근거).
assert.equal(coverage.Days, 111)
assert.equal(coverage.FirstDate, '2026-03-28')

// 12칸 매트릭스: 4행 × 3열, 없는 칸은 null(빈칸으로 그린다).
const m = matrixRows(league)
assert.equal(m.length, 4)
assert.equal(m[0].cells.length, 3)
assert.equal(m[0].cells[0].Bucket, '0-0')
assert.equal(m[0].cells[2].Bucket, '0-2')
assert.equal(m[1].cells[0], null, '없는 칸은 null')
assert.equal(m[3].cells[0].Bucket, '3-0')

// 카운트가 타석을 바꾼다: 3-0 출루율 > 0-2 출루율, 3-0 스윙률 << 0-2 스윙률.
assert.ok(league['3-0'].OnBaseRate > league['0-2'].OnBaseRate)
assert.ok(league['3-0'].SwingRate < league['0-2'].SwingRate)

// 버킷 표: 선수에게 없는 버킷(2S)은 행을 만들지 않는다. 리그 짝은 같은 버킷이다.
const table = bucketTable(players[0], league)
assert.deepEqual(table.map((r) => r.bucket), ['전체', '초구', '타자유리'])
assert.equal(table[1].lg.SwingRate, 0.2659)
assert.equal(table[1].row.SwingRate, 0.1)

// 표본 하한: 투구 25구/타석 15는 미달이라 수치를 적지 않는다(0/0 을 .000 으로 찍지 않기).
assert.equal(pitchEnough(table[2].row), false, '25구는 투구 단위 하한 미달')
assert.equal(paEnough(table[2].row), false, '15타석은 타석 단위 하한 미달')
assert.equal(pitchEnough(table[1].row), true)
assert.equal(paEnough(table[1].row), true)
assert.equal(paEnough(null), false, 'null 행은 표본 없음')

// 목록 기본 필터: 12타석 타자는 감춘다.
assert.deepEqual(players.filter((p) => p.pa >= MIN_PA).map((p) => p.id), [1])

console.log('count.test.js OK')
