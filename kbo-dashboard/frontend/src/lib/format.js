// 숫자·기록 문자열 포맷 헬퍼. Home / Teams 등 여러 페이지가 공유한다.

export const fmtRate = (v) => (Number.isFinite(v) ? v.toFixed(3).replace(/^0/, '') : '-')
export const fmtOne = (v) => (Number.isFinite(v) ? v.toFixed(1) : '-')
export const fmtTwo = (v) => (Number.isFinite(v) ? v.toFixed(2) : '-')
export const fmtInt = (v) => (Number.isFinite(v) ? Math.round(v).toLocaleString('ko-KR') : '-')
export const fmtPct = (v) => (Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '-')
// 분 -> "3:06" (경기 소요시간 표기)
export const fmtMinutes = (v) => (Number.isFinite(v) ? `${Math.floor(v / 60)}:${String(Math.round(v % 60)).padStart(2, '0')}` : '-')

// "22-10"(승-패) 또는 "19-0-10"(승-무-패) -> {w, l, pct}
export function parseRecord(s) {
  const parts = String(s || '').split('-').map((x) => parseInt(x, 10) || 0)
  const [w, l] = parts.length === 3 ? [parts[0], parts[2]] : [parts[0] || 0, parts[1] || 0]
  return { w, l, pct: w + l ? w / (w + l) : null }
}

export const recordWinRate = (s) => parseRecord(s).pct || 0

// "3승"/"2패"/"1무" -> 부호 있는 점수 (연승 +, 연패 -)
export function streakScore(s) {
  if (!s) return 0
  const n = parseInt(s, 10) || 0
  if (s.includes('승')) return n
  if (s.includes('패')) return -n
  return 0
}

// "6승0무4패" -> 승률
export function recentWinRate(s) {
  if (!s) return 0
  const w = parseInt((s.match(/(\d+)승/) || [])[1] || 0, 10)
  const l = parseInt((s.match(/(\d+)패/) || [])[1] || 0, 10)
  return w + l ? w / (w + l) : 0
}
