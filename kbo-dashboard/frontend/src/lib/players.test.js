import assert from 'node:assert/strict'
import { compareUrl, filterPlayers, matchesName, playerKey, toggleComparison } from './players.js'

const rows = [
  { PlayerId: 1, 선수명: '홍길동', 팀명: 'LG', 규정충족: true },
  { PlayerId: 2, 선수명: '홍길동', 팀명: '삼성', 규정충족: false },
  { PlayerId: 3, 선수명: '선수C', 팀명: 'LG', 규정충족: true },
]
assert.equal(filterPlayers(rows, { query: ' 홍 길 동 ' }).length, 2)
assert.deepEqual(filterPlayers(rows, { query: '홍', team: 'LG', qualified: true }), [rows[0]])
assert.equal(filterPlayers(rows, { query: '없는선수' }).length, 0)
assert.notEqual(playerKey(rows[0]), playerKey(rows[1]))
const selected = toggleComparison(toggleComparison([], '1'), '2')
assert.deepEqual(toggleComparison(selected, '3'), ['1', '2'])
assert.deepEqual(toggleComparison(selected, '1'), ['2'])
assert.deepEqual(selected, ['1', '2'])

// 이름 검색은 공백·대소문자·전각을 무시한다.
assert.equal(matchesName('홍길동', ' 홍 길 동 '), true)
assert.equal(matchesName('홍길동', '길동'), true)
assert.equal(matchesName('홍길동', ''), true, '빈 검색어는 전부 통과해야 한다')
assert.equal(matchesName('홍길동', '선수Z'), false)
assert.equal(matchesName(null, '홍'), false, '이름이 없는 행에서 터지면 안 된다')

// 비교 화면 이동: 선수 ID 두 개일 때만, 역할(hitter→batter)·시즌을 그대로 싣는다.
assert.equal(compareUrl(['52605', '66606'], 'hitter', 2026), '/compare?role=batter&a=52605&b=66606&sa=2026&sb=2026')
assert.equal(compareUrl(['1', '2'], 'pitcher', 2025), '/compare?role=pitcher&a=1&b=2&sa=2025&sb=2025')
assert.equal(compareUrl(['52605'], 'hitter', 2026), null, '한 명이면 이동하지 않는다')
assert.equal(compareUrl(['LG:홍길동', '2'], 'hitter', 2026), null, 'ID 없는 대체 키는 다른 선수로 바꾸지 않는다')
assert.equal(compareUrl(['0', '2'], 'hitter', 2026), null)
assert.equal(compareUrl(['abc', '2'], 'hitter', 2026), null)
