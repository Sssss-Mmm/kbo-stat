// apiError 자체 점검. `node src/lib/apiError.test.js` 로 실행.
// 화면에 영문 axios 문구가 새는 것과, 서로 다른 실패가 같은 문구로 뭉개지는 것을 막는다.
import assert from 'node:assert/strict'
import { apiError } from './apiError.js'

// 1) 백엔드가 준 한국어 detail 이 최우선이다.
const withDetail = { response: { status: 404, data: { detail: '2026시즌 hitter 선수 데이터가 없습니다.' } }, message: 'Request failed with status code 404' }
assert.equal(apiError(withDetail), '2026시즌 hitter 선수 데이터가 없습니다.')

// 2) 서로 다른 실패는 서로 다른 문구여야 한다 — 조치가 다르기 때문이다.
const noResponse = { message: 'Network Error' }          // 백엔드 다운
const notFound = { response: { status: 404, data: {} } }  // 그 시즌 자료 없음(정상일 수 있음)
const dbDown = { response: { status: 503, data: { detail: 'database unavailable' } } }
const serverErr = { response: { status: 500, data: {} } }
const msgs = [apiError(noResponse), apiError(notFound), apiError(dbDown), apiError(serverErr)]
assert.equal(new Set(msgs).size, 4, `네 가지 실패가 구분되어야 한다: ${JSON.stringify(msgs)}`)

// 3) 영문 axios 문구가 새지 않는다.
for (const m of msgs) {
  assert.ok(!/Request failed|Network Error/.test(m), `영문 원문이 노출됐다: ${m}`)
}

// 4) detail 이 비었거나 문자열이 아니면 상태코드로 떨어진다.
assert.equal(apiError({ response: { status: 500, data: { detail: '   ' } } }), '서버 오류가 발생했습니다 (HTTP 500).')
assert.equal(apiError({ response: { status: 400, data: { detail: { msg: 'x' } } } }), '요청이 거부되었습니다 (HTTP 400).')

// 5) 아무것도 없어도 깨지지 않는다.
assert.equal(apiError(undefined), '서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.')
assert.equal(apiError({}), '서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.')

console.log('ok: apiError 자체 점검 통과')
