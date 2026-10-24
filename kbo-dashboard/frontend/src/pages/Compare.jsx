// 선수 비교(P2-D): 타자끼리·투수끼리. 선수마다 시즌을 따로 고를 수 있고(sa, sb), 리그 백분위는 각자 그 시즌의
// 규정 충족 선수를 기준으로 한다. 값은 네이버 시즌 기록. 박스스코어 자료가 있는 시즌(2025)은 그 검증 상태를 함께 보인다.
// URL 쿼리: role, a, b, sa, sb, metric.
import { useState } from 'react'
import TrendLine from '../components/charts/TrendLine'
import { AdvancedLegend, AdvancedValue, LoadState, SourceLine, Stat, useV2 } from '../components/V2Bits'
import { useRoute } from '../lib/useRoute'
import { followLink, pageUrl, updateQuery } from '../lib/navigation'
import { fetchPlayerSeason, fetchSeasons, intParam } from '../lib/v2'
import { advancedOf, advancedPercentile, betterSide, comparableAdvanced, COMPARE_METRICS, fetchBattingAdvanced, fetchLeague,
  fetchProfile, fmtAdvanced, latestCollected, leaguePool, MIN_ADVANCED_POOL, NAVER_SEASON_LABEL, percentile, playerLabel, ROLE_LABEL,
  searchPlayers, seasonLine, toNumber, verificationSummary } from '../lib/p2d'
import '../styles/V2.css'
import '../styles/P2D.css'

const SIDES = { a: 'var(--series-1)', b: 'var(--series-2)' }
const DEFAULT_METRIC = { batter: 'OPS', pitcher: 'ERA' }
// 추이: 계산값 지표는 계산값만, 출처 지표는 출처 값만 잇는다(상태가 섞이지 않게)
const trendValue = (m, key) => (m && m.status === (key === 'babip_source' ? 'source' : 'calculated') ? m.value : null)

function Picker({ side, role, onPick }) {
  const [q, setQ] = useState('')
  const state = useV2(() => (q.trim().length >= 1 ? searchPlayers({ q: q.trim(), role }) : Promise.resolve(null)), [q, role])
  return (
    <div className="p2d-picker">
      <input type="search" placeholder={`${side === 'a' ? '첫' : '두'} 번째 ${ROLE_LABEL[role]} 이름`} value={q} maxLength={30}
        aria-label={`${side.toUpperCase()} 선수 찾기`} onChange={(e) => setQ(e.target.value)} />
      {state.data && (
        <ul className="p2d-pick-list">
          {!state.data.data.length && <li className="v2-empty">없음</li>}
          {state.data.data.slice(0, 8).map((p) => (
            <li key={p.player_id}><button onClick={() => { setQ(''); onPick(p.player_id) }}>{playerLabel(p)}
              {p.same_name > 0 && <span className="v2-metric"> · ID {p.player_id}</span>}</button></li>
          ))}
        </ul>
      )}
    </div>
  )
}

function useSide(id, role, seasonParam, boxSeasons) {
  const profile = useV2(() => (id ? fetchProfile(id) : Promise.resolve(null)), [id])
  const mine = (profile.data?.data.seasons || []).filter((s) => s.role === role).map((s) => s.season)
  const season = seasonParam && mine.includes(seasonParam) ? seasonParam : mine[0] ?? null
  const league = useV2(() => (season ? fetchLeague(role, season) : Promise.resolve(null)), [role, season])
  // P3-A 고급 지표 백분위 모집단(그 시즌 규정 충족 타자) — 실패하면 백분위만 비운다
  const advLeague = useV2(() => (season && role === 'batter' ? fetchBattingAdvanced(season).catch(() => []) : Promise.resolve([])),
    [role, season])
  const hasBox = season !== null && boxSeasons.includes(season)
  const box = useV2(() => (id && hasBox ? fetchPlayerSeason(id, { season }).catch((e) => (e?.response?.status === 404 ? null : Promise.reject(e)))
    : Promise.resolve(null)), [id, season, hasBox])
  return { id, profile, seasons: mine, season, line: seasonLine(profile.data, season, role), league: league.data || [], hasBox,
    advLeague: advLeague.data || [],
    verification: verificationSummary(box.data, role) }
}

function VerifyLine({ side, role }) {
  if (!side.line) return null
  if (!side.hasBox) return <p className="v2-note">{side.season} 검증 정보 없음 — 네이버 시즌 기록 값만(다른 출처와 교차 대조하지 않음)</p>
  const v = side.verification
  if (!v) return <p className="v2-note">{side.season} 박스스코어에 이 선수의 {ROLE_LABEL[role]} 기록이 없습니다.</p>
  return (
    <p className="v2-note">
      {side.season} 박스스코어 경기 기록 검증(투구 데이터 대조): {v.items}개 항목 중 일치 {v.agree}
      {v.conflict > 0 && <b> · 불일치 {v.conflict}</b>}{v.other > 0 && ` · 대조 불가 ${v.other}`}
      {' '}(한 경기라도 다르면 그 항목은 불일치) · KBO 원본 대조 전.
      {' '}표의 시즌 값(네이버 시즌 기록)과는 다른 출처입니다.
    </p>
  )
}

function Compare() {
  const { query } = useRoute()
  const role = query.get('role') === 'pitcher' ? 'pitcher' : 'batter'
  const metrics = COMPARE_METRICS[role]
  const metricKey = metrics.some((m) => m.key === query.get('metric')) ? query.get('metric') : DEFAULT_METRIC[role]
  const seasonsInfo = useV2(fetchSeasons, [])
  const boxSeasons = (seasonsInfo.data?.data || []).filter((s) => s.box_games > 0).map((s) => s.season)
  const A = useSide(intParam(query, 'a'), role, intParam(query, 'sa'), boxSeasons)
  const B = useSide(intParam(query, 'b'), role, intParam(query, 'sb'), boxSeasons)
  const sides = { a: A, b: B }
  const metric = metrics.find((m) => m.key === metricKey)
  const pct = (side, m) => (m.adv ? advancedPercentile(side.advLeague, m.adv, advancedOf(side.line, m.adv), m.better)
    : percentile(leaguePool(side.league, m.key), side.line?.stats[m.key], m.better))
  // 고급 지표는 같은 시즌·같은 상태끼리만 우열을 표시한다
  const winner = (m) => {
    if (!m.adv) return betterSide(A.line.stats[m.key], B.line.stats[m.key], m.better)
    const a = advancedOf(A.line, m.adv)
    const b = advancedOf(B.line, m.adv)
    return comparableAdvanced(a, b, A.season, B.season) ? betterSide(a.value, b.value, m.better) : null
  }

  return (
    <div className="v2-page p2d-compare">
      <div className="v2-head">
        <h2>선수 비교 <small>{ROLE_LABEL[role]}</small></h2>
        <div className="v2-seg">
          {['batter', 'pitcher'].map((r) => (
            <button key={r} className={role === r ? 'on' : ''} onClick={() => updateQuery({ role: r, a: null, b: null, sa: null, sb: null, metric: null })}>
              {ROLE_LABEL[r]}</button>))}
        </div>
      </div>

      <section className="p2d-sides">
        {Object.entries(sides).map(([k, side]) => (
          <div className="v2-card" key={k} style={{ borderTop: `4px solid ${SIDES[k]}` }}>
            {!side.id && <Picker side={k} role={role} onPick={(id) => updateQuery({ [k]: id, [`s${k}`]: null })} />}
            {side.id && (
              <>
                <LoadState state={side.profile} empty={side.profile.status === 404 ? '선수 기록이 없습니다.' : null} />
                {side.profile.data && (
                  <>
                    <h3>
                      <a href={pageUrl('player', { id: side.id, season: side.season, role })} onClick={followLink}>
                        {playerLabel(side.profile.data.data.player)}</a>
                    </h3>
                    <div className="v2-controls">
                      <select value={side.season ?? ''} aria-label={`${k.toUpperCase()} 시즌`}
                        onChange={(e) => updateQuery({ [`s${k}`]: e.target.value })}>
                        {side.seasons.map((s) => <option key={s} value={s}>{s} 시즌</option>)}
                      </select>
                      <button className="v2-link-btn" onClick={() => updateQuery({ [k]: null, [`s${k}`]: null })}>다른 선수</button>
                    </div>
                    {!side.seasons.length && <p className="v2-empty">{ROLE_LABEL[role]} 기록이 없습니다.</p>}
                    {side.line && <p className="v2-card-sub">{side.season} {side.line.team} · {side.line.position || ROLE_LABEL[role]}
                      {side.line.qualified === true ? ' · 규정 충족' : side.line.qualified === false ? ' · 규정 미달' : ''}</p>}
                    <VerifyLine side={side} role={role} />
                  </>
                )}
              </>
            )}
          </div>
        ))}
      </section>

      {A.line && B.line && (
        <>
          <section className="p2d-section">
            <h3 className="v2-section">시즌 기록과 리그 백분위</h3>
            <p className="v2-note">백분위 = 그 선수 시즌의 규정 충족 선수 중 이 값보다 나쁘거나 같은 선수 비율(100에 가까울수록 좋음). 값이 없으면 '미확정'이고 백분위를 매기지 않습니다.</p>
            <div className="v2-table-wrap">
              <table className="v2-table p2d-cmp">
                <thead><tr><th className="lalign">지표</th><th>{A.profile.data.data.player.name} ({A.season})</th><th className="lalign">백분위</th>
                  <th>{B.profile.data.data.player.name} ({B.season})</th><th className="lalign">백분위</th></tr></thead>
                <tbody>
                  {metrics.map((m) => {
                    const win = winner(m)
                    return (
                      <tr key={m.key}>
                        <td className="lalign">{m.label}{m.advanced && <span className="v2-metric"> 고급</span>}</td>
                        {['a', 'b'].map((k) => {
                          const side = sides[k]
                          const p = pct(side, m)
                          return [
                            <td key={`${k}v`} className={win === k ? 'p2d-win' : undefined}>
                              {m.adv ? <AdvancedValue metricKey={m.adv} m={advancedOf(side.line, m.adv)} showNote />
                                : m.innings ? (side.line.stats[m.key] ?? <Stat value={null} />)
                                  : <Stat value={side.line.stats[m.key]} rate={m.rate} digits={m.digits ?? null} />}
                            </td>,
                            <td key={`${k}p`} className="lalign">
                              {p === null ? <span className="v2-unknown">-</span> : (
                                <span className="p2d-pct" title={`${p}백분위`}>
                                  <span className="p2d-bar"><span style={{ width: `${p}%`, background: SIDES[k] }} /></span><em>{p}</em>
                                </span>
                              )}
                            </td>,
                          ]
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="v2-foot">리그 기준: {A.season} 규정 충족 {leaguePool(A.league, metrics[0].key).length}명
              {B.season !== A.season && ` · ${B.season} 규정 충족 ${leaguePool(B.league, metrics[0].key).length}명`}</p>
            {role === 'batter' && (
              <>
                <p className="v2-note">고급 지표(ISO·BABIP·BB%·K%)는 <b>같은 시즌·같은 상태</b>(계산값끼리 또는 출처 값끼리)일 때만 우세를 굵게 표시합니다.
                  {' '}백분위는 그 시즌 규정 충족 타자 중 같은 상태의 값이 {MIN_ADVANCED_POOL}명 이상일 때만 매깁니다 — 적으면 '-'.
                  {' '}BABIP(계산)은 희생플라이 자료가 있는 경우(2025 투구 데이터 완결 선수)만, BB%·K% 는 타석 수가 확인된 선수만 계산합니다.</p>
                <AdvancedLegend />
              </>
            )}
          </section>

          <section className="p2d-section">
            <div className="v2-head">
              <h3 className="v2-section">시즌별 추이</h3>
              <select value={metricKey} onChange={(e) => updateQuery({ metric: e.target.value })} aria-label="추이 지표">
                {metrics.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>
            <TrendLine yLabel={metric.label} xTickStep={2}
              fmt={(v) => (metric.adv ? fmtAdvanced(metric.adv, { status: 'calculated', value: v, display: v }).text
                : metric.rate ? v.toFixed(3).replace(/^0/, '') : metric.digits ? v.toFixed(metric.digits) : Math.round(v))}
              series={['a', 'b'].map((k) => ({
                label: sides[k].profile.data.data.player.name, color: SIDES[k], dash: k === 'b' ? '6 4' : undefined,
                points: sides[k].profile.data.data.seasons.filter((s) => s.role === role)
                  .map((s) => ({ x: s.season, y: metric.adv ? trendValue(advancedOf(s, metric.adv), metric.adv) : toNumber(s.stats[metric.key]) }))
                  .filter((p) => p.y !== null),
              }))} />
            <p className="v2-foot">기록이 없는 시즌은 0 으로 그리지 않고 건너뜁니다 — 앞뒤 시즌을 직선으로 잇습니다.</p>
          </section>
        </>
      )}
      {(A.id || B.id) && !(A.line && B.line) && !A.profile.loading && !B.profile.loading && (
        <p className="v2-empty">두 선수를 모두 고르면 비교가 보입니다.</p>
      )}

      <SourceLine label={NAVER_SEASON_LABEL}
        fetchedAt={latestCollected([...(A.profile.data?.meta.sources || []), ...(B.profile.data?.meta.sources || [])])}
        extra="리그 백분위도 같은 자료(/api/player-stats)" />
    </div>
  )
}

export default Compare
