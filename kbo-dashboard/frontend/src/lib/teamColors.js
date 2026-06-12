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

// 팀 엠블럼: KBO 공식 엠블럼(Naver CDN 원본)을 로컬에 받아 자체 origin 에서 서빙.
// CDN 직접 참조는 핫링크(Referer) 차단으로 403 이 나므로 public/emblems/ 로 vendoring.
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
  return TEAM_EMBLEMS[team] || null
}
