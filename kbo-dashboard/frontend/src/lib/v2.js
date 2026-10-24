// /api/v2 (출처·수집 시각·검증 상태를 함께 주는 통계 API) 클라이언트와 표시 규칙.
//
// 표시 원칙(P2-B):
//   - 외부 기록(official = 네이버 박스스코어, KBO 공식 기록의 2차 출처)과 자체 계산(calc = 투구 데이터)을 섞지 않는다.
//   - 미확정 계산값(null)은 0 으로 바꾸지 않는다 — '미확정' 으로 보인다.
//   - kbo.status 가 'kbo_verified' 가 아니면 KBO 직접 검증 완료로 보이지 않는다(현재 전부 not_checked).
//   - 이닝은 정수 아웃에서 1/3 단위로 만든다(17 → '5 2/3').
import axios from 'axios'

/**
 * @typedef {'observed_naver_match'|'observed_naver_conflict'|'naver_verified'|'naver_conflict'|
 *           'naver_unusable'|'calc_missing'|'naver_missing'|'unverified'} VerificationStatus
 * @typedef {{status: 'not_checked'|'kbo_verified'|'kbo_conflict'}} KboStatus
 * @typedef {{source: string, kind: string, note?: string, raw_files?: number, fetched_at_min?: string|null,
 *            fetched_at_max?: string|null, build_id?: string|null, calc_rule?: string|null, loaded_at?: string|null}} MetaSource
 * @typedef {{season: number, as_of: string|null, generated_at: string, sources: MetaSource[],
 *            collection_policy: Record<string,string>, kbo_direct_verification: 'available'|'not_available',
 *            reference_data: 'current_unversioned',
 *            through_date?: string|null}} Meta
 * @typedef {{source: string, fetched_at: string|null, raw_file: string|null, [stat: string]: any}} OfficialLine
 * @typedef {{outs?: number|null, outs_complete?: boolean, pa_complete?: boolean, stats_complete?: boolean,
 *            ip_from_outs?: string|null, [stat: string]: any}} CalcLine
 * @typedef {{player_id: number, name: string, side: 'away'|'home'|null, team: string|null,
 *            official: OfficialLine|null, calc: CalcLine|null,
 *            verification: Record<string, VerificationStatus>, kbo: KboStatus}} BoxPlayer
 * @typedef {{data: {game: {game_id: string, date: string, dh: number, away: string, home: string,
 *            score: {away: number|null, home: number|null}|null, status: string|null, ballpark: string|null},
 *            official: {source: string, fetched_at: string, raw_file: string,
 *                       team_sum_mismatch: Record<string,string[]>}|null,
 *            pitchers: BoxPlayer[], batters: BoxPlayer[],
 *            exceptions: {kind: string, role: string|null, player_id: number|null, player: string, count: number, detail: string}[],
 *            kbo: KboStatus}, meta: Meta}} BoxResponse
 * @typedef {{limit: number, offset: number, total: number, next_offset: number|null, sort?: string}} Page
 * @typedef {BoxPlayer & {game_id: string, date: string, role: 'pitcher'|'batter', opponent: string|null,
 *            home_away: string|null}} GameLogRow
 * @typedef {{data: {player: {player_id: number, name: string, names: {name: string, source: string}[]},
 *            games: GameLogRow[]}, page: Page, meta: Meta}} PlayerGamesResponse
 * @typedef {{official: {source: string, games: number, totals: Record<string, number|string|null>,
 *              rates: Record<string, number|null>, team_sum_mismatch_games: Record<string, number>}|null,
 *            calc: {calc_rule: string, games: number, games_stats_complete: number, stats_exact: boolean,
 *              totals: Record<string, number|null>, rates: Record<string, number|null>,
 *              games_outs_complete?: number, outs_lower_bound?: number}|null,
 *            verification: Record<string, Partial<Record<VerificationStatus, number>>>, kbo: KboStatus}} SeasonRole
 * @typedef {{data: {player: {player_id: number, name: string, names: {name: string, source: string}[]},
 *            through_date: string|null, roles: {pitcher?: SeasonRole, batter?: SeasonRole}}, meta: Meta}} PlayerSeasonResponse
 * @typedef {{rank: number, player_id: number, name: string, team: string|null, games: number,
 *            value: number, complete: boolean}} Leader
 * @typedef {{data: {leaders: Leader[], criteria: {basis: string, stat: string, order: 'asc'|'desc',
 *            min_outs: number, min_ab: number, qualified: boolean, qualification_rule: string|null,
 *            excluded_not_exact: number, excluded_team_sum_mismatch: number, excluded_missing_value: number}},
 *            page: Page, meta: Meta}} LeadersResponse
 */

const TIMEOUT = 15000

/** null·빈 문자열·false 가 아닌 값만 쿼리로 보낸다(서버 기본값을 그대로 쓰게). */
export function cleanParams(params) {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== false))
}

const get = (url, params) => axios.get(url, { params: cleanParams(params || {}), timeout: TIMEOUT }).then((r) => r.data)

/** @returns {Promise<BoxResponse>} */
export const fetchBox = (gameId, { asOf } = {}) => get(`/api/v2/games/${encodeURIComponent(gameId)}/box`, { as_of: asOf })
/** @returns {Promise<PlayerGamesResponse>} */
export const fetchPlayerGames = (playerId, params) =>
  get(`/api/v2/players/${encodeURIComponent(playerId)}/games`, {
    season: params.season, role: params.role, date_from: params.dateFrom, date_to: params.dateTo,
    limit: params.limit, offset: params.offset, sort: params.sort, as_of: params.asOf,
  })
/** @returns {Promise<PlayerSeasonResponse>} */
export const fetchPlayerSeason = (playerId, params) =>
  get(`/api/v2/players/${encodeURIComponent(playerId)}/season`, {
    season: params.season, role: params.role, through_date: params.throughDate, as_of: params.asOf,
  })
/** @returns {Promise<LeadersResponse>} */
export const fetchLeaders = (params) =>
  get('/api/v2/leaders', {
    season: params.season, role: params.role, stat: params.stat, basis: params.basis,
    min_outs: params.minOuts, min_ab: params.minAb, qualified: params.qualified,
    through_date: params.throughDate, as_of: params.asOf, limit: params.limit, offset: params.offset,
  })
export const fetchDataQuality = (season, { asOf } = {}) => get('/api/v2/data-quality', { season, as_of: asOf })

/** 시즌 누적 타자 기록(v1 /api/player-stats — 네이버 시즌 기록). 공식 규정타석 순위에 쓴다. */
export const fetchSeasonHitters = (season) =>
  axios.get('/api/player-stats', { params: { role: 'hitter', season }, timeout: TIMEOUT }).then((r) => r.data.data || [])

export const SEASON_SOURCE_LABEL = '네이버 시즌 누적 기록 (KBO 공식 기록의 2차 출처) · 규정타석 충족 표시 기준'

/**
 * 공식 규정타석 타율 순위: 시즌 기록의 규정충족 선수만, 타율 내림차순, 같은 타율은 같은 순위.
 * (박스스코어 합계로는 타석 수를 몰라 규정타석을 판정할 수 없다 — 그쪽은 '참고 순위'.)
 */
export function qualifiedBattingRanking(rows) {
  const eligible = rows
    .filter((r) => r['규정충족'] === true && Number.isFinite(Number(r.AVG)) && r.AVG !== null)
    .sort((a, b) => Number(b.AVG) - Number(a.AVG) || Number(a.PlayerId) - Number(b.PlayerId))
  let rank = 0
  let prev = null
  return eligible.map((r, i) => {
    const value = Math.round(Number(r.AVG) * 1000) / 1000  // 화면 표기(.337) 기준으로 동률 판정
    if (value !== prev) { rank = i + 1; prev = value }
    return { rank, player_id: Number(r.PlayerId), name: r['선수명'], team: r['팀명'], games: r.G, value }
  })
}

// ---------- 표시 ----------

export const UNKNOWN = '미확정'

/** 정수 아웃 → 1/3 단위 이닝. null(미확정)은 null 그대로. */
export function inningsFromOuts(outs) {
  if (outs === null || outs === undefined || !Number.isFinite(Number(outs))) return null
  const n = Math.trunc(Number(outs))
  const whole = Math.trunc(n / 3)
  const frac = n % 3
  return frac ? `${whole} ${frac}/3` : String(whole)
}

/** 숫자 칸 표시. null 은 0 이 아니라 '미확정'(또는 지정한 문구). */
export function fmtStat(value, { unknown = UNKNOWN, digits = null, rate = false } = {}) {
  if (value === null || value === undefined || value === '') return unknown
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  if (rate) return n.toFixed(3).replace(/^0/, '')
  return digits === null ? n.toLocaleString('ko-KR') : n.toFixed(digits)
}

export const VERIFICATION = {
  observed_naver_match: { label: '투구 데이터 입증 · 네이버 일치', short: '일치', tone: 'ok' },
  observed_naver_conflict: { label: '투구 데이터 입증 · 네이버와 다름', short: '불일치', tone: 'warn' },
  naver_verified: { label: '계산 미확정 · 네이버 값과 같음', short: '네이버 일치', tone: 'info' },
  naver_conflict: { label: '계산 미확정 · 네이버 값과 다름', short: '네이버 다름', tone: 'warn' },
  naver_unusable: { label: '네이버 원본 팀 합계 불일치 — 비교 기준 제외', short: '원본 불일치', tone: 'warn' },
  calc_missing: { label: '투구 데이터에 없음(대주자·대수비 등)', short: '계산 없음', tone: 'muted' },
  naver_missing: { label: '네이버 박스스코어에 없음', short: '네이버 없음', tone: 'muted' },
  unverified: { label: '대조할 외부 기록 없음', short: '대조 전', tone: 'muted' },
}

/** @param {string|undefined} status */
export function verificationInfo(status) {
  return VERIFICATION[status] || { label: '대조 결과 없음', short: '—', tone: 'muted' }
}

/** KBO 직접 검증 표기. 'kbo_verified' 가 아니면 절대 '검증 완료' 라고 하지 않는다. */
export function kboLabel(kbo) {
  if (kbo?.status === 'kbo_verified') return 'KBO 원본 직접 검증 일치'
  if (kbo?.status === 'kbo_conflict') return 'KBO 원본과 다름'
  return 'KBO 직접 검증 전'
}

export const OFFICIAL_SOURCE_LABEL = '네이버 박스스코어 (KBO 공식 기록의 2차 출처)'
export const CALC_SOURCE_LABEL = '자체 계산 (네이버 문자중계 투구 데이터)'

export const TIME_HELP = {
  asOf: '데이터 확보 시점: 이 시각까지 시스템이 실제로 수집·적재해 둔 자료만 씁니다. 나중에 백필한 자료는 그 이전 시점에 없던 것으로 봅니다.',
  throughDate: '경기 날짜 기준: 이 날짜까지 열린 경기만 합산합니다(수집 시점과 무관).',
}

export const LEADER_STATS = {
  pitcher: {
    official: [['era', 'ERA'], ['whip', 'WHIP'], ['so', '삼진'], ['outs', '이닝'], ['h', '피안타'], ['bb', '볼넷'],
      ['hr', '피홈런'], ['er', '자책'], ['bf', '상대 타자']],
    calc: [['so', '삼진'], ['outs', '이닝'], ['h', '피안타'], ['bb', '볼넷'], ['hbp', '사구'], ['bf', '상대 타자']],
  },
  batter: {
    official: [['avg', '타율'], ['h', '안타'], ['hr', '홈런'], ['rbi', '타점'], ['r', '득점'], ['sb', '도루'],
      ['bb', '볼넷'], ['so', '삼진'], ['ab', '타수']],
    calc: [['avg', '타율'], ['h', '안타'], ['hr', '홈런'], ['b2', '2루타'], ['bb', '볼넷'], ['so', '삼진'], ['pa', '타석']],
  },
}
export const RATE_STATS = new Set(['era', 'whip', 'avg'])

/** 리더 값 표시: 이닝은 아웃→1/3, 비율은 자리수. */
export function fmtLeaderValue(stat, value) {
  if (stat === 'outs') return inningsFromOuts(value) ?? UNKNOWN
  if (stat === 'avg') return fmtStat(value, { rate: true })
  if (stat === 'era' || stat === 'whip') return fmtStat(value, { digits: 2 })
  return fmtStat(value)
}

/** 대조 예외 종류(verify.exception.kind) → 화면 문구. */
export const EXCEPTION_LABEL = {
  called_game: '콜드·이닝 도중 종료', tie: '무승부', walkoff: '끝내기', team_sum_mismatch: '원본 팀 합계 불일치',
  auto_ibb_no_pitch: '자동 고의4구(투구 없음)', pinch_runner: '대주자', defensive_sub: '대수비·교체',
  pitcher_batting_slot: '타순의 투수', pinch_hitter_no_pa: '타석 없는 대타', pitcher_no_pitch: '투구 없는 투수',
  observed_conflict_auto_ibb: '자동 고의4구로 인한 불일치', observed_conflict_other: '원인 미상 불일치',
  no_boxscore: '박스스코어 없음', no_pitch_data: '투구 데이터 없음', no_pitch_rows: '투구 행 없음',
  not_in_boxscore: '박스스코어에 없는 선수',
}

// ---------- 추세 ----------

/**
 * 최근 경기 추세 점. 외부 기록(official) 기준 — 계산값과 섞지 않는다.
 * 투수: 경기별 이닝(아웃/3)과 삼진. 타자: 경기별 안타, 누적 타율(경기 순서대로).
 * 외부 기록이 없는 경기는 건너뛴다(0 으로 메우지 않는다).
 * @param {GameLogRow[]} games 날짜 오름차순
 */
export function recentTrend(games, role) {
  const rows = games.filter((g) => g.role === role && g.official)
  if (role === 'pitcher') {
    return {
      innings: rows.map((g, i) => ({ x: i + 1, y: g.official.outs == null ? NaN : g.official.outs / 3, date: g.date })),
      so: rows.map((g, i) => ({ x: i + 1, y: g.official.so ?? NaN, date: g.date })),
    }
  }
  let h = 0
  let ab = 0
  const avg = []
  rows.forEach((g, i) => {
    if (g.official.h == null || g.official.ab == null) return  // 모르는 경기는 누적에 넣지 않는다
    h += g.official.h
    ab += g.official.ab
    avg.push({ x: i + 1, y: ab ? h / ab : NaN, date: g.date })
  })
  return { hits: rows.map((g, i) => ({ x: i + 1, y: g.official.h ?? NaN, date: g.date })), avg }
}

/** 선수 경기 기록 요청 인자. 시즌 합계와 같은 기간이 되도록 through_date 를 date_to 로 넘긴다. */
export function playerGamesParams({ season, role, asOf, through, limit, offset = 0 }) {
  return { season, role, sort: '-date', limit, offset, asOf, dateTo: through || null }
}

/** 404 를 사람이 읽을 문구로. 기준 시점(as_of)이 있으면 '그때는 확보하지 않았다'와 '없다'를 구분한다. */
export function notFoundMessage(kind, asOf) {
  const what = kind === 'game' ? '이 경기' : '이 선수'
  return asOf
    ? `기준 시점(as_of)에는 ${what}의 기록을 아직 확보하지 않았습니다 — 나중에 수집한 자료는 그 이전 시점에 없던 것으로 봅니다.`
    : `${what}의 v2 기록을 찾지 못했습니다(적재된 시즌·ID 를 확인해 주세요).`
}

/** URL 쿼리에서 숫자를 안전하게(없거나 숫자가 아니면 fallback). */
export function intParam(query, key, fallback = null) {
  const raw = query.get(key)
  if (raw === null || raw.trim() === '') return fallback
  const n = Number(raw)
  return Number.isInteger(n) ? n : fallback
}

/** datetime-local 입력('2026-10-24T09:00') → 서버가 요구하는 시간대 포함 ISO(KST +09:00). 빈 값은 null. */
export function kstInputToIso(value) {
  if (!value) return null
  const withSeconds = /T\d{2}:\d{2}$/.test(value) ? `${value}:00` : value
  return `${withSeconds}+09:00`
}

/** ISO 시각 → 'YYYY-MM-DD HH:MM KST'. */
export function fmtKst(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const kst = new Date(d.getTime() + 9 * 3600 * 1000)
  return `${kst.toISOString().slice(0, 16).replace('T', ' ')} KST`
}

// ---------- P2-C: 시즌·일정·순위·홈 (KBO 공식 사이트 수집분, 수집 중단) ----------

export const fetchSeasons = () => get('/api/v2/seasons')
export const fetchSchedule = ({ date, season, month }) => get('/api/v2/schedule', { date, season, month })
export const fetchStandingsV2 = (season, throughDate) => get('/api/v2/standings', { season, through_date: throughDate })
export const fetchHome = (season) => get('/api/v2/home', { season })

export const SCHEDULE_SOURCE_LABEL = 'KBO 공식 사이트 수집 기록 · 수집 중단 · 외부 공개 전(이용 권한 확인 중)'

export const GAME_STATUS = { final: '종료', tie: '무승부', canceled: '취소', scheduled: '예정' }

// 빈 일정의 이유 — '경기 없음'과 '자료 없음'을 섞지 않는다.
export function emptyScheduleMessage(reason, range) {
  if (reason === 'no_games') return '이 날은 경기가 없습니다.'
  if (reason === 'season_not_held') return '이 시즌의 일정 자료가 없습니다.'
  if (reason === 'out_of_range') {
    return `보유 자료 범위 밖입니다${range ? ` (${range.first_date} ~ ${range.last_date} 정규시즌)` : ''} — 포스트시즌·이후 일정은 수집하지 않았습니다.`
  }
  return null
}

export const COVERAGE_TEXT = {
  season_final: '정규시즌 전체 경기 결과로 계산',
  partial: '선택한 날짜까지 끝난 경기만으로 계산',
  after_last_played: '보유 자료의 마지막 경기까지 계산 — 그 뒤 경기는 자료가 없습니다',
  before_first_game: '선택한 날짜에는 아직 끝난 경기가 없습니다',
}

export const RANK_CHECK = {
  match: '일치',
  tie_resolved_by_source: '승률 동률 — 원본 순위(상대전적·순위 결정전)를 따름',
  differs: '정규시즌 승률 순서와 다름 — 사유 미확정(원본 순위에 포스트시즌 결과가 반영됐을 가능성이 있으나, 포스트시즌 자료가 없어 확인하지 못함)',
}

// /api/v2/standings 행 → StandingsTable(v1 표) 행 모양. 순위는 계산 순위, 원본 순위는 따로 둔다.
export const toStandingsTableRow = (r) => ({
  rank: r.rank, team: r.team, games: r.games, wins: r.wins, losses: r.losses, draws: r.draws, win_rate: r.pct,
  games_behind: r.games_behind, last_10_games: r.last10, streak: r.streak, home_record: r.home, away_record: r.away,
})

export const dateOnly = (iso) => (iso ? String(iso).slice(0, 10) : null)
