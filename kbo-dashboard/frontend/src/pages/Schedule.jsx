// 경기일정 페이지. /api/schedule-games 를 받아 달력(월 단위)로 보여준다.
// 팀 칩으로 특정 팀만 필터하면 그 팀 관점(vs/@ 상대, 승패)으로 칩이 바뀐다.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { TEAM_COLORS, teamColor, teamEmblem } from '../lib/teamColors'
import SeasonBanner from '../components/SeasonBanner'
import { kstToday, seasonOptions } from '../lib/season'
import '../styles/Schedule.css'
import { apiError } from '../lib/apiError'

const TEAMS = Object.keys(TEAM_COLORS)
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

const pad = (n) => String(n).padStart(2, '0')
const monthKey = (y, m) => `${y}-${m}` // m: 1-12

// 시즌 상태별 일정 안내 (FR-12): 오프시즌은 조회 전용, 포스트시즌은 PO 일정 미수집.
const SCHEDULE_NOTE = {
  postseason: 'PO 일정은 수집 범위 밖 · 정규시즌 일정만 표시합니다',
  offseason: '최종 결과 조회만 가능합니다',
  preseason: '개막 일정',
}

function Schedule({ seasonInfo }) {
  const [games, setGames] = useState([])
  // 일정 데이터는 2026 한 시즌뿐이다(season.js SEASONS.league).
  const season = seasonOptions('league')[0]
  const [selectedTeam, setSelectedTeam] = useState('')
  const [viewKey, setViewKey] = useState('') // "YYYY-M"
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    axios
      .get('/api/schedule-games', { params: { season } })
      .then((res) => {
        if (!active) return
        setGames(res.data.status === 'success' ? res.data.data : [])
        if (res.data.status !== 'success') setError('경기 일정을 가져오는데 실패했습니다.')
      })
      .catch((err) => active && setError(apiError(err)))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [season])

  // 데이터가 존재하는 달 목록 (오름차순)
  const months = useMemo(() => {
    const set = new Set()
    for (const g of games) {
      if (!g.Date) continue
      const [y, m] = g.Date.split('-').map(Number)
      set.add(monthKey(y, m))
    }
    return [...set].sort((a, b) => {
      const [ay, am] = a.split('-').map(Number)
      const [by, bm] = b.split('-').map(Number)
      return ay - by || am - bm
    })
  }, [games])

  // 데이터 로드 시 표시할 달 결정: 오늘이 속한 달 > 마지막 달
  useEffect(() => {
    if (months.length === 0) {
      setViewKey('')
      return
    }
    const [ty, tm] = kstToday().split('-').map(Number)  // 오늘(KST)
    const todayKey = monthKey(ty, tm)
    if (months.includes(todayKey)) {
      setViewKey(todayKey)
      return
    }
    // 오늘이 일정 밖이면: 개막 전이면 첫 달, 시즌 종료 후면 마지막 달
    const [fy, fm] = months[0].split('-').map(Number)
    const before = ty < fy || (ty === fy && tm < fm)
    setViewKey(before ? months[0] : months[months.length - 1])
  }, [months])

  // 날짜별 경기 묶음
  const byDate = useMemo(() => {
    const map = {}
    for (const g of games) {
      if (!g.Date) continue
      ;(map[g.Date] ||= []).push(g)
    }
    return map
  }, [games])

  const monthIndex = months.indexOf(viewKey)
  const [vy, vm] = viewKey ? viewKey.split('-').map(Number) : [season, 1]

  // 달력 셀 구성 (일~토, 6주까지)
  const weeks = useMemo(() => {
    if (!viewKey) return []
    const firstWeekday = new Date(vy, vm - 1, 1).getDay()
    const daysInMonth = new Date(vy, vm, 0).getDate()
    const cells = []
    for (let i = 0; i < firstWeekday; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(d)
    while (cells.length % 7 !== 0) cells.push(null)
    const out = []
    for (let i = 0; i < cells.length; i += 7) out.push(cells.slice(i, i + 7))
    return out
  }, [viewKey, vy, vm])

  const todayStr = kstToday()

  const visibleForDay = (day) => {
    const key = `${vy}-${pad(vm)}-${pad(day)}`
    let list = byDate[key] || []
    if (selectedTeam) {
      list = list.filter((g) => g.home_team === selectedTeam || g.away_team === selectedTeam)
    }
    return list
  }

  return (
    <div className="schedule-container">
      {/* 일정은 활성 시즌(개막전이면 다음 시즌) 기준이라, 기본 선택일 때는 배너를 '과거 시즌'으로 표시하지 않는다 */}
      <SeasonBanner
        info={seasonInfo}
        selected={season === seasonInfo.season ? seasonInfo.dataSeason : season}
        note={SCHEDULE_NOTE[seasonInfo.state] || ''}
      />
      <div className="schedule-filters">
        <h2>{season}시즌 경기일정</h2>
        <div className="team-chips">
          <button
            className={`team-chip${selectedTeam === '' ? ' active' : ''}`}
            onClick={() => setSelectedTeam('')}
            style={selectedTeam === '' ? { background: '#33404a', borderColor: '#33404a', color: '#fff' } : {}}
          >
            전체
          </button>
          {TEAMS.map((t) => {
            const active = selectedTeam === t
            const c = teamColor(t)
            return (
              <button
                key={t}
                className={`team-chip${active ? ' active' : ''}`}
                onClick={() => setSelectedTeam(active ? '' : t)}
                style={
                  active
                    ? { background: c, borderColor: c, color: '#fff' }
                    : { borderColor: c, color: c }
                }
              >
                {teamEmblem(t) && <img className="chip-emblem" src={teamEmblem(t)} alt="" />}
                {t}
              </button>
            )
          })}
        </div>
      </div>

      {loading && <p className="loading">로딩중...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && viewKey && (
        <>
          <div className="cal-nav">
            <button
              className="cal-nav-btn"
              disabled={monthIndex <= 0}
              onClick={() => setViewKey(months[monthIndex - 1])}
            >
              ‹
            </button>
            <span className="cal-title">
              {vy}년 {vm}월
            </span>
            <button
              className="cal-nav-btn"
              disabled={monthIndex >= months.length - 1}
              onClick={() => setViewKey(months[monthIndex + 1])}
            >
              ›
            </button>
          </div>

          <div className="cal-grid">
            {WEEKDAYS.map((w, i) => (
              <div key={w} className={`cal-wd${i === 0 ? ' sun' : ''}${i === 6 ? ' sat' : ''}`}>
                {w}
              </div>
            ))}
            {weeks.flat().map((day, idx) => {
              if (day === null) return <div key={idx} className="cal-cell empty" />
              const dateStr = `${vy}-${pad(vm)}-${pad(day)}`
              const wd = idx % 7
              const list = visibleForDay(day)
              return (
                <div key={idx} className={`cal-cell${dateStr === todayStr ? ' today' : ''}`}>
                  <div className={`cal-date${wd === 0 ? ' sun' : ''}${wd === 6 ? ' sat' : ''}`}>{day}</div>
                  <div className="cal-games">
                    {list.map((g, i) =>
                      selectedTeam ? (
                        <TeamGame key={i} g={g} team={selectedTeam} />
                      ) : (
                        <Game key={i} g={g} onTeam={setSelectedTeam} />
                      )
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}

      {!loading && !error && !viewKey && (
        <p className="loading">
          {seasonInfo.state === 'preseason' ? '개막 일정이 아직 공개되지 않았습니다.' : `${season}시즌 경기 일정이 없습니다.`}
        </p>
      )}
    </div>
  )
}

// 전체 보기용 경기 칩: 원정 @ 홈
function Game({ g, onTeam }) {
  const done = g.status === 'final' && g.home_score != null && g.away_score != null
  return (
    <div className="game-chip">
      <button className="g-team team-ink" style={{ '--team-c': teamColor(g.away_team) }} onClick={() => onTeam(g.away_team)}>
        {teamEmblem(g.away_team) && <img className="g-emblem" src={teamEmblem(g.away_team)} alt="" />}
        {g.away_team}
      </button>
      <span className="g-score">{done ? `${g.away_score} : ${g.home_score}` : g.Time || 'vs'}</span>
      <button className="g-team team-ink" style={{ '--team-c': teamColor(g.home_team) }} onClick={() => onTeam(g.home_team)}>
        {teamEmblem(g.home_team) && <img className="g-emblem" src={teamEmblem(g.home_team)} alt="" />}
        {g.home_team}
      </button>
    </div>
  )
}

// 팀 필터 보기용 경기 칩: 팀 관점 (vs/@ 상대, 승패)
function TeamGame({ g, team }) {
  const isHome = g.home_team === team
  const opp = isHome ? g.away_team : g.home_team
  const done = g.status === 'final' && g.home_score != null && g.away_score != null
  const my = isHome ? g.home_score : g.away_score
  const their = isHome ? g.away_score : g.home_score
  let cls = 'tg-pending'
  if (done) cls = my > their ? 'tg-win' : my < their ? 'tg-loss' : 'tg-draw'
  return (
    <div className={`game-chip team ${cls}`} style={{ borderLeftColor: teamColor(opp) }}>
      <span className="tg-loc">{isHome ? 'vs' : '@'}</span>
      {teamEmblem(opp) && <img className="g-emblem" src={teamEmblem(opp)} alt="" />}
      <span className="tg-opp">{opp}</span>
      <span className="tg-score">
        {done ? `${my} : ${their}` : g.Time || '-'}
        {done && <b className="tg-res">{my > their ? '승' : my < their ? '패' : '무'}</b>}
      </span>
    </div>
  )
}

export default Schedule
