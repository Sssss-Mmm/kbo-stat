// 선수 상세: 시즌 합계(외부 기록 / 자체 계산 분리) · 검증 상태 · 경기 기록(서버 페이지) · 최근 경기 추세.
// P2-D: 시즌별 기록(네이버 시즌 기록, 2007–) — 박스스코어 자료가 없는 시즌에도 보인다.
import { useRoute } from '../lib/useRoute'
import { followLink, pageUrl, updateQuery } from '../lib/navigation'
import { advancedOf, COMPARE_METRICS, fetchProfile, latestCollected, NAVER_SEASON_LABEL, playerLabel, ROLE_LABEL } from '../lib/p2d'
import { CALC_SOURCE_LABEL, fetchPlayerGames, fetchPlayerSeason, inningsFromOuts, intParam, kstInputToIso,
  notFoundMessage, OFFICIAL_SOURCE_LABEL, playerGamesParams, recentTrend, verificationInfo } from '../lib/v2'
import { AdvancedLegend, AdvancedValue, GameLink, KboBadge, LoadState, SourceLine, Stat, TimeControls, useV2, VerificationBadge } from '../components/V2Bits'
import TrendLine from '../components/charts/TrendLine'
import '../styles/V2.css'

const PAGE = 15
const TREND_GAMES = 20
const OFFICIAL_COLS = {
  pitcher: [['outs', '이닝'], ['bf', '타자'], ['h', '피안타'], ['hr', '피홈런'], ['bb', '볼넷'], ['so', '삼진'], ['er', '자책']],
  batter: [['ab', '타수'], ['h', '안타'], ['hr', '홈런'], ['bb', '볼넷'], ['so', '삼진'], ['rbi', '타점'], ['sb', '도루']],
}
const CALC_COLS = {
  pitcher: [['outs', '이닝'], ['bf', '타자'], ['h', '피안타'], ['bb', '볼넷'], ['hbp', '사구'], ['so', '삼진']],
  batter: [['pa', '타석'], ['ab', '타수'], ['h', '안타'], ['hr', '홈런'], ['bb', '볼넷'], ['so', '삼진']],
}
// 경기 기록 표에 보여 줄 대조 항목(역할별 핵심 3개).
const SHOWN_METRICS = { pitcher: ['Outs', 'BF', 'SO'], batter: ['AB', 'H', 'BB'] }

function cell(col, value) {
  return col === 'outs' ? (inningsFromOuts(value) ?? <Stat value={null} />) : <Stat value={value} />
}

function SeasonCards({ role, block }) {
  const off = block.official
  const calc = block.calc
  return (
    <div className="v2-cards">
      <section className="v2-card">
        <h3>박스스코어 합계</h3>
        <p className="v2-card-sub">{OFFICIAL_SOURCE_LABEL}</p>
        {off ? (
          <>
            <dl className="v2-dl">
              <div><dt>경기</dt><dd>{off.games}</dd></div>
              {OFFICIAL_COLS[role].map(([k, label]) => <div key={k}><dt>{label}</dt><dd>{cell(k, off.totals[k])}</dd></div>)}
              {role === 'pitcher'
                ? <><div><dt>ERA</dt><dd><Stat value={off.rates.era} digits={2} unknown="-" /></dd></div>
                    <div><dt>WHIP</dt><dd><Stat value={off.rates.whip} digits={2} unknown="-" /></dd></div></>
                : <div><dt>타율</dt><dd><Stat value={off.rates.avg} rate unknown="-" /></dd></div>}
            </dl>
            {Object.keys(off.team_sum_mismatch_games || {}).length > 0 && (
              <p className="v2-warn">원본 팀 합계가 어긋난 경기 포함: {Object.entries(off.team_sum_mismatch_games)
                .map(([k, n]) => `${k} ${n}경기`).join(', ')}</p>
            )}
          </>
        ) : <p className="v2-empty">박스스코어 기록 없음</p>}
      </section>
      <section className="v2-card">
        <h3>자체 계산 합계</h3>
        <p className="v2-card-sub">{CALC_SOURCE_LABEL}</p>
        {calc ? (
          <>
            <dl className="v2-dl">
              <div><dt>경기</dt><dd>{calc.games}</dd></div>
              {CALC_COLS[role].map(([k, label]) => <div key={k}><dt>{label}</dt><dd>{cell(k, calc.totals[k])}</dd></div>)}
              {role === 'batter' && <div><dt>타율</dt><dd><Stat value={calc.rates.avg} rate /></dd></div>}
            </dl>
            {role === 'pitcher' && calc.totals.outs === null && (
              <p className="v2-warn">아웃 미확정 경기 {calc.games - calc.games_outs_complete}개 — 시즌 이닝은 미확정
                (확정분만 {inningsFromOuts(calc.outs_lower_bound)}이닝 이상)</p>
            )}
            {!calc.stats_exact && <p className="v2-warn">결과 불명 타석이 있어 일부 합계는 하한값이고 비율은 만들지 않습니다.</p>}
          </>
        ) : <p className="v2-empty">투구 데이터 계산 없음</p>}
      </section>
      <section className="v2-card">
        <h3>검증 상태</h3>
        <p className="v2-card-sub">경기별 자체 계산 ↔ 네이버 대조 건수</p>
        <ul className="v2-verify-list">
          {Object.entries(block.verification).map(([metric, counts]) => (
            <li key={metric}><b>{metric}</b>{' '}
              {Object.entries(counts).map(([s, n]) => <span key={s} className="v2-count">{verificationInfo(s).short} {n}</span>)}
            </li>
          ))}
        </ul>
        <KboBadge kbo={block.kbo} />
      </section>
    </div>
  )
}

function Trend({ role, games }) {
  const recent = games.slice(-TREND_GAMES)
  const t = recentTrend(recent, role)
  if (role === 'pitcher') {
    return (
      <div className="v2-trend">
        <h3>최근 {recent.length}경기 추세 (박스스코어)</h3>
        <TrendLine yLabel="경기별 이닝·삼진" xTickStep={5} fmt={(v) => v.toFixed(1)}
          series={[{ label: '이닝', color: 'var(--series-1)', points: t.innings },
            { label: '삼진', color: 'var(--series-2)', dash: '5 4', points: t.so }]} />
      </div>
    )
  }
  return (
    <div className="v2-trend">
      <h3>최근 {recent.length}경기 추세 (박스스코어)</h3>
      <TrendLine yLabel="누적 타율" xTickStep={5} fmt={(v) => v.toFixed(3).replace(/^0/, '')}
        series={[{ label: '누적 타율(구간)', color: 'var(--series-1)', points: t.avg }]} />
    </div>
  )
}

/** 시즌별 기록(P2-D). 박스스코어 시즌과 별개 출처라 따로 둔다. */
function SeasonHistory({ id, role, season }) {
  const state = useV2(() => fetchProfile(id), [id])
  const body = state.data?.data
  const roles = [...new Set((body?.seasons || []).map((s) => s.role))]
  const shown = roles.includes(role) ? role : roles[0]
  const rows = (body?.seasons || []).filter((s) => s.role === shown)
  const cols = [['G', '경기', {}], ...COMPARE_METRICS[shown || 'batter'].map((m) => [m.key, m.label, m])]
  return (
    <section>
      <h3 className="v2-section">시즌별 기록 {shown && <small className="v2-metric">{ROLE_LABEL[shown]}</small>}</h3>
      <LoadState state={state} empty={state.status === 404 ? '네이버 시즌 기록에 이 선수가 없습니다.' : null} />
      {body && (
        <>
          <p className="v2-note">{playerLabel(body.player)}{body.player.pitch_bat ? ` · ${body.player.pitch_bat}` : ''}
            {' · '}{roles.map((r) => (
              <a key={r} className="p2d-compare-link" href={pageUrl('compare', { role: r, a: id, sa: season })} onClick={followLink}>
                {ROLE_LABEL[r]} 비교</a>))}</p>
          <div className="v2-table-wrap">
            <table className="v2-table">
              <thead><tr><th className="lalign">시즌</th><th className="lalign">팀</th>
                {cols.map(([k, label]) => <th key={k}>{label}</th>)}</tr></thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.season} className={s.season === season ? 'p2d-current' : undefined}>
                    <td className="lalign">{s.season}</td>
                    <td className="lalign"><a href={pageUrl('team', { team: s.team, season: s.season })} onClick={followLink}>{s.team}</a></td>
                    {cols.map(([k, , m]) => (
                      <td key={k} className="v2-num">{m.adv ? <AdvancedValue metricKey={m.adv} m={advancedOf(s, m.adv)} />
                        : m.innings ? (s.stats[k] ?? <Stat value={null} />)
                          : <Stat value={s.stats[k]} rate={m.rate} digits={m.digits ?? null} />}</td>))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {shown === 'batter' && <AdvancedLegend />}
          <SourceLine label={NAVER_SEASON_LABEL} fetchedAt={latestCollected(state.data.meta.sources)} />
        </>
      )}
    </section>
  )
}

function PlayerV2() {
  const { query } = useRoute()
  const id = intParam(query, 'id')
  const season = intParam(query, 'season', 2025)
  const asOfInput = query.get('asof') || ''
  const through = query.get('through') || null
  const offset = Math.max(0, intParam(query, 'offset', 0))
  const asOf = kstInputToIso(asOfInput)

  const seasonState = useV2(() => (id ? fetchPlayerSeason(id, { season, throughDate: through, asOf }) : Promise.reject(new Error('id'))),
    [id, season, through, asOfInput])
  const roles = seasonState.data?.data.roles || {}
  const role = query.get('role') && roles[query.get('role')] ? query.get('role') : Object.keys(roles)[0] || 'pitcher'
  const gamesState = useV2(() => (id ? fetchPlayerGames(id, playerGamesParams({ season, role, asOf, through, limit: PAGE, offset }))
    : Promise.reject(new Error('id'))), [id, season, role, offset, asOfInput, through])
  const trendState = useV2(() => (id ? fetchPlayerGames(id, playerGamesParams({ season, role, asOf, through, limit: TREND_GAMES }))
    : Promise.reject(new Error('id'))), [id, season, role, asOfInput, through])  // 합계와 같은 기간(through_date)

  if (!id) return <div className="v2-page"><p className="v2-error">선수를 지정해 주세요(리더보드에서 선수를 고르세요).</p></div>
  if (seasonState.status === 404) {
    return (
      <div className="v2-page">
        <div className="v2-head"><h2>선수 <small>#{id}</small></h2><span className="v2-pill">{season} 시즌</span></div>
        <SeasonHistory id={id} role={query.get('role') === 'batter' ? 'batter' : query.get('role') === 'pitcher' ? 'pitcher' : null} season={season} />
        <h3 className="v2-section">박스스코어 경기 기록</h3>
        <TimeControls asOfInput={asOfInput} throughDate={through}
          onChange={({ asof, through: t }) => updateQuery(asof !== undefined ? { asof, offset: null } : { through: t })} />
        <p className="v2-empty">{notFoundMessage('player', asOf)} 박스스코어 경기 기록은 2025 시즌만 적재돼 있습니다 — {season} 시즌은 위 시즌별 기록만 있습니다.</p>
      </div>
    )
  }
  const player = seasonState.data?.data.player
  const page = gamesState.data?.page
  const games = gamesState.data?.data.games || []

  return (
    <div className="v2-page">
      <div className="v2-head">
        <h2>{player ? player.name : `선수 ${id}`} <small>#{id}</small></h2>
        <div className="v2-controls">
          {Object.keys(roles).length > 1 && (
            <div className="v2-seg" role="group" aria-label="역할">
              {Object.keys(roles).map((r) => (
                <button key={r} className={role === r ? 'on' : ''} aria-pressed={role === r}
                  onClick={() => updateQuery({ role: r, offset: null })}>{r === 'pitcher' ? '투수' : '타자'}</button>
              ))}
            </div>
          )}
          <span className="v2-pill">{season} 시즌</span>
        </div>
      </div>
      <TimeControls asOfInput={asOfInput} throughDate={through}
        onChange={({ asof, through: t }) => updateQuery(asof !== undefined ? { asof, offset: null } : { through: t })} />

      <LoadState state={seasonState} empty={seasonState.data && !Object.keys(roles).length ? '이 조건의 기록이 없습니다.' : null} />
      {roles[role] && <SeasonCards role={role} block={roles[role]} />}

      {trendState.data && <Trend role={role} games={[...trendState.data.data.games].reverse()} />}

      <SeasonHistory id={id} role={role} season={season} />

      <h3 className="v2-section">경기 기록</h3>
      <LoadState state={gamesState} empty={gamesState.data && !games.length ? '경기 기록이 없습니다.' : null} />
      {games.length > 0 && (
        <div className="v2-table-wrap">
          <table className="v2-table">
            <thead>
              <tr>
                <th className="lalign">날짜</th><th className="lalign">상대</th>
                {OFFICIAL_COLS[role].map(([k, label]) => <th key={k}>{label}</th>)}
                <th className="lalign">계산 이닝/타석</th><th className="lalign">검증</th>
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <tr key={`${g.game_id}-${g.role}`}>
                  <td className="lalign"><GameLink id={g.game_id}>{g.date}</GameLink></td>
                  <td className="lalign">{g.opponent || '-'}</td>
                  {OFFICIAL_COLS[role].map(([k]) => <td key={k} className="v2-num">{g.official ? cell(k, g.official[k]) : '-'}</td>)}
                  <td className="lalign">{g.calc ? (role === 'pitcher' ? cell('outs', g.calc.outs) : <Stat value={g.calc.pa} />) : '-'}</td>
                  <td className="lalign">
                    <span className="v2-badges">
                      {SHOWN_METRICS[role].map((m) => <span key={m} className="v2-metric">{m} <VerificationBadge status={g.verification[m]} /></span>)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {page && page.total > PAGE && (
        <div className="v2-pager">
          <button disabled={offset === 0} onClick={() => updateQuery({ offset: Math.max(0, offset - PAGE) || null })}>최근</button>
          <span>{offset + 1}–{Math.min(offset + PAGE, page.total)} / {page.total}경기</span>
          <button disabled={page.next_offset == null} onClick={() => updateQuery({ offset: page.next_offset })}>이전 경기</button>
        </div>
      )}
      <SourceLine label={OFFICIAL_SOURCE_LABEL} fetchedAt={seasonState.data?.meta?.sources?.[0]?.fetched_at_max}
        extra="자체 계산은 별도 표시" />
    </div>
  )
}

export default PlayerV2
