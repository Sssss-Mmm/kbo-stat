// web/ 와 동일한 팀 색상 팔레트.
export const TEAM_COLORS = {
  LG: '#0b7f74',
  KT: '#2e65b8',
  삼성: '#356bc6',
  KIA: '#d05240',
  한화: '#e0872c',
  두산: '#243b6b',
  SSG: '#c73845',
  NC: '#315f8d',
  롯데: '#8a5a28',
  키움: '#7a3f76',
}

export function teamColor(team) {
  return TEAM_COLORS[team] || '#53636f'
}

// 팀 엠블럼: 구단 엠블럼은 각 구단의 상표라 공개 저장소에 포함하지 않는다.
// 로컬에서만 public/emblems/{코드}.png 를 직접 넣고 VITE_TEAM_EMBLEMS=1 로 켜면 표시된다.
// 꺼져 있으면 엠블럼 자리를 비우고 팀명·팀 색상만 쓴다.
const EMBLEMS_ENABLED = import.meta.env?.VITE_TEAM_EMBLEMS === '1'
const EMBLEM = (code) => `/emblems/${code}.png`
export const TEAM_EMBLEMS = {
  LG: EMBLEM('LG'),
  KT: EMBLEM('KT'),
  삼성: EMBLEM('SS'),
  KIA: EMBLEM('HT'),
  한화: EMBLEM('HH'),
  두산: EMBLEM('OB'),
  SSG: EMBLEM('SK'),
  NC: EMBLEM('NC'),
  롯데: EMBLEM('LT'),
  키움: EMBLEM('WO'),
}

export function teamEmblem(team) {
  if (!EMBLEMS_ENABLED) return null
  return TEAM_EMBLEMS[team] || null
}
