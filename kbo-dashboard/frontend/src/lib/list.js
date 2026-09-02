// 선수 목록 표(존 히트맵 · 구종 아스널 · 볼카운트)가 공유하는 정렬/필터 규칙.
// 세 화면이 같은 목록 UI 라 세 번 복붙하는 대신 여기 한 군데에 둔다.

const blank = (v) => v === null || v === undefined || v === ''

// 정렬 규칙: 빈값은 방향과 무관하게 항상 뒤. 방향을 뒤집었더니 '-' 가 맨 위로
// 올라오는 표는 읽을 수 없다. 숫자는 수치 비교, 그 외는 한글 로케일 비교.
export function sortRows(rows, { key, dir }) {
  const factor = dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    if (blank(av) && blank(bv)) return 0
    if (blank(av)) return 1
    if (blank(bv)) return -1
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * factor
    return String(av).localeCompare(String(bv), 'ko') * factor
  })
}

// 같은 컬럼 재클릭이면 방향 토글, 새 컬럼이면 내림차순으로 시작.
export const nextSort = (prev, key) =>
  prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }

/**
 * 목록 필터 한 축. 토글은 계속 하나고 의미만 승격시킨다 —
 * 규정충족 토글을 표본 하한 토글 옆에 하나 더 붙이면 거의 같은 뜻의 스위치가 둘이 된다.
 *
 * 백엔드가 행마다 규정충족(true/false/null)을 실어 준다. null 은 '규정 미달'이 아니라
 * '알 수 없음'이다(시즌 스탯 CSV 가 없는 2025 는 전부 null). 그래서 기준을 시즌마다 바꾼다.
 *   플래그가 하나라도 있으면 → 규정충족이 기준
 *   전부 null 이면          → 기존 표본 하한(min)이 기준  ← 2025 가 통째로 비지 않는 이유
 *
 * @param players  {qualified: true|false|null, ...}[]
 * @param opts     min/unit/noun = 폴백 하한과 라벨 문구, sample = 하한을 잴 값
 * @returns {{byRule, keep, label, empty}}
 */
export function listFilter(players, { min, unit, noun, sample }) {
  const byRule = players.some((p) => p.qualified === true || p.qualified === false)
  return {
    byRule,
    keep: (p) => (byRule ? p.qualified === true : sample(p) >= min),
    label: byRule ? '규정 미달 포함' : `표본 부족 ${noun} 포함(${min}${unit} 미만)`,
    // 필터 결과가 0명이면 빈 표로 침묵하지 않고 무엇을 끄면 되는지 말한다.
    empty: byRule
      ? `규정을 충족한 ${noun}가 없습니다 — 위 '규정 미달 포함'을 켜면 전체가 보입니다.`
      : `${min}${unit} 이상인 ${noun}가 없습니다 — 위 체크박스를 켜면 전체가 보입니다.`,
  }
}
