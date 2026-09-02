// 목록 정렬/필터 자체 점검. `node src/lib/list.test.js` 로 실행.
import assert from 'node:assert/strict'
import { sortRows, nextSort, listFilter } from './list.js'

const rows = [
  { name: '가', pitches: 300, rate: 0.31, qualified: true },
  { name: '나', pitches: 90, rate: null, qualified: false },
  { name: '다', pitches: 120, rate: 0.28, qualified: false },
]

// 숫자는 수치 비교, 방향은 dir 이 정한다.
assert.deepEqual(sortRows(rows, { key: 'pitches', dir: 'desc' }).map((r) => r.name), ['가', '다', '나'])
assert.deepEqual(sortRows(rows, { key: 'pitches', dir: 'asc' }).map((r) => r.name), ['나', '다', '가'])
// 빈값은 방향과 무관하게 항상 뒤 — 오름차순에서 null 이 맨 위로 올라오면 안 된다.
assert.deepEqual(sortRows(rows, { key: 'rate', dir: 'asc' }).map((r) => r.name), ['다', '가', '나'])
assert.deepEqual(sortRows(rows, { key: 'rate', dir: 'desc' }).map((r) => r.name), ['가', '다', '나'])
// 원본은 건드리지 않는다(useMemo 입력이 그대로 재사용된다).
assert.equal(rows[0].name, '가')

// 같은 컬럼 재클릭 = 방향 토글, 새 컬럼 = 내림차순 시작.
assert.deepEqual(nextSort({ key: 'pa', dir: 'desc' }, 'pa'), { key: 'pa', dir: 'asc' })
assert.deepEqual(nextSort({ key: 'pa', dir: 'asc' }, 'pa'), { key: 'pa', dir: 'desc' })
assert.deepEqual(nextSort({ key: 'pa', dir: 'asc' }, 'name'), { key: 'name', dir: 'desc' })

// 규정충족 플래그가 있는 시즌: 기준이 규정충족으로 승격된다.
const opts = { min: 100, unit: '구', noun: '선수', sample: (p) => p.pitches }
const flagged = listFilter(rows, opts)
assert.equal(flagged.byRule, true)
assert.deepEqual(rows.filter(flagged.keep).map((r) => r.name), ['가'])
assert.match(flagged.label, /규정 미달 포함/)

// 플래그가 전부 null 인 시즌(2025): 기준이 표본 하한으로 되돌아간다.
// 여기서 규정충족을 기준으로 삼으면 목록이 통째로 빈다 — 이 화면의 유일한 위험 분기다.
const unknown = rows.map((r) => ({ ...r, qualified: null }))
const fallback = listFilter(unknown, opts)
assert.equal(fallback.byRule, false)
assert.deepEqual(unknown.filter(fallback.keep).map((r) => r.name), ['가', '다'])
assert.match(fallback.label, /표본 부족 선수 포함\(100구 미만\)/)

console.log('list.test.js OK')
