const normalize = (value) => String(value ?? '').normalize('NFKC').replace(/\s+/g, '').toLocaleLowerCase('ko-KR')

export function playerKey(row) {
  return String(row.PlayerId ?? `${row['팀명']}:${row['선수명']}`)
}

// 이름 부분 일치. 공백·전각/반각·대소문자를 무시하므로 '김 현수' 로도 '김현수' 가 잡힌다.
// 빈 검색어는 항상 참 — 호출부가 매번 `!search ||` 를 쓰지 않아도 된다.
export function matchesName(name, query) {
  const term = normalize(query)
  return !term || normalize(name).includes(term)
}

export function filterPlayers(rows, { team = 'all', query = '', qualified = false }) {
  return rows.filter((row) => (team === 'all' || row['팀명'] === team)
    && (!qualified || row['규정충족'] === true)
    && matchesName(row['선수명'], query))
}

export function toggleComparison(selected, id) {
  if (selected.includes(id)) return selected.filter((value) => value !== id)
  return selected.length < 2 ? [...selected, id] : selected
}

export const BASIC_COLUMNS = {
  hitter: ['선수명', '팀명', 'G', 'AVG', 'HR', 'RBI', 'OPS', 'WAR'],
  pitcher: ['선수명', '팀명', 'G', 'W', 'L', 'SV', 'IP', 'ERA', 'WHIP', 'WAR'],
}

export const STAT_LABELS = {
  선수명: '선수 이름', 팀명: '소속 구단', 포지션: '수비 포지션', G: '출장 경기',
  AVG: '타율', AB: '타수', H: '안타 / 투수는 피안타', '2B': '2루타', '3B': '3루타',
  HR: '홈런 / 투수는 피홈런', RBI: '타점', R: '득점', SB: '도루', BB: '볼넷',
  SO: '삼진 / 투수는 탈삼진', OBP: '출루율', SLG: '장타율', OPS: '출루율 + 장타율',
  'wRC+': '조정 득점 창출력 · 100이 리그 평균', WAR: '대체 선수 대비 승리 기여도 · 수집 자료 기준',
  W: '승리', L: '패배', SV: '세이브', HLD: '홀드', IP: '투구 이닝',
  ERA: '평균자책점 · 낮을수록 적은 자책점', WHIP: '이닝당 안타·볼넷 허용 · 낮을수록 적은 출루 허용',
  ER: '자책점', QS: '퀄리티 스타트 · 6이닝 이상, 3자책점 이하',
  'K/9': '9이닝당 탈삼진', 'BB/9': '9이닝당 볼넷', 'K/BB': '탈삼진 / 볼넷',
}
