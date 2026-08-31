// 리그 운영 페이지 (FR-08). 관중과 경기시간, 팀별 이동거리를 한 화면에 묶는다.
// 소비 API 4개: /api/attendance, /api/game-time/team, /api/game-time/yearly, /api/team-games.
// 원 데이터가 팀×월 관중 / 팀 평균·연도 평균 경기시간까지라서, 경기 단위가 필요한 것
// (요일별·구장별·최장 경기·분포)은 만들 수 없다. 그 사실은 화면 하단에 그대로 적는다.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import TrendLine from '../components/charts/TrendLine'
import { MiniTable, BarList, TeamCell, Note } from '../components/MiniTable'
import SeasonBanner from '../components/SeasonBanner'
import { teamColor } from '../lib/teamColors'
import { fmtInt, fmtPct, fmtOne, fmtMinutes } from '../lib/format'
import { teamTravel } from '../lib/travel'
import '../styles/Home.css'
import '../styles/Ops.css'

function Ops({ seasonInfo }) {
  // 관중·팀별 경기시간은 2026 한 시즌뿐이라 시즌 셀렉터를 두지 않는다(연도 축은 추이 차트가 담당).
  const season = seasonInfo.dataSeason
  const [d, setD] = useState({ attendance: [], teamTime: [], yearly: [], games: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        // NFR-06: 실패는 null, 정상 응답인데 데이터가 없으면 [] 로 구분한다.
        const get = (url, params) => axios.get(url, { params })
          .then((r) => r.data.data || [])
          .catch(() => null)
        const [attendance, teamTime, yearly, games] = await Promise.all([
          get('/api/attendance', { season }),
          get('/api/game-time/team', { season }),
          get('/api/game-time/yearly'),
          get('/api/team-games', { season }),
        ])
        if (active) setD({ attendance, teamTime, yearly, games })
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [season])

  // 관중: Month 0 이 시즌 합계, 1~12 가 월별. 팀이 홈경기를 치르지 않은 달은 행 자체가 없다.
  const att = useMemo(() => {
    const rows = d.attendance || []
    const totals = [...rows.filter((r) => r.Month === 0)].sort((a, b) => (b.Attendance || 0) - (a.Attendance || 0))
    const monthRows = rows.filter((r) => r.Month > 0)
    const months = [...new Set(monthRows.map((r) => r.Month))].sort((a, b) => a - b)
    const grid = {}
    monthRows.forEach((r) => { (grid[r.Team] ||= {})[r.Month] = r.Attendance })
    const league = totals.reduce((s, r) => s + (r.Attendance || 0), 0)
    const byMonth = months.map((m) => ({
      month: m,
      value: monthRows.filter((r) => r.Month === m).reduce((s, r) => s + (r.Attendance || 0), 0),
    }))
    const teams = totals.length ? totals.map((r) => r.Team) : Object.keys(grid).sort()
    return { totals, months, grid, league, byMonth, teams, updatedAt: rows[0]?.UpdatedAt }
  }, [d.attendance])

  // 팀별 경기시간: 정규이닝 기준 오름차순(빠른 팀이 위).
  const teamTime = useMemo(
    () => [...(d.teamTime || [])].sort((a, b) => (a.RegularInningMinutes || 0) - (b.RegularInningMinutes || 0)),
    [d.teamTime],
  )

  // 연도별 경기시간: 연장 포함은 1982~, 정규이닝은 2010~ 만 집계돼 있다(원본 그대로 그린다).
  const yearly = useMemo(() => {
    const rows = d.yearly || []
    const pick = (type) => rows
      .filter((r) => r.Type === type && Number.isFinite(r.AverageMinutes))
      .map((r) => ({ x: r.Season, y: r.AverageMinutes }))
      .sort((a, b) => a.x - b.x)
    const extra = pick('include_extra')
    const regular = pick('regular')
    const best = (cmp) => (extra.length ? extra.reduce((a, b) => (cmp(b.y, a.y) ? b : a)) : null)
    const cur = extra[extra.length - 1] || null
    const prev = extra[extra.length - 2] || null
    return {
      extra,
      regular,
      longest: best((a, b) => a > b),
      shortest: best((a, b) => a < b),
      cur,
      diff: cur && prev ? cur.y - prev.y : null,
      span: extra.length ? `${extra[0].x}~${extra[extra.length - 1].x}` : '-',
    }
  }, [d.yearly])

  // 이동거리: 경기 로그(구장 포함)에서 계산한다. 정의와 좌표 출처는 lib/travel.js 주석 참고.
  const travel = useMemo(() => teamTravel(d.games || []), [d.games])

  if (loading) return <div className="ops"><p className="loading">로딩중...</p></div>
  if (error) return <div className="ops"><p className="error">{error}</p></div>
  // 셋 다 실패했을 때만 페이지 전체가 에러가 된다.
  if (!d.attendance && !d.teamTime && !d.yearly && !d.games) {
    return <div className="ops"><p className="error">운영 데이터를 불러오지 못했습니다.</p></div>
  }

  const topTeam = att.totals[0]
  const avgTeamMin = teamTime.length
    ? teamTime.reduce((s, t) => s + (t.RegularInningMinutes || 0), 0) / teamTime.length
    : null

  return (
    <div className="ops">
      <SeasonBanner info={seasonInfo} selected={season} note="관중·팀별 경기시간은 2026시즌만 수집돼 있습니다" />
      <section className="ops-hero">
        <div>
          <p className="eyebrow">KBO Dashboard</p>
          <h2>{season}시즌 리그 운영</h2>
        </div>
        {att.updatedAt && <p className="ops-updated">관중 갱신 {att.updatedAt}</p>}
      </section>

      <section className="card-grid">
        <article className="stat-card">
          <span className="kicker">시즌 총 관중</span>
          <h3>{att.totals.length ? fmtInt(att.league) : '-'}</h3>
          <p>{att.totals.length ? `${att.totals.length}개 구단 홈경기 합계` : '집계 없음'}</p>
        </article>
        <article className="stat-card">
          <span className="kicker">최다 관중 구단</span>
          <h3>{topTeam?.Team || '-'}</h3>
          <p>{topTeam ? `${fmtInt(topTeam.Attendance)}명 · 리그의 ${fmtPct(topTeam.Attendance / (att.league || 1))}` : '-'}</p>
        </article>
        <article className="stat-card">
          <span className="kicker">평균 경기시간</span>
          <h3>{fmtMinutes(avgTeamMin)}</h3>
          <p>{teamTime.length ? '10개 구단 정규이닝 기준 평균' : '집계 없음'}</p>
        </article>
        <article className="stat-card">
          <span className="kicker">전년 대비</span>
          <h3>{yearly.diff === null ? '-' : `${yearly.diff > 0 ? '+' : ''}${yearly.diff}분`}</h3>
          <p>{yearly.cur ? `${yearly.cur.x} ${fmtMinutes(yearly.cur.y)} (연장 포함)` : '-'}</p>
        </article>
      </section>

      {/* 이 화면의 주인공: 연장 포함 45시즌 추이 */}
      <section className="panel">
        <div className="panel-head">
          <h3>연도별 평균 경기시간</h3>
          <p>{yearly.span} · 정규이닝 계열은 2010시즌부터 집계</p>
        </div>
        {yearly.extra.length ? (
          <>
            <TrendLine
              series={[
                { label: '연장 포함', color: 'var(--accent-3)', points: yearly.extra },
                { label: '정규이닝', color: 'var(--accent)', points: yearly.regular },
              ]}
              yLabel="분"
              fmt={(v) => fmtMinutes(v)}
              xTickStep={5}
            />
            <div className="stat-rows ops-extremes">
              <div className="stat-row">
                <span>가장 길었던 시즌</span>
                <strong>{yearly.longest ? `${yearly.longest.x} · ${fmtMinutes(yearly.longest.y)}` : '-'}</strong>
              </div>
              <div className="stat-row">
                <span>가장 짧았던 시즌</span>
                <strong>{yearly.shortest ? `${yearly.shortest.x} · ${fmtMinutes(yearly.shortest.y)}` : '-'}</strong>
              </div>
            </div>
          </>
        ) : <Note rows={d.yearly} empty="연도별 경기시간 데이터가 없습니다." />}
      </section>

      <div className="panel-grid-2">
        <article className="panel">
          <div className="panel-head"><h3>구단별 관중</h3><p>{season}시즌 홈경기 누적</p></div>
          {att.totals.length ? (
            <>
              <BarList
                items={att.totals.map((r) => ({ label: r.Team, value: r.Attendance || 0, color: teamColor(r.Team) }))}
                fmt={fmtInt}
              />
              <div className="ops-table-wrap">
                <MiniTable
                  columns={[
                    { key: 'Team', label: '구단', left: true, render: (r) => <TeamCell team={r.Team} /> },
                    { key: 'Attendance', label: '총 관중', render: (r) => fmtInt(r.Attendance) },
                    { key: 'share', label: '리그 비중', render: (r) => fmtPct((r.Attendance || 0) / (att.league || 1)) },
                  ]}
                  rows={att.totals}
                />
              </div>
            </>
          ) : <Note rows={d.attendance} empty={`${season}시즌 관중 데이터가 없습니다.`} />}
        </article>

        <article className="panel">
          <div className="panel-head"><h3>구단별 경기시간</h3><p>정규이닝 / 연장 포함</p></div>
          {teamTime.length ? (
            <>
              <BarList
                items={teamTime.map((t) => ({ label: t.Team, value: t.RegularInningMinutes || 0, color: teamColor(t.Team) }))}
                fmt={fmtMinutes}
              />
              <div className="ops-table-wrap">
                <MiniTable
                  columns={[
                    { key: 'Team', label: '구단', left: true, render: (r) => <TeamCell team={r.Team} /> },
                    { key: 'reg', label: '정규이닝', render: (r) => fmtMinutes(r.RegularInningMinutes) },
                    { key: 'ext', label: '연장 포함', render: (r) => fmtMinutes(r.IncludeExtraMinutes) },
                    { key: 'gap', label: '차이', render: (r) => `+${(r.IncludeExtraMinutes || 0) - (r.RegularInningMinutes || 0)}분` },
                  ]}
                  rows={teamTime}
                />
              </div>
            </>
          ) : <Note rows={d.teamTime} empty={`${season}시즌 경기시간 데이터가 없습니다.`} />}
        </article>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h3>월별 관중</h3>
          <p>구단 × 월 · 홈경기가 없던 달은 빈칸</p>
        </div>
        {att.months.length ? (
          <>
            <BarList
              items={att.byMonth.map((m) => ({ label: `${m.month}월`, value: m.value, color: 'var(--accent-3)' }))}
              fmt={fmtInt}
            />
            <div className="ops-table-wrap">
              <MiniTable
                columns={[
                  { key: 'Team', label: '구단', left: true, render: (r) => <TeamCell team={r.team} /> },
                  ...att.months.map((m) => ({
                    key: `m${m}`,
                    label: `${m}월`,
                    render: (r) => (Number.isFinite(att.grid[r.team]?.[m]) ? fmtInt(att.grid[r.team][m]) : '-'),
                  })),
                  { key: 'sum', label: '합계', render: (r) => fmtInt(att.months.reduce((s, m) => s + (att.grid[r.team]?.[m] || 0), 0)) },
                ]}
                rows={att.teams.map((t) => ({ team: t }))}
              />
            </div>
          </>
        ) : <Note rows={d.attendance} empty={`${season}시즌 월별 관중 데이터가 없습니다.`} />}
      </section>

      {/* 이동거리: 목표 사이트에 있는 메뉴(G-02). 네비를 늘리지 않고 운영 페이지 패널로 둔다. */}
      <section className="panel">
        <div className="panel-head">
          <h3>팀별 이동거리</h3>
          <p>{season}시즌 · 구장 간 직선거리(대권거리) 누적</p>
        </div>
        {travel.teams.length ? (
          <>
            <BarList
              items={travel.teams.map((t) => ({ label: t.team, value: t.km, color: teamColor(t.team) }))}
              fmt={(v) => `${fmtInt(v)}km`}
            />
            <div className="ops-table-wrap">
              <MiniTable
                columns={[
                  { key: 'team', label: '구단', left: true, render: (r) => <TeamCell team={r.team} /> },
                  { key: 'km', label: '총 이동거리', render: (r) => `${fmtInt(r.km)}km` },
                  { key: 'games', label: '경기', render: (r) => fmtInt(r.games) },
                  { key: 'moves', label: '이동', render: (r) => `${r.moves}회` },
                  { key: 'stays', label: '연전', render: (r) => `${r.stays}회` },
                  { key: 'perGame', label: '경기당', render: (r) => `${fmtOne(r.perGame)}km` },
                  {
                    key: 'longest',
                    label: '최장 이동',
                    left: true,
                    render: (r) => (r.longest
                      ? `${r.longest.from}→${r.longest.to} ${fmtInt(r.longest.km)}km (${r.longest.date.slice(5)})`
                      : '-'),
                  },
                ]}
                rows={travel.teams}
              />
            </div>
            <p className="ops-travel-def">
              <b>계산 기준</b> · 날짜순으로 <b>직전 경기 구장 → 다음 경기 구장</b>을 더합니다.
              같은 구장 연전은 0km(표의 &lsquo;연전&rsquo;), 원정 복귀 이동도 포함합니다.
              시즌 첫 경기 이전 이동은 직전 위치를 알 수 없어 제외합니다.
              거리는 구장 좌표 기준 <b>직선거리</b>라 실제 도로·항공 이동보다 짧습니다(보정 계수를 곱하지 않았습니다).
              {travel.unknownGames > 0 && ` 좌표를 모르는 구장(${travel.unknownParks.join(', ')})의 경기 ${travel.unknownGames}건(${fmtPct(travel.ratioUnknown)})은 제외했습니다.`}
            </p>
          </>
        ) : <Note rows={d.games} empty={`${season}시즌 경기 로그가 없어 이동거리를 계산할 수 없습니다.`} />}
      </section>

      <p className="ops-limits">
        수집 데이터는 <b>구단×월 관중</b>과 <b>구단·연도 평균 경기시간</b>까지입니다.
        경기 단위 관중·소요시간이 없어 요일별·구장별·시작시간대별 집계, 최장/최단 경기, 소요시간 분포,
        구장 수용률은 계산할 수 없습니다. 관중은 2026시즌만 수집돼 있어 연도별 추이도 경기시간에만 있습니다.
      </p>
    </div>
  )
}

export default Ops
