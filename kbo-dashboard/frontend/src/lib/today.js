// 오늘의 경기 카드 안내 문구. /api/today-games 는 저장된 일정 CSV 로만 답한다(실시간 아님 — P3-S1).

export const BASIS = '저장된 일정 기준(실시간 아님) · 선발 정보 없음'
export const STALE = '저장 이후 갱신되지 않아 결과가 반영되지 않은 경기가 있습니다.'

/**
 * @param body  /api/today-games 응답 ({date, asOf, data})
 * @param today 'YYYY-MM-DD' (KST)
 * @returns {{basis: string, asOf: string|null, stale: string|null}}
 */
export function scheduleNotes(body, today) {
  const asOf = body?.asOf ? `일정 자료 ${body.asOf.slice(0, 10)} ${body.asOf.slice(11, 16)} 저장` : null
  const past = body?.date && body.date < today
  const stale = past && (body.data || []).some((g) => g.statusCode === 'BEFORE') ? STALE : null
  return { basis: BASIS, asOf, stale }
}
