// axios 오류를 화면에 보여줄 한국어 문구로 바꾼다.
//
// 백엔드 라우터는 404/400 에 한국어 detail 을 실어 보낸다
// (예: "2026시즌 hitter 선수 데이터가 없습니다."). 그런데 화면은 err.message 만
// 써서 그 문구를 버리고 "Request failed with status code 500" 을 한국어
// 대시보드에 그대로 띄웠다. 게다가 백엔드 다운(연결 실패)·시즌 데이터 없음(404)·
// DB 다운(503)이 화면에서 구분되지 않았다 — 첫째는 서버를 봐야 하고, 둘째는
// 1월이라면 아무 조치도 필요 없는 정상 상태다.
//
// 우선순위: 백엔드가 준 detail > 상태코드별 안내 > 연결 실패.
export function apiError(err) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail

  const status = err?.response?.status
  if (!status) return '서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.'
  if (status === 404) return '요청한 데이터가 없습니다.'
  if (status === 503) return '데이터베이스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
  if (status >= 500) return `서버 오류가 발생했습니다 (HTTP ${status}).`
  return `요청이 거부되었습니다 (HTTP ${status}).`
}
