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
