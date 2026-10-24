// 투수·타자 리더보드. 설정은 URL 쿼리에 둔다(새로고침·공유해도 같은 화면).
//
// 순위 종류를 섞지 않는다:
//   - 규정타석 타율 순위: 시즌 누적 기록(v1 /api/player-stats, 규정충족 표시)으로 만든 공식 기준 순위
//   - 참고 순위: 박스스코어 합계에 최소 타수·이닝을 건 순위(/api/v2/leaders) — 공식 규정 순위가 아니다
//   - 규정이닝(투수): 팀 경기 수 × 1이닝을 박스스코어 경기 수로 계산한 순위
import { useRoute } from '../lib/useRoute'
import { updateQuery } from '../lib/navigation'
import { fetchLeaders, fetchSeasonHitters, fmtLeaderValue, intParam, kstInputToIso, LEADER_STATS,
  OFFICIAL_SOURCE_LABEL, CALC_SOURCE_LABEL, qualifiedBattingRanking, RATE_STATS, SEASON_SOURCE_LABEL } from '../lib/v2'
import { LoadState, PlayerLink, SourceLine, TimeControls, useV2 } from '../components/V2Bits'
import '../styles/V2.css'

const SEASONS = [2025]  // v2 데이터(박스스코어·계산)가 적재된 시즌
const PAGE = 20

function Leaders() {
  const { query } = useRoute()
  const season = intParam(query, 'season', SEASONS[0])
  const role = query.get('role') === 'batter' ? 'batter' : 'pitcher'
  const basis = query.get('basis') === 'calc' ? 'calc' : 'official'
  const stats = LEADER_STATS[role][basis]
  const stat = stats.some(([k]) => k === query.get('stat')) ? query.get('stat') : stats[0][0]
  const battingAvg = role === 'batter' && stat === 'avg'
  // 타율(박스스코어 기준)은 기본이 공식 규정타석 순위. 'reference' 를 고르면 최소 타수 참고 순위.
  const mode = battingAvg && basis === 'official' && query.get('rank') !== 'reference' ? 'qualified_pa' : 'v2'
  const minAb = intParam(query, 'min_ab', battingAvg ? 300 : 0)
  const minOuts = intParam(query, 'min_outs', 0)
  const qualified = role === 'pitcher' && basis === 'official' && query.get('qualified') !== '0' && RATE_STATS.has(stat)
  const offset = Math.max(0, intParam(query, 'offset', 0))
  const through = query.get('through') || null
  const asOfInput = query.get('asof') || ''

  const state = useV2(
    () => (mode === 'qualified_pa'
      ? fetchSeasonHitters(season).then((rows) => {
        const all = qualifiedBattingRanking(rows)
        return { leaders: all.slice(offset, offset + PAGE), total: all.length, criteria: null, meta: null }
      })
      : fetchLeaders({ season, role, stat, basis, minAb: role === 'batter' ? minAb : null,
        minOuts: role === 'pitcher' ? minOuts : null, qualified, throughDate: through, asOf: kstInputToIso(asOfInput),
        limit: PAGE, offset }).then((r) => ({ leaders: r.data.leaders, total: r.page.total, criteria: r.data.criteria,
        meta: r.meta }))),
    [mode, season, role, stat, basis, minAb, minOuts, qualified, through, asOfInput, offset],
  )
  const set = (values) => updateQuery({ offset: null, ...values })
  const body = state.data
  const isReference = mode === 'v2' && body?.criteria?.ranking === 'reference'
  const rankLabel = mode === 'qualified_pa' ? '순위' : isReference ? '참고 순위' : '순위(계산)'

  return (
    <div className="v2-page">
      <div className="v2-head">
        <h2>리더보드</h2>
        <div className="v2-controls">
          <select value={season} onChange={(e) => set({ season: e.target.value })} aria-label="시즌">
            {SEASONS.map((s) => <option key={s} value={s}>{s} 시즌</option>)}
          </select>
          <div className="v2-seg" role="group" aria-label="역할">
            {[['pitcher', '투수'], ['batter', '타자']].map(([k, label]) => (
              <button key={k} className={role === k ? 'on' : ''} aria-pressed={role === k}
                onClick={() => set({ role: k, stat: null, min_ab: null, min_outs: null, rank: null })}>{label}</button>
            ))}
          </div>
          <div className="v2-seg" role="group" aria-label="집계 기준">
            {[['official', '박스스코어'], ['calc', '자체 계산']].map(([k, label]) => (
              <button key={k} className={basis === k ? 'on' : ''} aria-pressed={basis === k}
                onClick={() => set({ basis: k, stat: null, rank: null })}>{label}</button>
            ))}
          </div>
          <select value={stat} onChange={(e) => set({ stat: e.target.value, rank: null })} aria-label="항목">
            {stats.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
          {battingAvg && basis === 'official' && (
            <div className="v2-seg" role="group" aria-label="순위 종류">
              {[['qualified', '규정타석 순위'], ['reference', '최소 타수 참고 순위']].map(([k, label]) => {
                const on = (k === 'qualified') === (mode === 'qualified_pa')
                return <button key={k} className={on ? 'on' : ''} aria-pressed={on}
                  onClick={() => set({ rank: k === 'qualified' ? null : 'reference' })}>{label}</button>
              })}
            </div>
          )}
          {role === 'batter' && mode === 'v2' && (
            <label className="v2-inline">최소 타수
              <input type="number" min="0" max="700" value={minAb} onChange={(e) => set({ min_ab: e.target.value })} />
            </label>
          )}
          {role === 'pitcher' && (
            <label className="v2-inline">최소 이닝(아웃)
              <input type="number" min="0" max="1000" value={minOuts} onChange={(e) => set({ min_outs: e.target.value })} />
            </label>
          )}
          {role === 'pitcher' && basis === 'official' && RATE_STATS.has(stat) && (
            <label className="v2-inline">
              <input type="checkbox" checked={qualified} onChange={(e) => set({ qualified: e.target.checked ? null : '0' })} />
              규정이닝
            </label>
          )}
        </div>
      </div>

      <div className="v2-note">
        {mode === 'qualified_pa' && '규정타석 타율 순위: 시즌 누적 기록에서 규정타석을 채운 선수만 순위를 매깁니다(공식 타격 순위 기준). '}
        {isReference && <b>참고 순위입니다 — 공식 규정타석·규정이닝 순위가 아닙니다. </b>}
        {mode === 'v2' && basis === 'official' && '박스스코어 기준: 경기별 네이버 박스스코어(KBO 공식 기록의 2차 출처) 합계입니다. KBO 원본으로 직접 검증한 값이 아닙니다.'}
        {basis === 'calc' && '자체 계산 기준: 투구 데이터로 계산한 값 중 확정된 선수만 순위에 넣습니다(미확정 경기가 있는 선수는 제외).'}
        {role === 'batter' && mode === 'v2' && ` 박스스코어에는 타석 수가 없어 규정타석을 판정할 수 없으므로 최소 타수(현재 ${minAb}타수)로만 거릅니다.`}
        {qualified && ' 규정이닝 = 소속 팀 경기 수 × 1이닝(가장 최근 경기의 팀, 기준 시점에 박스스코어를 가진 경기만 셈) — 박스스코어로 계산한 값입니다.'}
      </div>

      {mode === 'v2' && (
        <TimeControls asOfInput={asOfInput} throughDate={through} onChange={({ asof, through: t }) =>
          set(asof !== undefined ? { asof } : { through: t })} />
      )}
      {mode === 'qualified_pa' && <p className="v2-note">시즌 누적 기록은 시즌 최종 값입니다 — 기준 시점(as_of·through_date)을 적용하지 않습니다.</p>}

      <LoadState state={state} empty={body && !body.leaders.length ? '조건에 맞는 선수가 없습니다.' : null} />
      {body && body.leaders.length > 0 && (
        <div className="v2-table-wrap">
          <table className="v2-table">
            <thead>
              <tr><th>{rankLabel}</th><th className="lalign">선수</th><th className="lalign">팀</th><th>경기</th>
                <th>{stats.find(([k]) => k === stat)?.[1]}</th></tr>
            </thead>
            <tbody>
              {body.leaders.map((r) => (
                <tr key={r.player_id}>
                  <td>{r.rank}</td>
                  <td className="lalign"><PlayerLink id={r.player_id} name={r.name} season={season} role={role} /></td>
                  <td className="lalign">{r.team || '-'}</td>
                  <td>{r.games}</td>
                  <td className="v2-num">{fmtLeaderValue(stat, r.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {body && body.total > 0 && (
        <div className="v2-pager">
          <button disabled={offset === 0} onClick={() => updateQuery({ offset: Math.max(0, offset - PAGE) || null })}>이전</button>
          <span>{offset + 1}–{Math.min(offset + PAGE, body.total)} / {body.total}명</span>
          <button disabled={offset + PAGE >= body.total} onClick={() => updateQuery({ offset: offset + PAGE })}>다음</button>
        </div>
      )}
      {body?.criteria && (
        <p className="v2-foot">
          제외: 미확정 {body.criteria.excluded_not_exact}명 · 원본 팀 합계 불일치 {body.criteria.excluded_team_sum_mismatch}명
          · 값 누락 {body.criteria.excluded_missing_value ?? 0}명
        </p>
      )}
      <SourceLine label={mode === 'qualified_pa' ? SEASON_SOURCE_LABEL : basis === 'official' ? OFFICIAL_SOURCE_LABEL : CALC_SOURCE_LABEL}
        fetchedAt={body?.meta?.sources?.[0]?.fetched_at_max}
        extra="KBO 직접 검증 전" />
    </div>
  )
}

export default Leaders
