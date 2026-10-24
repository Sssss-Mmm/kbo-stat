// 경기일정 페이지(P2-C). /api/v2/schedule 로 한 달 달력과 선택한 날의 경기 목록을 보여 준다.
// 상태는 종료·무승부·취소(사유)·예정, 더블헤더는 1·2차전. 박스스코어가 있는 경기만 상세 링크를 건다.
// 시즌·달·날짜·팀은 URL 쿼리(season, month=YYYY-M, date, team). '오늘' 기준이 아니라 보유 자료 범위 안에서 고른다.
import { useMemo } from 'react'
import { TEAM_COLORS, teamColor, teamEmblem } from '../lib/teamColors'
import { useRoute } from '../lib/useRoute'
import { updateQuery } from '../lib/navigation'
import { emptyScheduleMessage, fetchSchedule, fetchSeasons, GAME_STATUS, intParam,
  SCHEDULE_SOURCE_LABEL } from '../lib/v2'
import { GameLink, LoadState, SourceLine, useV2 } from '../components/V2Bits'
import '../styles/Schedule.css'
import '../styles/V2.css'

const TEAMS = Object.keys(TEAM_COLORS)
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']
const pad = (n) => String(n).padStart(2, '0')
const monthKey = (y, m) => `${y}-${m}` // m: 1-12

function monthsBetween(first, last) {
  if (!first || !last) return []
  const out = []
  let [y, m] = first.split('-').map(Number)
  const [ly, lm] = last.split('-').map(Number)
  while (y < ly || (y === ly && m <= lm)) {
    out.push(monthKey(y, m))
    if (++m > 12) { m = 1; y += 1 }
  }
  return out
}

function Schedule() {
  const { query } = useRoute()
  const seasons = useV2(fetchSeasons, [])
  const held = (seasons.data?.data || []).filter((s) => s.schedule)
  const season = intParam(query, 'season', held.at(-1)?.season ?? null)
  const range = held.find((s) => s.season === season)?.schedule
  const months = useMemo(() => monthsBetween(range?.first_date, range?.last_date), [range?.first_date, range?.last_date])
  // 기본 달: 보유 자료의 마지막 경기 달(오늘 날짜를 쓰지 않는다)
  const lastPlayed = range?.last_played_date || range?.last_date
  const viewKey = months.includes(query.get('month')) ? query.get('month')
    : lastPlayed ? monthKey(...lastPlayed.split('-').slice(0, 2).map(Number)) : ''
  const [vy, vm] = viewKey ? viewKey.split('-').map(Number) : [season, 1]
  const selectedTeam = TEAMS.includes(query.get('team')) ? query.get('team') : ''
  const day = query.get('date') || null

  const month = useV2(() => (viewKey ? fetchSchedule({ season: vy, month: vm }) : Promise.resolve(null)), [viewKey])
  const detail = useV2(() => (day ? fetchSchedule({ date: day }) : Promise.resolve(null)), [day])

  const byDate = useMemo(() => {
    const map = {}
    for (const g of month.data?.data || []) (map[g.date] ||= []).push(g)
    return map
  }, [month.data])

  const weeks = useMemo(() => {
    if (!viewKey) return []
    const cells = Array(new Date(vy, vm - 1, 1).getDay()).fill(null)
    for (let d = 1; d <= new Date(vy, vm, 0).getDate(); d++) cells.push(d)
    while (cells.length % 7) cells.push(null)
    return cells
  }, [viewKey, vy, vm])

  const forTeam = (list) => (selectedTeam ? list.filter((g) => g.home.team === selectedTeam || g.away.team === selectedTeam) : list)
  const monthIndex = months.indexOf(viewKey)

  return (
    <div className="schedule-container">
      <div className="schedule-filters">
        <h2>{season ? `${season}시즌 경기일정` : '경기일정'}</h2>
        <div className="v2-controls">
          <select value={season ?? ''} onChange={(e) => updateQuery({ season: e.target.value, month: null, date: null })} aria-label="시즌">
            {[...held].reverse().map((s) => <option key={s.season} value={s.season}>{s.season} 시즌</option>)}
          </select>
          <label className="v2-inline">날짜
            <input type="date" value={day || ''} onChange={(e) => {
              const d = e.target.value || null
              updateQuery({ date: d, ...(d ? { season: d.slice(0, 4), month: `${Number(d.slice(0, 4))}-${Number(d.slice(5, 7))}` } : {}) })
            }} />
          </label>
        </div>
        <div className="team-chips">
          <button className={`team-chip${selectedTeam === '' ? ' active' : ''}`} onClick={() => updateQuery({ team: null })}
            style={selectedTeam === '' ? { background: '#33404a', borderColor: '#33404a', color: '#fff' } : {}}>전체</button>
          {TEAMS.map((t) => {
            const active = selectedTeam === t
            const c = teamColor(t)
            return (
              <button key={t} className={`team-chip${active ? ' active' : ''}`} onClick={() => updateQuery({ team: active ? null : t })}
                style={active ? { background: c, borderColor: c, color: '#fff' } : { borderColor: c, color: c }}>
                {teamEmblem(t) && <img className="chip-emblem" src={teamEmblem(t)} alt="" />}
                {t}
              </button>
            )
          })}
        </div>
      </div>

      {range && <p className="v2-note">보유 범위 {range.first_date} ~ {range.last_date} 정규시즌 · 종료 {range.played}경기(무승부 {range.ties}) · 취소 {range.canceled}경기{range.scheduled > 0 && ` · 예정 ${range.scheduled}경기`} · 포스트시즌 자료 없음</p>}

      {day && (
        <section className="v2-section sched-day" aria-label={`${day} 경기`}>
          <h3>{day} 경기 <button className="v2-link-btn" onClick={() => updateQuery({ date: null })}>닫기</button></h3>
          <LoadState state={detail} empty={detail.data && !forTeam(detail.data.data).length
            ? (detail.data.data.length ? '선택한 팀의 경기가 없습니다.' : emptyScheduleMessage(detail.data.reason, detail.data.range)) : null} />
          {detail.data && forTeam(detail.data.data).length > 0 && (
            <div className="v2-table-wrap">
              <table className="v2-table">
                <thead><tr><th className="lalign">시간</th><th className="lalign">원정</th><th>점수</th><th className="lalign">홈</th>
                  <th className="lalign">상태</th><th className="lalign">구장</th><th className="lalign">상세</th></tr></thead>
                <tbody>
                  {forTeam(detail.data.data).map((g, i) => (
                    <tr key={g.game_id || `${g.away.team}-${i}`}>
                      <td className="lalign">{g.time || '-'}{g.doubleheader && <span className="v2-pill">DH {g.doubleheader}차전</span>}</td>
                      <td className="lalign">{g.away.team}</td>
                      <td>{g.away.score ?? '-'} : {g.home.score ?? '-'}</td>
                      <td className="lalign">{g.home.team}</td>
                      <td className="lalign">{GAME_STATUS[g.status] || g.status}{g.cancel_reason && ` (${g.cancel_reason})`}</td>
                      <td className="lalign">{g.ballpark || '-'}</td>
                      <td className="lalign">{g.has_box ? <GameLink id={g.game_id}>박스스코어</GameLink> : <span className="muted">-</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <LoadState state={seasons.loading ? seasons : month} empty={!seasons.loading && !held.length ? '일정 자료가 없습니다.' : null} />
      {viewKey && month.data && (
        <>
          <div className="cal-nav">
            <button className="cal-nav-btn" disabled={monthIndex <= 0} onClick={() => updateQuery({ month: months[monthIndex - 1] })} aria-label="이전 달">‹</button>
            <span className="cal-title">{vy}년 {vm}월</span>
            <button className="cal-nav-btn" disabled={monthIndex >= months.length - 1} onClick={() => updateQuery({ month: months[monthIndex + 1] })} aria-label="다음 달">›</button>
          </div>
          <div className="cal-grid">
            {WEEKDAYS.map((w, i) => <div key={w} className={`cal-wd${i === 0 ? ' sun' : ''}${i === 6 ? ' sat' : ''}`}>{w}</div>)}
            {weeks.map((d, idx) => {
              if (d === null) return <div key={idx} className="cal-cell empty" />
              const dateStr = `${vy}-${pad(vm)}-${pad(d)}`
              const wd = idx % 7
              return (
                <div key={idx} className={`cal-cell${dateStr === day ? ' selected' : ''}`}>
                  <button className={`cal-date sched-date${wd === 0 ? ' sun' : ''}${wd === 6 ? ' sat' : ''}`}
                    onClick={() => updateQuery({ date: dateStr })} aria-label={`${dateStr} 경기 보기`}>{d}</button>
                  <div className="cal-games">
                    {forTeam(byDate[dateStr] || []).map((g, i) => (selectedTeam
                      ? <TeamGame key={i} g={g} team={selectedTeam} />
                      : <Game key={i} g={g} onTeam={(t) => updateQuery({ team: t })} />))}
                  </div>
                </div>
              )
            })}
          </div>
          {!month.data.data.length && <p className="v2-empty">{emptyScheduleMessage(month.data.reason, month.data.range)}</p>}
          <SourceLine label={SCHEDULE_SOURCE_LABEL} fetchedAt={month.data.meta.sources?.[0]?.collected_at}
            extra={`박스스코어 상세 기록은 ${held.filter((s) => s.box_games).map((s) => s.season).join('·') || '없음'} 시즌만`} />
        </>
      )}
    </div>
  )
}

const done = (g) => g.status === 'final' || g.status === 'tie'

// 전체 보기용 경기 칩: 원정 : 홈
function Game({ g, onTeam }) {
  return (
    <div className={`game-chip${g.status === 'canceled' ? ' sched-canceled' : ''}`} title={g.cancel_reason || undefined}>
      <button className="g-team team-ink" style={{ '--team-c': teamColor(g.away.team) }} onClick={() => onTeam(g.away.team)}>
        {teamEmblem(g.away.team) && <img className="g-emblem" src={teamEmblem(g.away.team)} alt="" />}
        {g.away.team}
      </button>
      <span className="g-score">{done(g) ? `${g.away.score} : ${g.home.score}` : g.status === 'canceled' ? '취소' : g.time || 'vs'}</span>
      <button className="g-team team-ink" style={{ '--team-c': teamColor(g.home.team) }} onClick={() => onTeam(g.home.team)}>
        {teamEmblem(g.home.team) && <img className="g-emblem" src={teamEmblem(g.home.team)} alt="" />}
        {g.home.team}
      </button>
    </div>
  )
}

// 팀 필터 보기용 경기 칩: 팀 관점 (vs/@ 상대, 승패)
function TeamGame({ g, team }) {
  const isHome = g.home.team === team
  const opp = isHome ? g.away.team : g.home.team
  const my = isHome ? g.home.score : g.away.score
  const their = isHome ? g.away.score : g.home.score
  const cls = !done(g) ? 'tg-pending' : my > their ? 'tg-win' : my < their ? 'tg-loss' : 'tg-draw'
  return (
    <div className={`game-chip team ${cls}`} style={{ borderLeftColor: teamColor(opp) }} title={g.cancel_reason || undefined}>
      <span className="tg-loc">{isHome ? 'vs' : '@'}</span>
      {teamEmblem(opp) && <img className="g-emblem" src={teamEmblem(opp)} alt="" />}
      <span className="tg-opp">{opp}</span>
      <span className="tg-score">
        {done(g) ? `${my} : ${their}` : g.status === 'canceled' ? '취소' : g.time || '-'}
        {done(g) && <b className="tg-res">{my > their ? '승' : my < their ? '패' : '무'}</b>}
      </span>
    </div>
  )
}

export default Schedule
