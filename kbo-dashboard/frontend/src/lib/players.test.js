import assert from 'node:assert/strict'
import { filterPlayers, matchesName, playerKey, toggleComparison } from './players.js'

const rows = [
  { PlayerId: 1, 선수명: '김현수', 팀명: 'LG', 규정충족: true },
  { PlayerId: 2, 선수명: '김현수', 팀명: '삼성', 규정충족: false },
  { PlayerId: 3, 선수명: '오스틴', 팀명: 'LG', 규정충족: true },
]
assert.equal(filterPlayers(rows, { query: ' 김 현 수 ' }).length, 2)
assert.deepEqual(filterPlayers(rows, { query: '김', team: 'LG', qualified: true }), [rows[0]])
assert.equal(filterPlayers(rows, { query: '없는선수' }).length, 0)
assert.notEqual(playerKey(rows[0]), playerKey(rows[1]))
const selected = toggleComparison(toggleComparison([], '1'), '2')
assert.deepEqual(toggleComparison(selected, '3'), ['1', '2'])
assert.deepEqual(toggleComparison(selected, '1'), ['2'])
assert.deepEqual(selected, ['1', '2'])

// 이름 검색은 공백·대소문자·전각을 무시한다.
assert.equal(matchesName('김현수', ' 김 현 수 '), true)
assert.equal(matchesName('김현수', '현수'), true)
assert.equal(matchesName('김현수', ''), true, '빈 검색어는 전부 통과해야 한다')
assert.equal(matchesName('김현수', '박병호'), false)
assert.equal(matchesName(null, '김'), false, '이름이 없는 행에서 터지면 안 된다')
