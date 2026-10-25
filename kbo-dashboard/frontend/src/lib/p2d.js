// P2-D 팀 상세 · 선수 검색 · 선수 비교 — API 클라이언트와 표시 규칙(순수 함수).
// 없는 값(null)은 0 으로 바꾸지 않는다: 계산에서 빼고, 화면에는 '미확정'/'자료 없음'으로 보인다.
import axios from 'axios'
import { cleanParams, fmtStat } from './v2.js'

const get = (url, params) => axios.get(url, { params: cleanParams(params || {}), timeout: 15000 }).then((r) => r.data)

export const fetchTeam = (team, season) => get(`/api/v2/teams/${encodeURIComponent(team)}`, { season })
export const searchPlayers = ({ q, team, season, role }) => get('/api/v2/players/search', { q, team, season, role })
export const fetchProfile = (id) => get(`/api/v2/players/${encodeURIComponent(id)}/profile`)
/** 리그 비교 기준(그 시즌 전 선수). v1 /api/player-stats — 네이버 시즌 기록, 같은 열 이름. */
export const fetchLeague = (role, season) =>
  get('/api/player-stats', { role: role === 'batter' ? 'hitter' : 'pitcher', season }).then((d) => d.data || [])
/** P3-A 시즌 타자 고급 지표(규정 충족 타자) — 백분위 모집단. */
export const fetchBattingAdvanced = (season) =>
  get('/api/v2/batting/advanced', { season, qualified: true, limit: 200 }).then((d) => d.data || [])

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
    // P3-A: 프로필 advanced 에서 읽는 지표(adv). ISO 는 출처 값이 아니라 개수 기반 자체 계산값
    { key: 'iso', adv: 'iso', label: 'ISO', better: 'high', advanced: true },
    { key: 'babip', adv: 'babip', label: 'BABIP(계산)', better: 'high', advanced: true },
    { key: 'babip_source', adv: 'babip_source', label: 'BABIP(출처)', better: 'high', advanced: true },
    { key: 'bb_pct', adv: 'bb_pct', label: 'BB%', better: 'high', advanced: true },
    { key: 'k_pct', adv: 'k_pct', label: 'K%', better: 'low', advanced: true },
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

// ---------------------------------------------------------------- P3-A 타자 고급 지표 표시 규칙

/** 지표별 표시: ISO·BABIP 소수 3자리, BB%·K% 소수 1자리 + %. */
export const ADVANCED_FORMAT = { iso: { digits: 3 }, babip: { digits: 3 }, babip_source: { digits: 3 },
  bb_pct: { digits: 1, pct: true }, k_pct: { digits: 1, pct: true } }
/** 상태 → 화면 문구. 출처 값과 계산값은 같은 상태로 보이지 않는다. */
export const ADVANCED_STATUS = {
  calculated: '계산값', source: '출처 제공값(네이버) — 직접 계산 아님',
  unavailable: '계산 불가', zero_denominator: '분모 0 — 계산할 수 없음', missing: '고급 지표 자료 없음',
}
/** 백분위를 매기는 최소 모집단(같은 상태의 값 수). 이보다 적으면 백분위를 보이지 않는다. */
export const MIN_ADVANCED_POOL = 20

/** 지표 객체(API metrics.*) → {text, kind, note}. 계산 불가·분모 0 은 '-'(0 으로 보이지 않게), 사유는 note. */
export function fmtAdvanced(key, m) {
  if (!m) return { text: '-', kind: 'missing', note: ADVANCED_STATUS.missing }
  if (m.status === 'unavailable') return { text: '-', kind: 'unavailable', note: m.reason || ADVANCED_STATUS.unavailable }
  if (m.status === 'zero_denominator') return { text: '-', kind: 'zero_denominator', note: ADVANCED_STATUS.zero_denominator }
  const spec = ADVANCED_FORMAT[key] || { digits: 3 }
  const v = m.display ?? m.value
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return { text: '-', kind: 'unavailable', note: m.reason || ADVANCED_STATUS.unavailable }
  const n = Number(v).toFixed(spec.digits)
  const text = spec.pct ? `${n}%` : n.replace(/^0(?=\.)/, '')
  return { text, kind: m.status === 'source' ? 'source' : 'calculated',
    note: m.status === 'source' ? ADVANCED_STATUS.source : ADVANCED_STATUS.calculated }
}

/** 선수 시즌 줄의 고급 지표 하나(없으면 undefined). */
export const advancedOf = (line, key) => line?.advanced?.metrics?.[key]

/** 두 값을 직접 비교해도 되는가: 같은 시즌 · 같은 상태(계산값끼리 또는 출처 값끼리) · 값이 있음. */
export function comparableAdvanced(a, b, seasonA, seasonB) {
  return Boolean(a && b && seasonA === seasonB && a.status === b.status && ['calculated', 'source'].includes(a.status)
    && a.value !== null && b.value !== null)
}

/** 모집단: 같은 상태인 값만(계산값과 출처 값을 섞지 않는다). */
export function advancedPool(rows, key, status) {
  return rows.map((r) => r.metrics?.[key]).filter((m) => m && m.status === status && m.value !== null).map((m) => m.value)
}

/** 백분위 — 모집단이 MIN_ADVANCED_POOL 보다 작거나 값이 계산·출처 상태가 아니면 null. */
export function advancedPercentile(rows, key, m, better) {
  if (!m || !['calculated', 'source'].includes(m.status) || m.value === null) return null
  const pool = advancedPool(rows, key, m.status)
  return pool.length < MIN_ADVANCED_POOL ? null : percentile(pool, m.value, better)
}

// ---------------------------------------------------------------- 홈 '선수 BABIP 단순 평균'(P3-A 4단계)

/** 홈 리그 카드의 BABIP: 규정 충족(`규정충족` true) 타자의 출처(네이버) BABIP 를 선수 수로 나눈 **단순 평균**.
 *  타석 가중이 아니고, 값이 숫자가 아닌 선수는 뺀다. 리그 전체 BABIP(분자 합/분모 합)가 아니다. 대상이 없으면 NaN. */
export function qualifiedSimpleMean(rows, key) {
  const vals = (rows || []).filter((r) => r['규정충족'] === true).map((r) => r[key]).filter(Number.isFinite)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : NaN
}
export const PLAYER_MEAN_BABIP_NOTE = '선수 BABIP 단순 평균: 규정 타석을 채운 타자의 네이버 BABIP 값을 선수 수로 나눈 평균입니다(타석 수 가중 아님, 값이 없는 선수 제외). 리그 전체 BABIP가 아닙니다.'

// ---------------------------------------------------------------- 선수 비교 양방향 막대(1차 시각화)

/** 차트에 올리는 지표(COMPARE_METRICS 의 key). 출장량에 비례하는 누적 지표·WAR 는 수치표에만 둔다. */
export const CHART_METRICS = {
  batter: ['AVG', 'OBP', 'SLG', 'iso', 'bb_pct', 'k_pct', 'wRC+'],
  pitcher: ['ERA', 'WHIP', 'K/9', 'BB/9', 'K/BB'],
}

/** 역할의 차트 지표 정의(COMPARE_METRICS 순서·속성 그대로). */
export const chartMetrics = (role) => COMPARE_METRICS[role].filter((m) => CHART_METRICS[role].includes(m.key))

/** 한 선수·한 지표의 백분위와 그 계산에 실제로 쓴 모집단 수(n). 수치표와 같은 함수(percentile·advancedPercentile)를 그대로 부른다.
 *  pct 가 null 이면 reason 에 정확한 사유, short 에 차트용 짧은 문구('데이터 없음' = 값 자체가 없음, '비교 불가' = 값은 있으나
 *  백분위를 매길 수 없음)를 담는다 — 막대를 0 으로 그리지 않기 위해서다. */
export function metricPercentile(m, line, league, advLeague) {
  if (m.adv) {
    const v = advancedOf(line, m.adv)
    const usable = v && ['calculated', 'source'].includes(v.status) && v.value !== null
    const n = usable ? advancedPool(advLeague, m.adv, v.status).length : null
    const pct = advancedPercentile(advLeague, m.adv, v, m.better)
    const reason = pct !== null ? null
      : !usable ? fmtAdvanced(m.adv, v).note
        : `같은 상태 값 ${n}명 — ${MIN_ADVANCED_POOL}명 미만이라 백분위 없음`
    return { pct, n, reason, short: pct !== null ? null : usable ? '비교 불가' : '데이터 없음', text: fmtAdvanced(m.adv, v).text }
  }
  const pool = leaguePool(league, m.key)
  const raw = line?.stats?.[m.key]
  const pct = percentile(pool, raw, m.better)
  const reason = pct !== null ? null : toNumber(raw) === null ? '기록 없음' : '그 시즌 규정 충족 선수가 없어 백분위 없음'
  // 수치표(Stat)와 같은 형식 — 없는 값은 '-'
  return { pct, n: pool.length, reason, short: pct !== null ? null : toNumber(raw) === null ? '데이터 없음' : '비교 불가',
    text: fmtStat(raw, { rate: m.rate, digits: m.digits ?? null, unknown: '-' }) }
}

/** 수치표·차트의 우세 쪽('a' | 'b' | 'tie' | null). 고급 지표는 같은 시즌·같은 상태끼리만 우열을 표시한다. */
export function compareWinner(m, aLine, bLine, seasonA, seasonB) {
  if (!m.adv) return betterSide(aLine.stats[m.key], bLine.stats[m.key], m.better)
  const a = advancedOf(aLine, m.adv)
  const b = advancedOf(bLine, m.adv)
  return comparableAdvanced(a, b, seasonA, seasonB) ? betterSide(a.value, b.value, m.better) : null
}

/** 차트 아래 '백분위 없음' 사유 목록: 같은 사유끼리 묶어 [{reason, items: ['BB% — 오스틴 · 2026', ...]}]. 순서는 처음 나온 순.
 *  labels = [A 표시, B 표시] — 보통 '이름 · 시즌'. */
export function missingReasons(rows, labels) {
  const by = new Map()
  for (const { m, a, b } of rows) {
    for (const [s, label] of [[a, labels[0]], [b, labels[1]]]) {
      if (s.pct !== null) continue
      if (!by.has(s.reason)) by.set(s.reason, [])
      by.get(s.reason).push(`${m.label} — ${label}`)
    }
  }
  return [...by].map(([reason, items]) => ({ reason, items }))
}

/** 차트 행 aria-label: 색·위치 없이도 읽히게 값·백분위·우세를 문장으로. */
export function chartRowLabel(m, names, a, b, win) {
  const side = (name, s) => `${name} ${s.text}${s.pct === null ? ` (백분위 없음: ${s.reason})` : `, ${s.pct}백분위`}`
  const lead = win === 'a' ? `${names[0]} 우세` : win === 'b' ? `${names[1]} 우세` : win === 'tie' ? '같음' : '우세 판정 없음'
  return `${m.label}${m.better === 'low' ? '(낮을수록 좋음)' : ''}: ${side(names[0], a)} / ${side(names[1], b)} · ${lead}`
}
