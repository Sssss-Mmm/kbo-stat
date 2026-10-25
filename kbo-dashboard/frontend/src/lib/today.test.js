import test from 'node:test'
import assert from 'node:assert/strict'
import { scheduleNotes, BASIS, STALE } from './today.js'

const body = (date, codes) => ({ date, asOf: '2026-10-24T02:13+09:00', data: codes.map((statusCode) => ({ statusCode })) })

test('저장 일정 기준·자료 저장 시각을 항상 보여 준다', () => {
  const n = scheduleNotes(body('2026-10-12', ['RESULT']), '2026-10-25')
  assert.equal(n.basis, BASIS)
  assert.match(n.basis, /저장된 일정 기준\(실시간 아님\)/)
  assert.equal(n.asOf, '일정 자료 2026-10-24 02:13 저장')
  assert.equal(n.stale, null)
})

test('지난 날짜인데 예정으로 남은 경기는 결과 미반영으로 안내한다', () => {
  assert.equal(scheduleNotes(body('2026-10-10', ['RESULT', 'BEFORE']), '2026-10-25').stale, STALE)
  assert.equal(scheduleNotes(body('2026-10-25', ['BEFORE']), '2026-10-25').stale, null)  // 오늘 경기는 아직 예정일 수 있다
  assert.equal(scheduleNotes(body('2026-10-10', ['CANCEL']), '2026-10-25').stale, null)
})

test('자료 시각이 없으면 지어내지 않는다', () => {
  assert.equal(scheduleNotes({ date: '2026-10-10', data: [] }, '2026-10-25').asOf, null)
  assert.equal(scheduleNotes(undefined, '2026-10-25').stale, null)
})
