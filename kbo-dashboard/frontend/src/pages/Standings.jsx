// 순위표 페이지(P2-C). /api/v2/standings 로 경기 결과에서 다시 계산한 순위를 보여 주고, 원본 순위표와의 대조를 옆에 둔다.
// 시즌·날짜는 URL 쿼리(season, through) — 새로고침·공유해도 같은 화면. 표는 v1 StandingsTable 을 그대로 쓴다.
import StandingsTable from '../components/StandingsTable'
import { LoadState, SourceLine, useV2 } from '../components/V2Bits'
import { useRoute } from '../lib/useRoute'
import { updateQuery } from '../lib/navigation'
import { COVERAGE_TEXT, fetchSeasons, fetchStandingsV2, intParam, RANK_CHECK, SCHEDULE_SOURCE_LABEL,
  toStandingsTableRow } from '../lib/v2'
import '../styles/Standings.css'
import '../styles/V2.css'

function Standings({ onTeamClick }) {
  const { query } = useRoute()
  const seasons = useV2(fetchSeasons, [])
  const held = (seasons.data?.data || []).filter((s) => s.schedule).map((s) => s.season)
  const season = intParam(query, 'season', held.at(-1) ?? null)
  const through = query.get('through') || null
  const state = useV2(() => (season ? fetchStandingsV2(season, through) : Promise.resolve(null)), [season, through])
  const body = state.data
  const range = seasons.data?.data.find((s) => s.season === season)?.schedule

  return (
    <div className="standings-container v2-page">
      <div className="standings-header v2-head">
        <h2>{season ? `${season}시즌 순위표` : '순위표'}</h2>
        <div className="v2-controls">
          <select value={season ?? ''} onChange={(e) => updateQuery({ season: e.target.value, through: null })} aria-label="시즌">
            {[...held].reverse().map((s) => <option key={s} value={s}>{s} 시즌</option>)}
          </select>
          <label className="v2-inline">날짜까지
            <input type="date" value={through || ''} min={range?.first_date} max={range?.last_date}
              onChange={(e) => updateQuery({ through: e.target.value || null })} />
          </label>
          {through && <button className="v2-link-btn" onClick={() => updateQuery({ through: null })}>시즌 전체</button>}
        </div>
      </div>

      <LoadState state={seasons.loading ? seasons : state}
        empty={!seasons.loading && !held.length ? '순위를 계산할 일정 자료가 없습니다.' : null} />
      {body && (
        <>
          <p className="v2-note">
            {COVERAGE_TEXT[body.coverage]}
            {body.last_played_date && ` · 시즌 마지막 경기 ${body.last_played_date}`}
            {body.remaining_scheduled > 0 && ` · 남은 예정 경기 ${body.remaining_scheduled}`}
            {' '}· 포스트시즌 미포함
          </p>
          {body.data.some((r) => r.games > 0) && <StandingsTable data={body.data.map(toStandingsTableRow)} onTeamClick={(team) => onTeamClick?.(team, season)} />}
          {body.check_summary && (
            <p className="v2-note">
              <b>원본 순위표 대조</b>: 승·패·무·승률·승차·최근10·연속·홈·원정 {body.check_summary.teams - body.check_summary.record_mismatch}/{body.check_summary.teams}팀 일치
              {body.check_summary.record_mismatch > 0 && <b className="v2-warn-text"> · 불일치 {body.check_summary.record_mismatch}팀</b>}
            </p>
          )}
          {!body.check_summary && body.coverage === 'partial' && (
            <p className="v2-note">날짜 기준 순위는 원본 순위표(시즌 최종)와 비교하지 않습니다.</p>
          )}
          {body.check_summary && (
            <div className="v2-table-wrap">
              <table className="v2-table">
                <caption className="v2-caption">순위 대조 — 계산 순위(위 표)와 원본 순위표의 순위를 따로 보여 줍니다</caption>
                <thead><tr><th className="lalign">팀</th><th>계산 순위</th><th>원본 순위</th><th className="lalign">순위 검증</th>
                  <th className="lalign">기록 검증</th></tr></thead>
                <tbody>
                  {body.data.map((r) => (
                    <tr key={r.team}>
                      <td className="lalign">{r.team}{r.tie && <span className="v2-pill">동률</span>}</td>
                      <td>{r.rank}</td>
                      <td>{r.source?.rank ?? '-'}</td>
                      <td className="lalign v2-wrap">{r.check.rank ? RANK_CHECK[r.check.rank] : '원본 없음'}</td>
                      <td className="lalign">{r.check.status === 'match' ? '일치' : r.check.fields?.length
                        ? <span className="v2-warn-text">불일치: {r.check.fields.join(', ')}</span> : '원본 없음'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="v2-foot">
            순위 = 경기 결과로 계산한 정규시즌 승률 순(같은 승률은 같은 순위) · 승률 {body.rules.pct === 'wins/(wins+losses+draws)'
              ? '승 ÷ (승+패+무) — 2009·2010 시즌 규정(무승부를 패로 계산)' : '승 ÷ (승+패) — 무승부 제외'}
            {' '}· 소수 넷째 자리에서 반올림 · 승차는 승률 1위 기준
          </p>
          <SourceLine label={SCHEDULE_SOURCE_LABEL} fetchedAt={body.meta.sources[0]?.collected_at} />
        </>
      )}
    </div>
  )
}

export default Standings
