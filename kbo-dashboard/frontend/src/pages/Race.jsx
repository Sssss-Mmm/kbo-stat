// 가을야구 레이스 보드 (IDEAS #1).
// "우리 팀 5위 가능해? 몇 경기 남았고 몇 개 이겨야 해?" 한 화면으로 답한다.
// 계산은 전부 lib/race.js 의 결정론적 산수다 — 확률·시뮬레이션은 만들지 않는다(PLAN 3절 비목표).
import { useState, useEffect, useMemo, Fragment } from 'react'
import axios from 'axios'
import RankRace from '../components/charts/RankRace'
import { TeamCell } from '../components/MiniTable'
import SeasonBanner from '../components/SeasonBanner'
import { teamColor } from '../lib/teamColors'
import { fmtRate } from '../lib/format'
import { kstToday } from '../lib/season'
import {
  SEASON_GAMES, PLAYOFF_CUT, MAGIC_MAX_REMAINING, showMagicNumbers,
  teamRunTotals, raceRows, contenders, dailyRanks, remainingMatchups,
} from '../lib/race'
import '../styles/Home.css'
import '../styles/Race.css'

const CUT_OPTIONS = [
  { value: 1, label: '1위 (우승)' },
  { value: 3, label: '3위 (준PO 직행)' },
  { value: 5, label: '5위 (가을야구)' },
]

// 로드 실패(null)와 "데이터가 원래 없음"([])을 구분해 보여준다 (Teams.jsx 와 같은 규칙).
function Note({ rows, empty }) {
  return rows === null
    ? <p className="error">불러오지 못했습니다.</p>
    : <p className="empty">{empty}</p>
}

const signed = (v) => (v > 0 ? `+${v}` : String(v))  // 커트라인 대비 게임차 부호 표기

function Race({ seasonInfo, onTeamClick }) {
  const season = seasonInfo.dataSeason
  const [cut, setCut] = useState(PLAYOFF_CUT)
  const [d, setD] = useState({ standings: [], games: [], schedule: [] })
  const [loading, setLoading] = useState(true)
  const [today] = useState(() => kstToday())

  // 세 엔드포인트를 한 번에 받아 클라이언트에서 계산한다. 새 API는 만들지 않는다.
  useEffect(() => {
    let active = true
    const get = (url) => axios.get(url, { params: { season } })
      .then((r) => r.data.data || [])
      .catch(() => null)  // NFR-06: 하나가 실패해도 나머지 패널은 그린다
    setLoading(true)
    Promise.all([get('/api/standings'), get('/api/team-games'), get('/api/schedule-games')])
      .then(([standings, games, schedule]) => {
        if (!active) return
        setD({ standings, games, schedule })
        setLoading(false)
      })
    return () => { active = false }
  }, [season])

  const rows = useMemo(
    () => raceRows(d.standings || [], teamRunTotals(d.games || []), cut),
    [d.standings, d.games, cut],
  )

  // 순위 곡선: 경기 결과 누적으로 개막일부터 복원한다(공식 스냅샷은 6월부터뿐이라).
  const race = useMemo(() => {
    const { series, dates } = dailyRanks(d.games || [])
    return {
      series: series.map((s) => ({ ...s, color: teamColor(s.team) })),
      dateCount: dates.length,
      first: dates[0],
      last: dates[dates.length - 1],
    }
  }, [d.games])

  const matchups = useMemo(() => {
    if (!rows.length) return []
    return remainingMatchups(d.schedule || [], contenders(rows, cut), today)
  }, [d.schedule, rows, cut, today])

  // 잔여 경기가 너무 많은 시즌 초반에는 매직넘버가 무의미하다(AC3).
  const maxRemaining = rows.reduce((m, r) => Math.max(m, r.remaining), 0)
  const showMagic = showMagicNumbers(rows)
  // 아직 재편성되지 않은 취소 경기 수. 잔여 합계(144 기준, 팀별이라 2로 나눈다)와 남은 일정의 차이다.
  const unscheduled = useMemo(() => {
    if (!rows.length || !d.schedule) return 0
    const listed = d.schedule.filter((g) => g.status !== 'final' && g.Date >= today).length
    return Math.max(0, Math.round(rows.reduce((a, r) => a + r.remaining, 0) / 2) - listed)
  }, [rows, d.schedule, today])

  const regular = seasonInfo.state === 'regular'
  const cutRow = rows.find((r) => r.rank === cut)

  if (loading) return <div className="race-container"><p className="loading">로딩중...</p></div>

  return (
    <div className="race-container">
      <SeasonBanner info={seasonInfo} selected={season} />

      <div className="race-header">
        <h2>{season} 가을야구 레이스</h2>
        {regular && (
          <label className="race-cut-pick">
            기준
            <select value={cut} onChange={(e) => setCut(Number(e.target.value))}>
              {CUT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        )}
      </div>

      {/* FR-12: 포스트시즌·오프시즌에 '레이스'는 이미 끝났다. 매직넘버·잔여 일정은 감추고 최종 순위만 남긴다. */}
      {!regular && (
        <p className="season-notice">
          {seasonInfo.state === 'preseason'
            ? `${season} 정규시즌은 종료됐습니다. 개막 후 잔여 경기·매직넘버가 다시 계산됩니다.`
            : '정규시즌이 종료돼 잔여 경기가 없습니다. 아래는 최종 순위와 시즌 순위 곡선입니다.'}
        </p>
      )}

      <section className="panel">
        <div className="panel-head">
          <h3>{regular ? `${cut}위 진출선 레이스` : '정규시즌 최종 순위'}</h3>
          <p>
            {regular && cutRow ? `기준 ${cut}위 ${cutRow.team} · 잔여 최대 ${maxRemaining}경기` : `${season}시즌`}
          </p>
        </div>
        {rows.length ? (
          <>
            <div className="race-scroll">
              <table className="race-table">
                <thead>
                  <tr>
                    <th className="lalign">순위</th>
                    <th className="lalign">팀</th>
                    <th>승-패-무</th>
                    <th>승률</th>
                    <th>피타고리안</th>
                    <th>차이</th>
                    {regular && <th>잔여</th>}
                    {regular && <th>{cut}위차</th>}
                    {regular && showMagic && <th>자력</th>}
                    {regular && showMagic && <th className="lalign">매직 / 트래직</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <Fragment key={r.team}>
                      <tr className={r.inside ? 'inside' : ''}>
                        <td className="lalign">{r.rank}</td>
                        <td className="lalign">
                          <button type="button" className="race-team" onClick={() => onTeamClick?.(r.team)} title={`${r.team} 팀 분석 보기`}>
                            <TeamCell team={r.team} />
                          </button>
                        </td>
                        <td>{r.wins}-{r.losses}-{r.draws}</td>
                        <td className="winrate">{fmtRate(r.win_rate)}</td>
                        <td>{fmtRate(r.pyth)}</td>
                        <td className={r.pythDiff == null ? '' : r.pythDiff >= 0 ? 'pos' : 'neg'}>
                          {r.pythDiff == null ? '-' : `${r.pythDiff >= 0 ? '+' : '-'}${fmtRate(Math.abs(r.pythDiff))}`}
                        </td>
                        {regular && <td>{r.remaining}</td>}
                        {regular && <td>{r.gbCut === 0 ? '-' : signed(r.gbCut)}</td>}
                        {regular && showMagic && (
                          <td title={r.eliminated ? '전승해도 진출 불가' : r.selfPower ? '전승하면 남의 결과와 무관하게 진출' : '다른 팀 결과가 필요'}>
                            {r.eliminated ? '✕' : r.selfPower ? '●' : '○'}
                          </td>
                        )}
                        {regular && showMagic && (
                          <td className="lalign magic">
                            {r.eliminated ? <span className="tag out">탈락 확정</span>
                              : r.inside
                                ? (r.magic === 0 ? <span className="tag in">진출 확정</span> : <><b>M {r.magic}</b> <span className="muted">승 / 상대 패</span></>)
                                : <><b>T {r.tragic}</b> <span className="muted">패면 탈락</span></>}
                          </td>
                        )}
                      </tr>
                      {r.rank === cut && (
                        <tr className="cutline">
                          <td colSpan={regular ? (showMagic ? 10 : 8) : 6}>{cut}위 커트라인</td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="race-foot">
              {regular && showMagic && <>매직넘버 M = (진출선 밖 팀의 전승 시 승수 − 내 승수) + 1, 트래직넘버 T = (내 전승 시 승수 − {cut}위 승수) + 1. </>}
              {regular && !showMagic && <>잔여 {maxRemaining}경기 — 매직넘버는 잔여 {MAGIC_MAX_REMAINING}경기 이하일 때만 표시한다. </>}
              잔여 경기는 <b>{SEASON_GAMES} − 경기수</b>, 승률·게임차는 무승부를 제외한 KBO 규정 계산이다.
              <b> 승부 예측이나 진출 확률이 아니라 산수다.</b>
              {' '}피타고리안 기대승률은 득점·실점(지수 1.83)만으로 낸 값이라 실제 승률과의 차이는 접전 운의 크기를 뜻한다.
            </p>
          </>
        ) : <Note rows={d.standings} empty={`${season}시즌 순위 데이터가 없습니다.`} />}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>시즌 순위 곡선</h3>
          <p>{race.first ? `${race.first} ~ ${race.last} · 경기 결과로 복원 (선을 클릭하면 강조)` : '경기 결과 기반'}</p>
        </div>
        {race.series.length
          ? <RankRace series={race.series} dateCount={race.dateCount} teamCount={race.series.length} />
          : <Note rows={d.games} empty="경기 결과가 없습니다." />}
      </section>

      {regular && (
        <section className="panel">
          <div className="panel-head">
            <h3>남은 맞대결</h3>
            <p>{cut}위 경쟁권 팀끼리의 잔여 일정</p>
          </div>
          {matchups.length ? (
            <>
              <ul className="matchup-list">
                {matchups.map((m) => (
                  <li key={`${m.a}|${m.b}`}>
                    <span className="mu-pair">
                      <b className="team-ink" style={{ '--team-c': teamColor(m.a) }}>{m.a}</b>
                      <span className="mu-vs">vs</span>
                      <b className="team-ink" style={{ '--team-c': teamColor(m.b) }}>{m.b}</b>
                      <span className="mu-count">{m.games.length}경기</span>
                    </span>
                    <span className="mu-games">
                      {m.games.map((g) => (
                        <span className="mu-game" key={g.date + g.ballpark}>{g.date.slice(5).replace('-', '/')} {g.ballpark}</span>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
              {unscheduled > 0 && (
                <p className="race-foot">아직 재편성되지 않은 취소 경기 {unscheduled}건은 이 목록에 없다. 잔여 경기 수에는 포함돼 있다.</p>
              )}
            </>
          ) : <Note rows={d.schedule} empty="경쟁권 팀끼리 남은 맞대결이 없습니다." />}
        </section>
      )}
    </div>
  )
}

export default Race
