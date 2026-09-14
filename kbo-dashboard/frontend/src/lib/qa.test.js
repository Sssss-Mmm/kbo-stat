import test from 'node:test'
import assert from 'node:assert/strict'
import { conversationHistory } from './qa.js'

test('follow-up context retains the last two questions and answers within API bounds', () => {
  const turns = Array.from({ length: 5 }, (_, i) => ({ question: `질문${i}`, season: 2026, answer: { title: `답${i}`, summary: '가'.repeat(1500) } }))
  const history = conversationHistory(turns)
  assert.deepEqual(history.map((m) => m.role), ['user', 'assistant', 'user', 'assistant'])
  assert.equal(history[0].content, '질문3')
  assert.equal(history[2].content, '질문4')
  assert.ok(history.every((m) => m.content.length <= 1000))
  assert.ok(history[1].content.startsWith('2026시즌. 답3'))
  assert.deepEqual(conversationHistory([]), [])
})
