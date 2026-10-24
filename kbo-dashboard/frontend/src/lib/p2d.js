// P2-D 팀 상세 · 선수 검색 · 선수 비교 — API 클라이언트와 표시 규칙(순수 함수).
// 없는 값(null)은 0 으로 바꾸지 않는다: 계산에서 빼고, 화면에는 '미확정'/'자료 없음'으로 보인다.
import axios from 'axios'
import { cleanParams } from './v2.js'

const get = (url, params) => axios.get(url, { params: cleanParams(params || {}), timeout: 15000 }).then((r) => r.data)

export const fetchTeam = (team, season) => get(`/api/v2/teams/${encodeURIComponent(team)}`, { season })
export const searchPlayers = ({ q, team, season, role }) => get('/api/v2/players/search', { q, team, season, role })
export const fetchProfile = (id) => get(`/api/v2/players/${encodeURIComponent(id)}/profile`)
/** 리그 비교 기준(그 시즌 전 선수). v1 /api/player-stats — 네이버 시즌 기록, 같은 열 이름. */
export const fetchLeague = (role, season) =>
  get('/api/player-stats', { role: role === 'batter' ? 'hitter' : 'pitcher', season }).then((d) => d.data || [])

export const ROLE_LABEL = { batter: '타자', pitcher: '투수' }
export const NAVER_SEASON_LABEL = '네이버 시즌 기록 (자동 수집 · KBO 원본 직접 대조 안 함 · 외부 공개 전)'

/** 비교 지표. better: high/low = 백분위 방향. digits/rate = 표시 형식. */
export const COMPARE_METRICS = {
  batter: [
    { key: 'AVG', label: '타율', rate: true, better: 'high' },
    { key: 'OBP', label: '출루율', rate: true, better: 'high' },
    { key: 'SLG', label: '장타율', rate: true, better: 'high' },
    { key: 'OPS', label: 'OPS', rate: true, better: 'high' },
    { key: 'wOBA', label: 'wOBA', rate: true, better: 'high', advanced: true },
    { key: 'wRC+', label: 'wRC+', digits: 1, better: 'high', advanced: true },
    { key: 'ISO', label: 'ISO', rate: true, better: 'high', advanced: true },
    { key: 'HR', label: '홈런', better: 'high' },
    { key: 'SB', label: '도루', better: 'high' },
    { key: 'WAR', label: 'WAR', digits: 2, better: 'high', advanced: true },
  ],
  pitcher: [
    { key: 'ERA', label: '평균자책점', digits: 2, better: 'low' },
    { key: 'WHIP', label: 'WHIP', digits: 2, better: 'low' },
    { key: 'K/9', label: '9이닝당 삼진', digits: 2, better: 'high', advanced: true },
    { key: 'BB/9', label: '9이닝당 볼넷', digits: 2, better: 'low', advanced: true },
    { key: 'K/BB', label: '삼진/볼넷', digits: 2, better: 'high', advanced: true },
    { key: 'IP', label: '이닝', innings: true, better: 'high' },
    { key: 'SO', label: '탈삼진', better: 'high' },
    { key: 'QS', label: '퀄리티 스타트', better: 'high' },
    { key: 'WAR', label: 'WAR', digits: 2, better: 'high', advanced: true },
  ],
}

/** 기록 값 → 숫자. 이닝 '180 2/3' → 180.667. 없거나 숫자가 아니면 null. */
export function toNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const ip = String(value).match(/^(\d+)(?:\s+([12])\/3)?$/)
  if (ip) return Number(ip[1]) + (ip[2] ? Number(ip[2]) / 3 : 0)
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/** 리그 비교 모집단: 그 시즌 규정 충족 선수의 값(없는 값 제외). */
export function leaguePool(rows, key) {
  return rows.filter((r) => r['규정충족'] === true).map((r) => toNumber(r[key])).filter((v) => v !== null)
}

/** 모집단 안 백분위(0–100, 클수록 좋음). 값·모집단이 없으면 null — 0 으로 두지 않는다. */
export function percentile(pool, value, better = 'high') {
  const v = toNumber(value)
  if (v === null || !pool.length) return null
  const worseOrEqual = pool.filter((p) => (better === 'low' ? p >= v : p <= v)).length
  return Math.round((worseOrEqual / pool.length) * 100)
}

/** 두 값 중 나은 쪽: 'a' | 'b' | 'tie' | null(하나라도 없음). */
export function betterSide(a, b, better = 'high') {
  const x = toNumber(a)
  const y = toNumber(b)
  if (x === null || y === null) return null
  if (x === y) return 'tie'
  return (better === 'low' ? x < y : x > y) ? 'a' : 'b'
}

/** 프로필에서 한 시즌·역할 줄. 없으면 null. */
export function seasonLine(profile, season, role) {
  return profile?.data?.seasons?.find((s) => s.season === season && s.role === role) || null
}

/** 두 선수 모두 해당 역할로 뛴 시즌(최근 것부터). */
export function commonSeasons(a, b, role) {
  const seasons = (p) => new Set((p?.data?.seasons || []).filter((s) => s.role === role).map((s) => s.season))
  const sb = seasons(b)
  return [...seasons(a)].filter((s) => sb.has(s)).sort((x, y) => y - x)
}

/** 동명이인 구분 표시: 이름 · 팀 포지션 · 생년월일. 모르는 칸은 뺀다(추측하지 않음). */
export function playerLabel(p) {
  const latest = p.seasons?.[0] || {}
  const team = p.team ?? latest.team
  const position = p.position ?? latest.position
  return [p.name, [team, position].filter(Boolean).join(' '), p.birth_date && `${p.birth_date}생`].filter(Boolean).join(' · ')
}

/** 시즌 범위 '2009–2026 (15시즌)'. */
export function seasonSpan(seasons) {
  const years = [...new Set((seasons || []).map((s) => s.season))].sort((a, b) => a - b)
  if (!years.length) return ''
  const span = years[0] === years.at(-1) ? `${years[0]}` : `${years[0]}–${years.at(-1)}`
  return `${span} (${years.length}시즌)`
}

/** v2 순위표의 홈·원정 'W-D-L' → '41승 1무 29패'. 형식이 다르면 원문 그대로. */
export function recordText(s) {
  const m = String(s ?? '').match(/^(\d+)-(\d+)-(\d+)$/)
  if (!m) return s ?? null
  return `${m[1]}승 ${m[2]}무 ${m[3]}패`
}

/** 'W-D-L' → 승률(무승부 제외). 경기가 없으면 null. */
export function recordPct(s) {
  const m = String(s ?? '').match(/^(\d+)-(\d+)-(\d+)$/)
  if (!m) return null
  const w = Number(m[1])
  const l = Number(m[3])
  return w + l ? w / (w + l) : null
}

/** 최근 경기 한 줄: 결과 · 점수(우리 팀 먼저) · 상대 · 홈/원정. */
export function gameLine(g) {
  const mine = g.side === 'home' ? g.home.score : g.away.score
  const theirs = g.side === 'home' ? g.away.score : g.home.score
  return { result: { W: '승', L: '패', T: '무' }[g.result] || g.result, score: `${mine}:${theirs}`,
    opponent: g.opponent, where: g.side === 'home' ? '홈' : '원정' }
}

const AGREE = new Set(['observed_naver_match', 'naver_verified'])
const CONFLICT = new Set(['observed_naver_conflict', 'naver_conflict', 'naver_unusable'])

/** v2 박스스코어 검증 요약(시즌 기록 화면 /api/v2/players/{id}/season). 항목별 상태 → 일치/불일치/대조 불가 항목 수.
 *  한 경기라도 어긋나면 그 항목은 불일치. 검증 자료가 없으면 null. */
export function verificationSummary(seasonBody, role) {
  const roleBody = seasonBody?.data?.roles?.[role]
  const v = roleBody?.verification
  if (!v || !Object.keys(v).length) return null
  const out = { items: 0, agree: 0, conflict: 0, other: 0, kbo: roleBody.kbo?.status ?? null }
  for (const counts of Object.values(v)) {
    const statuses = Object.keys(counts).filter((k) => counts[k] > 0)
    out.items += 1
    if (statuses.some((k) => CONFLICT.has(k))) out.conflict += 1
    else if (statuses.length && statuses.every((k) => AGREE.has(k))) out.agree += 1
    else out.other += 1
  }
  return out
}

/** 출처 목록에서 가장 늦은 수집 시각(ISO). 없으면 null. */
export function latestCollected(sources) {
  return (sources || []).map((s) => s?.collected_at).filter(Boolean).sort().at(-1) ?? null
}
