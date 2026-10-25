// 투구 분석(존 히트맵·구종 아스널·볼카운트) 공용 문구.
// Hits/InPlay 는 삼진·볼넷이 빠진 인플레이 타구 기준이라 공식 타율·BABIP 와 다르다.
// 세 탭이 같은 이름을 쓰도록 라벨을 여기 한 곳에 둔다.

export const HIT_RATE_NOTE = '인플레이 타구 중 안타 비율(삼진·볼넷 제외, 홈런 포함). 공식 타율 및 BABIP와 다른 지표입니다.'

export function hitRateLabel(role) {
  return role === 'pitcher' ? '피인플레이 안타율' : '인플레이 안타율'
}

// 2026-03-28 ~ 2026-09-24 → 2026.03.28~09.24 (같은 해면 끝 연도 생략).
function fmtRange(first, last) {
  const a = String(first).replaceAll('-', '.')
  const b = String(last).replaceAll('-', '.')
  return a.slice(0, 5) === b.slice(0, 5) ? `${a}~${b.slice(5)}` : `${a}~${b}`
}

export const COVERAGE_UNKNOWN = '투구 데이터 범위 확인 불가'

// /api/pitch-coverage 의 data → '투구 데이터: 2026.03.28~09.24 · 663/720경기(92.1%)'.
// 일정이 없으면 수집률 없이 경기 수만. 원본이 없거나(null) 범위를 모르면 COVERAGE_UNKNOWN.
// label 은 분석 CSV 가 원본보다 오래됐을 때 '투구 원본'으로 바꿔 둘을 구분한다.
export function coverageText(cov, label = '투구 데이터') {
  if (!cov || !cov.first_date || !cov.last_date || !Number.isFinite(cov.games)) return COVERAGE_UNKNOWN
  const parts = [fmtRange(cov.first_date, cov.last_date)]
  if (Number.isFinite(cov.regular_games) && cov.regular_total > 0) {
    parts.push(`${cov.regular_games}/${cov.regular_total}경기(${(cov.regular_games / cov.regular_total * 100).toFixed(1)}%)`)
    if (cov.unscheduled_games > 0) parts.push(`일정 미반영 ${cov.unscheduled_games}경기 포함`)
    if (cov.other_games > 0) parts.push(`정규시즌 외 ${cov.other_games}경기 포함`)
  } else {
    parts.push(`${cov.games}경기`)
  }
  return `${label}: ${parts.join(' · ')}`
}

// 탭·역할 → 그 화면이 실제로 읽는 분석 CSV(pitch-coverage 의 analysis 키).
export function analysisKey(view, role) {
  if (view === 'count') return 'count_baseball'
  if (view === 'arsenal') return role === 'pitcher' ? 'pitcher_arsenal' : 'batter_vs_pitch'
  return role === 'pitcher' ? 'pitcher_zones' : 'batter_zones'
}

// 분석 CSV 가 원본과 다르면 화면에 실제로 보이는 범위를 먼저 알린다. 일치하거나 모르면(undefined) null.
// entry === null 은 원본은 있는데 분석 CSV 가 없다는 뜻이다. 존 CSV 는 날짜 메타가 없어 투구 수로만 말한다.
export function staleText(entry) {
  if (entry === null) return '표시할 분석 데이터 없음 · 분석 데이터 갱신 필요'
  if (!entry?.stale) return null
  const shown = entry.first_date
    ? `${fmtRange(entry.first_date, entry.last_date)}(${entry.days}일)`
    : `${entry.pitches.toLocaleString()}구(원본 ${entry.raw_pitches.toLocaleString()}구)`
  return `표시 중인 분석 데이터: ${shown} · 분석 데이터 갱신 필요`
}
