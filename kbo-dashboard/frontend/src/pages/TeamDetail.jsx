// 팀 상세(P2-D): 시즌 팀 기록 · 홈/원정 · 최근 10경기 · 주요 타자·투수 · 그 시즌 출전 선수.
// 팀·시즌은 URL 쿼리(team, season). 기록·경기는 P2-C 순위·일정(2001–), 선수는 네이버 시즌 기록(2007–, 선수 ID 있음)
// — 그 이전 시즌은 KBO 기록실 규정 이상 선수 이름만(동명이인 구분·상세 연결 불가).
import { useState } from 'react'
import { GameLink, LoadState, PlayerLink, SourceLine, Stat, useV2 } from '../components/V2Bits'
import { useRoute } from '../lib/useRoute'
import { followLink, pageUrl, updateQuery } from '../lib/navigation'
import { COVERAGE_TEXT, fetchSeasons, fetchStandingsV2, intParam, SCHEDULE_SOURCE_LABEL } from '../lib/v2'
import { fetchTeam, gameLine, NAVER_SEASON_LABEL, recordPct, recordText } from '../lib/p2d'
import { teamColor } from '../lib/teamColors'
import { fmtRate } from '../lib/format'
import '../styles/V2.css'
import '../styles/P2D.css'

function KeyPlayers({ title, rows, season, role, stats }) {
  return (
    <div className="v2-card">
      <h3>{title}</h3>
      {!rows.length && <p className="v2-empty">WAR 자료가 있는 선수가 없습니다.</p>}
      <ol className="p2d-key">
        {rows.map((p) => (
          <li key={p.player_id}>
            <PlayerLink id={p.player_id} name={p.name} season={season} role={role} />
            <span className="v2-metric">{stats.map(([k, label, opts]) => (
              <span key={k}>{label} <Stat value={p.stats[k]} {...opts} /> </span>))}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function Roster({ players, season }) {
  const [tab, setTab] = useState('batter')
  const ids = players.basis === 'naver_season_stats'
  const rows = tab === 'batter' ? players.batters : players.pitchers
  return (
    <section className="p2d-section">
      <div className="v2-head">
        <h3 className="v2-section">{ids ? '그 시즌 출전 선수' : '규정 이상 선수(KBO 기록실)'} <span className="v2-count">{rows.length}명</span></h3>
        <div className="v2-seg" role="tablist">
          <button className={tab === 'batter' ? 'on' : ''} onClick={() => setTab('batter')}>타자 {players.batters.length}</button>
          <button className={tab === 'pitcher' ? 'on' : ''} onClick={() => setTab('pitcher')}>투수 {players.pitchers.length}</button>
        </div>
      </div>
      <p className="v2-note">{players.note}</p>
      {!rows.length ? <p className="v2-empty">자료 없음</p> : (
        <div className="v2-table-wrap">
          <table className="v2-table">
            {ids ? (
              <>
                <thead><tr><th className="lalign">선수</th><th>No.</th><th className="lalign">포지션</th><th>경기</th>
                  {tab === 'batter' ? <><th>타율</th><th>홈런</th><th>OPS</th></> : <><th>이닝</th><th>평균자책</th><th>WHIP</th></>}
                  <th>WAR</th></tr></thead>
                <tbody>
                  {[...rows].sort((a, b) => (b.stats.G ?? -1) - (a.stats.G ?? -1)).map((p) => (
                    <tr key={p.player_id}>
                      <td className="lalign"><PlayerLink id={p.player_id} name={p.name} season={season} role={tab} /></td>
                      <td>{p.back_no ?? '-'}</td><td className="lalign">{p.position || '-'}</td>
                      <td><Stat value={p.stats.G} /></td>
                      {tab === 'batter'
                        ? <><td><Stat value={p.stats.AVG} rate /></td><td><Stat value={p.stats.HR} /></td><td><Stat value={p.stats.OPS} rate /></td></>
                        : <><td>{p.stats.IP ?? <Stat value={null} />}</td><td><Stat value={p.stats.ERA} digits={2} /></td><td><Stat value={p.stats.WHIP} digits={2} /></td></>}
                      <td><Stat value={p.stats.WAR} digits={2} /></td>
                    </tr>
                  ))}
                </tbody>
              </>
            ) : (
              <>
                <thead><tr><th>기록실 순위</th><th className="lalign">선수</th><th>경기</th>
                  {tab === 'batter' ? <><th>타율</th><th>홈런</th><th>타점</th></> : <><th>이닝</th><th>평균자책</th><th>승-패</th></>}</tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={`${p.rank}-${p.name}`}>
                      <td>{p.rank}</td><td className="lalign">{p.name}</td><td><Stat value={p.games} /></td>
                      {tab === 'batter'
                        ? <><td><Stat value={p.avg} rate /></td><td><Stat value={p.home_runs} /></td><td><Stat value={p.rbi} /></td></>
                        : <><td>{p.innings_pitched ?? <Stat value={null} />}</td><td><Stat value={p.era} digits={2} /></td>
                          <td>{p.wins ?? '-'}-{p.losses ?? '-'}</td></>}
                    </tr>
                  ))}
                </tbody>
              </>
            )}
          </table>
        </div>
      )}
    </section>
  )
}

function TeamDetail() {
  const { query } = useRoute()
  const seasons = useV2(fetchSeasons, [])
  const held = (seasons.data?.data || []).filter((s) => s.schedule).map((s) => s.season)
  const season = intParam(query, 'season', held.at(-1) ?? null)
  const team = query.get('team') || null
  const table = useV2(() => (season ? fetchStandingsV2(season) : Promise.resolve(null)), [season])
  const teams = (table.data?.data || []).map((r) => r.team)
  const state = useV2(() => (season && team ? fetchTeam(team, season) : Promise.resolve(null)), [season, team])
  const d = state.data?.data
  const r = d?.record
  const sources = state.data?.meta?.sources || []
  const naver = sources.find((s) => s.source === 'naver_season_stats')

  return (
    <div className="v2-page p2d-team">
      <div className="v2-head">
        <h2 style={team ? { borderLeft: `6px solid ${teamColor(team)}`, paddingLeft: 10 } : undefined}>
          {team ? `${team} · ${season}시즌` : '팀 상세'}
        </h2>
        <div className="v2-controls">
          <select value={season ?? ''} onChange={(e) => updateQuery({ season: e.target.value })} aria-label="시즌">
            {[...held].reverse().map((s) => <option key={s} value={s}>{s} 시즌</option>)}
          </select>
          <select value={team ?? ''} onChange={(e) => updateQuery({ team: e.target.value || null })} aria-label="팀">
            <option value="">팀 선택</option>
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            {team && !teams.includes(team) && <option value={team}>{team}</option>}
          </select>
        </div>
      </div>

      {!team && <p className="v2-empty">팀을 고르세요. 순위표에서 팀 이름을 눌러도 됩니다.</p>}
      {team && (
        <LoadState state={state} empty={state.status === 404 ? `${season}시즌 ${team} 기록이 없습니다(그 시즌에 없던 팀이거나 일정 자료 없음).` : null} />
      )}

      {d && (
        <>
          <section className="v2-cards p2d-record">
            <div className="v2-card">
              <h3>시즌 기록 <span className="v2-metric">{COVERAGE_TEXT[d.coverage] || d.coverage}</span></h3>
              <div className="v2-big">{r.rank}위{r.tie ? ' (동률)' : ''}</div>
              <dl className="v2-dl">
                <div><dt>승</dt><dd>{r.wins}</dd></div><div><dt>패</dt><dd>{r.losses}</dd></div>
                <div><dt>무</dt><dd>{r.draws}</dd></div><div><dt>승률</dt><dd>{fmtRate(r.pct)}</dd></div>
                <div><dt>승차</dt><dd>{r.games_behind ?? '-'}</dd></div><div><dt>경기</dt><dd>{r.games}</dd></div>
              </dl>
              <p className="v2-card-sub">최근 10경기 {r.last10 ?? '-'} · 연속 {r.streak ?? '-'}
                {r.source && <> · 원본 순위 {r.source.rank}위</>}</p>
            </div>
            {[['home', '홈'], ['away', '원정']].map(([k, label]) => (
              <div className="v2-card" key={k}>
                <h3>{label} 성적</h3>
                <div className="v2-big">{fmtRate(recordPct(r[k]))}</div>
                <p className="v2-card-sub">{recordText(r[k]) ?? '자료 없음'}</p>
              </div>
            ))}
          </section>

          <section className="p2d-section">
            <h3 className="v2-section">최근 {d.recent_games.length}경기 <span className="v2-metric">리그 마지막 경기일 {d.last_played_date ?? '-'} · 실시간 아님</span></h3>
            {!d.recent_games.length ? <p className="v2-empty">끝난 경기가 없습니다.</p> : (
              <ul className="p2d-games">
                {d.recent_games.map((g) => {
                  const x = gameLine(g)
                  return (
                    <li key={`${g.date}-${g.doubleheader}-${g.opponent}`} className={`p2d-r-${g.result}`}>
                      <span className="p2d-result">{x.result}</span>
                      <span className="v2-num">{x.score}</span>
                      <span>{x.where === '홈' ? 'vs' : '@'} {x.opponent}</span>
                      <span className="v2-metric">{g.date}{g.doubleheader ? ` DH${g.doubleheader}` : ''} · {x.where}</span>
                      {g.has_box && <span className="v2-metric"><GameLink id={g.game_id}>박스스코어</GameLink></span>}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          {d.players.basis === 'naver_season_stats' && (
            <section className="v2-cards p2d-keys">
              <KeyPlayers title="주요 타자 (WAR)" rows={d.players.key_batters} season={season} role="batter"
                stats={[['AVG', '타율', { rate: true }], ['HR', '홈런', {}], ['OPS', 'OPS', { rate: true }], ['WAR', 'WAR', { digits: 2 }]]} />
              <KeyPlayers title="주요 투수 (WAR)" rows={d.players.key_pitchers} season={season} role="pitcher"
                stats={[['ERA', '평균자책', { digits: 2 }], ['SO', '삼진', {}], ['WAR', 'WAR', { digits: 2 }]]} />
            </section>
          )}

          <Roster players={d.players} season={season} />

          <p className="v2-foot">팀 선수 목록에서 선수를 고르면 상세 기록으로, <a href={pageUrl('search', { team, season })} onClick={followLink}>선수 찾기</a>에서 비교할 수 있습니다.</p>
          <SourceLine label={SCHEDULE_SOURCE_LABEL} fetchedAt={sources[0]?.collected_at} extra="팀 기록·최근 경기" />
          {naver && <SourceLine label={NAVER_SEASON_LABEL} fetchedAt={naver.collected_at} extra="선수 기록" />}
          {!naver && <p className="v2-source"><span className="v2-source-label">출처</span> 선수 기록: KBO 기록실 시즌 순위표(규정 이상만, v1 적재 · 자동 수집 · 외부 공개 전)</p>}
        </>
      )}
    </div>
  )
}

export default TeamDetail
