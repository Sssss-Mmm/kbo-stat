// 팀 분석 페이지 (FR-07).
// 한 팀을 골라 시즌 흐름을 세 각도로 본다: 순위 변화 / 월별 성적 / 홈·원정 비교.
// 순위 변화는 team-rank-history 의 실제 스냅샷 순위를 쓴다(누적 재계산이 아님).
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import RankRace from '../components/charts/RankRace'
import { MiniTable, BarList, TeamCell, Note } from '../components/MiniTable'
import { teamColor } from '../lib/teamColors'
import { fmtRate, fmtPct, fmtInt } from '../lib/format'
import SeasonBanner from '../components/SeasonBanner'
import '../styles/Home.css'
import '../styles/Teams.css'
import { apiError } from '../lib/apiError'

const TEAM_COUNT = 10
const MONTH_LABEL = (m) => `${m}월`

function Teams({ seasonInfo, initialTeam }) {
  const [season] = useState(seasonInfo.dataSeason)
  const [team, setTeam] = useState(initialTeam || null)
  const [d, setD] = useState({ history: [], monthly: [], games: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // 시즌 데이터는 한 번에 전 팀 분량을 받아두고, 팀 전환은 클라이언트에서 필터링한다.
  // (팀당 재요청보다 왕복이 적고, 순위 변화 차트는 어차피 전 팀 데이터가 필요하다.)
  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        // NFR-06: 한 엔드포인트가 실패해도 나머지 패널은 그린다.
        // 실패는 null, 정상 응답인데 데이터가 없으면 [] 로 구분한다.
        const get = (url) => axios.get(url, { params: { season } })
          .then((r) => r.data.data || [])
          .catch(() => null)
        const [history, monthly, games] = await Promise.all([
          get('/api/team-rank-history'),
          get('/api/team-monthly'),
          get('/api/team-games'),
        ])
        if (!active) return
        setD({ history, monthly, games })
        // 기본 선택: 현재 1위 팀.
        if (!team && history?.length) {
          const dates = history.map((r) => r.Date).sort()
          const last = dates[dates.length - 1]
          const top = history.find((r) => r.Date === last && r['순위'] === 1)
          setTeam(top?.['팀명'] || history[0]['팀명'])
        }
      } catch (err) {
        if (active) setError(apiError(err))
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [season])

  // 팀 목록은 순위 데이터가 우선이지만, 그게 실패하면 월별/경기 데이터에서 만든다.
  const teams = useMemo(() => {
    const names = [
      ...(d.history || []).map((r) => r['팀명']),
      ...(d.monthly || []).map((r) => r.Team),
      ...(d.games || []).map((r) => r.Team),
    ].filter(Boolean)
    return [...new Set(names)].sort()
  }, [d])

  // 순위 데이터가 없어 기본 팀이 안 정해졌으면 목록 첫 팀을 고른다.
  useEffect(() => {
    if (!team && teams.length) setTeam(teams[0])
  }, [teams, team])

  // 순위 변화: 날짜 인덱스 → 팀별 {index, rank} 시리즈.
  const race = useMemo(() => {
    const dates = [...new Set((d.history || []).map((r) => r.Date))].sort()
    const idx = Object.fromEntries(dates.map((dt, i) => [dt, i]))
    const seriesMap = {}
    const rows = d.history || []
    rows.forEach((r) => {
      (seriesMap[r['팀명']] ||= []).push({ index: idx[r.Date], rank: r['순위'] })
    })
    const series = Object.entries(seriesMap).map(([t, points]) => ({
      team: t,
      color: teamColor(t),
      points: points.sort((a, b) => a.index - b.index),
    }))
    return { series, dateCount: dates.length }
  }, [d.history])

  const monthly = useMemo(
    () => (d.monthly || []).filter((r) => r.Team === team).sort((a, b) => a.Month - b.Month),
    [d.monthly, team],
  )

  // 홈/원정: team-games 를 HomeAway 로 갈라 승패·득실 집계.
  const homeAway = useMemo(() => {
    const acc = {}
    const rows = d.games || []
    rows.filter((g) => g.Team === team).forEach((g) => {
      // 데이터는 소문자 'home'/'away'. 표기 변화에 대비해 대소문자·한글 모두 받는다.
      const raw = String(g.HomeAway || '').toLowerCase()
      const key = raw === 'home' || raw === '홈' ? '홈' : '원정'
      const a = (acc[key] ||= { w: 0, l: 0, dr: 0, rf: 0, ra: 0 })
      a.w += g.Win || 0
      a.l += g.Loss || 0
      a.dr += g.Draw || 0
      a.rf += g.RunsFor || 0
      a.ra += g.RunsAgainst || 0
    })
    return ['홈', '원정']
      .filter((k) => acc[k])
      .map((k) => ({ split: k, ...acc[k], pct: acc[k].w + acc[k].l ? acc[k].w / (acc[k].w + acc[k].l) : null }))
  }, [d.games, team])

  const seasonTotal = useMemo(() => {
    const t = monthly.reduce(
      (a, m) => ({ g: a.g + m.Games, w: a.w + m.Wins, l: a.l + m.Losses, dr: a.dr + m.Draws, rd: a.rd + m.RunDiff }),
      { g: 0, w: 0, l: 0, dr: 0, rd: 0 },
    )
    return { ...t, pct: t.w + t.l ? t.w / (t.w + t.l) : null }
  }, [monthly])

  if (loading) return <div className="teams-container"><p className="loading">로딩중...</p></div>
  if (error) return <div className="teams-container"><p className="error">{error}</p></div>
  // 셋 다 실패했을 때만 페이지 전체가 에러가 된다.
  if (!d.history && !d.monthly && !d.games) {
    return <div className="teams-container"><p className="error">팀 데이터를 불러오지 못했습니다.</p></div>
  }
  if (!teams.length) return <div className="teams-container"><p className="empty">{season}시즌 팀 데이터가 없습니다.</p></div>

  return (
    <div className="teams-container">
      <SeasonBanner info={seasonInfo} selected={season} />
      <div className="teams-header">
        <h2>{season}시즌 팀 분석</h2>
        <select value={team || ''} onChange={(e) => setTeam(e.target.value)}>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h3><TeamCell team={team} /> 시즌 요약</h3>
          <p>{monthly.length ? `${monthly[0].Month}월 ~ ${monthly[monthly.length - 1].Month}월` : '집계 없음'}</p>
        </div>
        {monthly.length ? (
          <div className="team-summary">
            <div><span>경기</span><strong>{fmtInt(seasonTotal.g)}</strong></div>
            <div><span>승-패-무</span><strong>{seasonTotal.w}-{seasonTotal.l}-{seasonTotal.dr}</strong></div>
            <div><span>승률</span><strong>{fmtRate(seasonTotal.pct)}</strong></div>
            <div><span>득실차</span><strong className={seasonTotal.rd >= 0 ? 'pos' : 'neg'}>
              {seasonTotal.rd > 0 ? '+' : ''}{fmtInt(seasonTotal.rd)}
            </strong></div>
          </div>
        ) : <Note rows={d.monthly} empty="시즌 집계가 없습니다." />}
      </section>

      {/* AC1 순위 변화 — 팀을 클릭하면 그 팀만 강조된다 */}
      <section className="panel">
        <div className="panel-head"><h3>순위 변화</h3><p>날짜별 순위 스냅샷 (선을 클릭하면 강조)</p></div>
        {race.series.length
          ? <RankRace series={race.series} dateCount={race.dateCount} teamCount={TEAM_COUNT} />
          : <Note rows={d.history} empty="순위 스냅샷이 없습니다." />}
      </section>

      <div className="panel-grid-2">
        {/* AC2 월별 성적 — 데이터 없는 달은 행을 만들지 않는다(0으로 채우지 않음) */}
        <article className="panel">
          <div className="panel-head"><h3>월별 성적</h3><p>{team}</p></div>
          {monthly.length ? (
            <>
              <MiniTable
                columns={[
                  { key: 'Month', label: '월', render: (r) => MONTH_LABEL(r.Month) },
                  { key: 'Games', label: 'G' },
                  { key: 'Wins', label: '승' },
                  { key: 'Losses', label: '패' },
                  { key: 'Draws', label: '무' },
                  { key: 'WinRate', label: '승률', render: (r) => fmtRate(r.WinRate) },
                  { key: 'RunDiff', label: '득실', render: (r) => (r.RunDiff > 0 ? `+${r.RunDiff}` : r.RunDiff) },
                ]}
                rows={monthly}
              />
              <BarList
                items={monthly.map((m) => ({ label: MONTH_LABEL(m.Month), value: m.WinRate || 0, color: teamColor(team) }))}
              />
            </>
          ) : <Note rows={d.monthly} empty="월별 집계가 없습니다." />}
        </article>

        {/* AC3 홈/원정 비교 */}
        <article className="panel">
          <div className="panel-head"><h3>홈 / 원정</h3><p>{team}</p></div>
          {homeAway.length ? (
            <>
              <MiniTable
                columns={[
                  { key: 'split', label: '구분', left: true },
                  { key: 'w', label: '승' },
                  { key: 'l', label: '패' },
                  { key: 'dr', label: '무' },
                  { key: 'pct', label: '승률', render: (r) => fmtRate(r.pct) },
                  { key: 'rf', label: '득점' },
                  { key: 'ra', label: '실점' },
                ]}
                rows={homeAway}
              />
              <BarList
                items={homeAway.map((h) => ({ label: h.split, value: h.pct || 0, color: teamColor(team) }))}
                fmt={fmtPct}
              />
            </>
          ) : <Note rows={d.games} empty="홈/원정 집계가 없습니다." />}
        </article>
      </div>
    </div>
  )
}

export default Teams
