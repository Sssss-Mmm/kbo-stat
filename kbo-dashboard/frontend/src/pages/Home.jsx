// HOME 대시보드 페이지.
// 선택한 시즌의 순위/경기결과/타자·투수 스탯/관중/경기시간을 한 번에 받아와
// (요약 카드, 타이틀 레이스, 리더보드, 분포 차트 등) 여러 패널로 가공해 보여준다.
// 무거운 파생 계산은 useMemo 로 감싸 데이터(d)/시즌이 바뀔 때만 재계산한다.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import Scatter from '../components/charts/Scatter'
import Beeswarm from '../components/charts/Beeswarm'
import RankRace from '../components/charts/RankRace'
import TodayGames from '../components/TodayGames'
import SeasonBanner from '../components/SeasonBanner'
import { teamColor, teamEmblem } from '../lib/teamColors'
import { MiniTable, BarList, TeamCell, Note } from '../components/MiniTable'
import { fmtRate, fmtOne, fmtTwo, fmtInt, fmtPct, fmtMinutes, parseRecord, recordWinRate, streakScore, recentWinRate } from '../lib/format'
import '../styles/Home.css'
import { apiError } from '../lib/apiError'

const TEAM_COUNT = 10

// "81 1/3" -> 81.333
function parseIP(s) {
  if (s === null || s === undefined) return 0
  const str = String(s).trim()
  const m = str.match(/^(\d+)(?:\s+(\d)\/3)?$/)
  if (m) return parseInt(m[1], 10) + (m[2] ? parseInt(m[2], 10) / 3 : 0)
  const f = parseFloat(str)
  return Number.isFinite(f) ? f : 0
}
const mean = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : NaN)

// ── 작은 프레젠테이션 컴포넌트들 (순수 표시용, 자체 상태 없음) ──

// [라벨, 값] 쌍 목록을 키-값 행으로 표시.
function StatRows({ rows }) {
  return (
    <div className="stat-rows">
      {rows.map(([k, v]) => (
        <div className="stat-row" key={k}><span>{k}</span><strong>{v}</strong></div>
      ))}
    </div>
  )
}

// 시즌 하이라이트 한 줄(부문 라벨 + 선수 + 값).
function HlItem({ label, player, val }) {
  const team = player?.['팀명']
  return (
    <li className="hl-item">
      <span className="hl-label">{label}</span>
      <span className="hl-player">
        {teamEmblem(team) && <img src={teamEmblem(team)} alt="" />}
        {player?.['선수명'] || '-'}
      </span>
      <strong className="hl-val">{val}</strong>
    </li>
  )
}

function Home({ seasonInfo, onOpsClick }) {
  // 순위·관중·경기시간은 백엔드가 판정한 활성 시즌 하나뿐이라 고를 게 없다.
  const season = seasonInfo.dataSeason
  const [d, setD] = useState({ standings: [], teamGames: [], hitters: [], pitchers: [], attendance: [], gameTime: [], failed: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // 시즌이 바뀔 때마다 6개 API 를 병렬 호출해 한 번에 적재. active 플래그로
  // 언마운트/시즌 재변경 시의 늦은 응답이 상태를 덮어쓰지 않게 막는다.
  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        // 실패한 요청은 빈 배열로 뭉개지 않고 어느 것이 실패했는지 기록한다(NFR-06).
        // 빈 배열은 "데이터가 없다", 실패 기록은 "못 받아왔다" — 화면에서 구분되어야 한다.
        const failed = []
        const get = (label, url, params) =>
          axios.get(url, { params }).then((r) => r.data.data || []).catch(() => { failed.push(label); return [] })
        const [standings, teamGames, hitters, pitchers, attendance, gameTime] = await Promise.all([
          get('순위', '/api/standings', { season }),
          get('경기 결과', '/api/team-games', { season }),
          get('타자 기록', '/api/player-stats', { role: 'hitter', season }),
          get('투수 기록', '/api/player-stats', { role: 'pitcher', season }),
          get('관중', '/api/attendance', { season }),
          get('경기시간', '/api/game-time/team', { season }),
        ])
        if (active) setD({ standings, teamGames, hitters, pitchers, attendance, gameTime, failed })
      } catch (err) {
        if (active) setError(apiError(err))
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [season])

  // 요약
  const summary = useMemo(() => {
    const { standings, hitters, pitchers } = d
    const byRank = [...standings].sort((a, b) => a.rank - b.rank)
    const leader = byRank[0]
    const streak = [...standings].sort((a, b) => streakScore(b.streak) - streakScore(a.streak))[0]
    const recent = [...standings].sort((a, b) => recentWinRate(b.last_10_games) - recentWinRate(a.last_10_games))[0]
    const warHit = [...hitters].sort((a, b) => (b.WAR || 0) - (a.WAR || 0))[0]
    const warPit = [...pitchers].sort((a, b) => (b.WAR || 0) - (a.WAR || 0))[0]
    const hr = [...hitters].sort((a, b) => (b.HR || 0) - (a.HR || 0))[0]
    return { leader, streak, recent, warHit, warPit, hr }
  }, [d])

  // 타이틀 레이스 (team-games 누적 순위)
  const race = useMemo(() => {
    const byDate = {}
    d.teamGames.forEach((g) => { (byDate[g.Date] ||= []).push(g) })
    const dates = Object.keys(byDate).sort()
    const cum = {}
    const seriesMap = {}
    dates.forEach((date, di) => {
      byDate[date].forEach((g) => {
        const c = (cum[g.Team] ||= { w: 0, l: 0 })
        c.w += g.Win || 0
        c.l += g.Loss || 0
      })
      const ranked = Object.keys(cum)
        .map((t) => ({ t, pct: cum[t].w / ((cum[t].w + cum[t].l) || 1), w: cum[t].w }))
        .sort((a, b) => b.pct - a.pct || b.w - a.w)
      if (ranked.length < TEAM_COUNT) return
      ranked.forEach((r, i) => { (seriesMap[r.t] ||= []).push({ index: di, rank: i + 1 }) })
    })
    const series = Object.entries(seriesMap).map(([team, points]) => ({ team, color: teamColor(team), points }))
    return { series, dateCount: dates.length }
  }, [d])

  // 팀 집계: 홈/원정 승률, 득실차
  const teamAgg = useMemo(() => {
    const homeAway = [...d.standings].sort((a, b) => a.rank - b.rank).map((s) => ({
      team: s.team, home: recordWinRate(s.home_record), away: recordWinRate(s.away_record),
    }))
    const diff = {}
    d.teamGames.forEach((g) => {
      const t = (diff[g.Team] ||= { rf: 0, ra: 0 })
      t.rf += g.RunsFor || 0
      t.ra += g.RunsAgainst || 0
    })
    const runDiff = Object.entries(diff)
      .map(([team, v]) => ({ label: team, value: v.rf - v.ra, color: teamColor(team) }))
      .sort((a, b) => b.value - a.value)
    return { homeAway, runDiff }
  }, [d])

  // 타자/투수 표본 필터
  const hitQ = useMemo(() => d.hitters.filter((h) => (h.AB || 0) >= 50), [d.hitters])
  const pitQ = useMemo(() => d.pitchers.filter((p) => parseIP(p.IP) >= 20), [d.pitchers])

  // 리그 평균(규정 충족 기준 + 전체 표본으로 비율)
  const league = useMemo(() => {
    const h = d.hitters.filter((x) => x['규정충족'])
    const p = d.pitchers.filter((x) => x['규정충족'])
    const sum = (arr, f) => arr.reduce((s, x) => s + (f(x) || 0), 0)
    const pa = sum(d.hitters, (x) => (x.AB || 0) + (x.BB || 0) + (x.HBP || 0))
    const ip = sum(d.pitchers, (x) => parseIP(x.IP))
    return {
      avg: mean(h.map((x) => x.AVG).filter(Number.isFinite)),
      obp: mean(h.map((x) => x.OBP).filter(Number.isFinite)),
      slg: mean(h.map((x) => x.SLG).filter(Number.isFinite)),
      ops: mean(h.map((x) => x.OPS).filter(Number.isFinite)),
      babip: mean(h.map((x) => x.BABIP).filter(Number.isFinite)),
      era: mean(p.map((x) => x.ERA).filter(Number.isFinite)),
      whip: mean(p.map((x) => x.WHIP).filter(Number.isFinite)),
      kPct: pa ? sum(d.hitters, (x) => x.SO) / pa : NaN,
      bbPct: pa ? sum(d.hitters, (x) => x.BB) / pa : NaN,
      hr9: ip ? (sum(d.pitchers, (x) => x.HR) * 9) / ip : NaN,
    }
  }, [d])

  // 시즌 하이라이트 (부문 1위)
  const highlights = useMemo(() => {
    const qH = d.hitters.filter((x) => x['규정충족'])
    const qP = d.pitchers.filter((x) => x['규정충족'])
    const top = (arr, f) => [...arr].sort((a, b) => f(b) - f(a))[0]
    return {
      avg: top(qH, (x) => x.AVG || 0),
      era: [...qP].sort((a, b) => (a.ERA ?? 99) - (b.ERA ?? 99))[0],
      hr: top(d.hitters, (x) => x.HR || 0),
      so: top(d.pitchers, (x) => x.SO || 0),
      sb: top(d.hitters, (x) => x.SB || 0),
    }
  }, [d])

  // 선구안(BB/K) · 제구력(K/BB) · 선발 안정성(QS%)
  const discipline = useMemo(() => {
    const bbk = d.hitters
      .filter((x) => x['규정충족'] && (x.SO || 0) > 0)
      .map((x) => ({ name: x['선수명'], team: x['팀명'], v: (x.BB || 0) / x.SO }))
      .sort((a, b) => b.v - a.v)
      .slice(0, 8)
    const kbb = [...d.pitchers]
      .filter((x) => x['규정충족'])
      .sort((a, b) => (b['K/BB'] || 0) - (a['K/BB'] || 0))
      .slice(0, 8)
    const qs = d.pitchers
      .filter((x) => (x.QS || 0) > 0 && parseIP(x.IP) >= 30)
      .map((x) => ({ name: x['선수명'], team: x['팀명'], v: (x.QS || 0) / (x.G || 1), qs: x.QS, g: x.G }))
      .sort((a, b) => b.v - a.v)
      .slice(0, 8)
    return { bbk, kbb, qs }
  }, [d])

  // 운영 데이터 요약
  const ops = useMemo(() => {
    // 실패한 요청의 파생값은 0 이 아니라 null 이어야 한다. 관중 조회가 죽었을 때
    // "총 관중 0" 을 그리면 없는 사실을 단정하는 것이 된다. fmt* 는 null 을 '-' 로 그린다.
    const attFailed = d.failed.includes('관중')
    const timeFailed = d.failed.includes('경기시간')
    const totals = d.attendance.filter((a) => a.Month === 0)
    const totalAtt = totals.reduce((s, a) => s + (a.Attendance || 0), 0)
    const topAtt = [...totals].sort((a, b) => (b.Attendance || 0) - (a.Attendance || 0))[0]
    const avgGameMin = mean(d.gameTime.map((g) => g.RegularInningMinutes).filter(Number.isFinite))
    return {
      totalAtt: attFailed ? null : totalAtt,
      topAtt: attFailed ? null : topAtt,
      avgGameMin: timeFailed ? null : avgGameMin,
    }
  }, [d])

  const RULES = [
    ['승부치기', '연장 10회부터 무사 1·2루로 시작하는 KBO 연장 규정.'],
    ['피치클락', '투수는 주자 없을 때 18초, 주자 있을 때 23초 내 투구.'],
    ['자동 고의4구', '공을 던지지 않고 1루 출루를 지시할 수 있는 규정.'],
    ['비디오 판독', '팀당 요청 가능 횟수 내에서 심판 판정을 재확인.'],
  ]

  return (
    <div className="home">
      <section className="home-hero">
        <div>
          <h2>한눈에 보는 {season} 시즌</h2>
        </div>
      </section>

      {/* NFR-06: 일부 요청만 실패한 경우 나머지 패널은 그대로 두고 실패 사실만 알린다. */}
      {d.failed?.length > 0 && (
        <p className="error">일부 데이터를 불러오지 못했습니다: {d.failed.join(', ')}</p>
      )}

      <SeasonBanner info={seasonInfo} selected={season} />

      {/* FR-12: 정규시즌·포스트시즌에만 오늘의 경기를 띄운다.
          오프시즌·개막전에는 경기가 없으므로 안내 + 아래 최종 순위/기록으로 대신한다. */}
      {seasonInfo.storyEnabled ? (
        <TodayGames
          standings={d.standings}
          storyEnabled={seasonInfo.storyEnabled}
          note={seasonInfo.state === 'postseason' ? 'PO 진행 중 · 포스트시즌 경기 데이터는 수집 범위 밖입니다.' : ''}
        />
      ) : (
        <section className="season-notice">
          <h3>{seasonInfo.state === 'preseason' ? `${seasonInfo.season} 시즌 개막까지 D-${seasonInfo.daysToOpening}` : '시즌 종료'}</h3>
          <p>
            {seasonInfo.state === 'preseason'
              ? `개막일 ${seasonInfo.opening} · 아래는 ${seasonInfo.dataSeason} 시즌 최종 순위와 기록입니다.`
              : `아래는 ${seasonInfo.dataSeason} 정규시즌 최종 순위와 기록입니다.`}
          </p>
        </section>
      )}

      {loading && <p className="loading">로딩중...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && d.standings.length > 0 && (
        <>
          {/* 요약 카드 */}
          <section className="card-grid">
            <article className="stat-card primary">
              <span className="kicker">현재 1위</span>
              <h3>{summary.leader?.team || '-'}</h3>
              <p>{summary.leader ? `${summary.leader.wins}승 ${summary.leader.losses}패 ${summary.leader.draws}무 · 승률 ${fmtRate(summary.leader.win_rate)}` : '-'}</p>
            </article>
            <article className="stat-card">
              <span className="kicker">연승/연패</span>
              <h3>{summary.streak?.team || '-'}</h3>
              <p>{summary.streak?.streak || '-'} · 최근 10경기 {summary.recent ? `${summary.recent.team}` : ''}</p>
            </article>
            <article className="stat-card">
              <span className="kicker">WAR 1위 타자</span>
              <h3>{summary.warHit?.['선수명'] || '-'}</h3>
              <p>{summary.warHit ? `${summary.warHit['팀명']} · WAR ${fmtTwo(summary.warHit.WAR)} · OPS ${fmtRate(summary.warHit.OPS)}` : '-'}</p>
            </article>
            <article className="stat-card">
              <span className="kicker">WAR 1위 투수</span>
              <h3>{summary.warPit?.['선수명'] || '-'}</h3>
              <p>{summary.warPit ? `${summary.warPit['팀명']} · WAR ${fmtTwo(summary.warPit.WAR)} · ERA ${fmtTwo(summary.warPit.ERA)}` : '-'}</p>
            </article>
            <article className="stat-card">
              <span className="kicker">홈런 1위</span>
              <h3>{summary.hr?.['선수명'] || '-'}</h3>
              <p>{summary.hr ? `${summary.hr['팀명']} · ${summary.hr.HR}홈런 · ${summary.hr.RBI}타점` : '-'}</p>
            </article>
            <article className="stat-card">
              <span className="kicker">리그 평균</span>
              <h3>{fmtRate(league.ops)} OPS</h3>
              <p>타율 {fmtRate(league.avg)} · ERA {fmtTwo(league.era)} · WHIP {fmtTwo(league.whip)}</p>
            </article>
          </section>

          {/* 팀: 타이틀 레이스 */}
          <section className="panel">
            <div className="panel-head"><h3>타이틀 레이스</h3><p>날짜별 누적 순위 변화</p></div>
            {d.failed.includes('경기 결과')
              ? <Note rows={null} />
              : <RankRace series={race.series} dateCount={race.dateCount} teamCount={TEAM_COUNT} />}
          </section>

          {/* 순위 + 홈/원정 성적 */}
          <section className="panel-grid-2">
            <article className="panel">
              <div className="panel-head"><h3>KBO 팀 순위</h3><p>{season}시즌</p></div>
              <MiniTable
                columns={[
                  { key: 'rk', label: '#', render: (_, i) => i + 1 },
                  { key: 'team', label: '팀', left: true, render: (r) => <TeamCell team={r.team} /> },
                  { key: 'games', label: 'G' },
                  { key: 'wins', label: '승' },
                  { key: 'losses', label: '패' },
                  { key: 'draws', label: '무' },
                  { key: 'win_rate', label: '승률', render: (r) => fmtRate(r.win_rate) },
                  { key: 'games_behind', label: '게임차', render: (r) => (r.games_behind ? fmtOne(r.games_behind) : '-') },
                  { key: 'streak', label: '연속' },
                ]}
                rows={[...d.standings].sort((a, b) => a.rank - b.rank)}
              />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>홈 / 원정 성적</h3><p>홈 승률 순</p></div>
              <MiniTable
                columns={[
                  { key: 'rk', label: '#', render: (_, i) => i + 1 },
                  { key: 'team', label: '팀', left: true, render: (r) => <TeamCell team={r.team} /> },
                  { key: 'hw', label: '홈승', render: (r) => parseRecord(r.home_record).w },
                  { key: 'hl', label: '홈패', render: (r) => parseRecord(r.home_record).l },
                  { key: 'hp', label: '홈승률', render: (r) => fmtRate(parseRecord(r.home_record).pct) },
                  { key: 'aw', label: '원정승', render: (r) => parseRecord(r.away_record).w },
                  { key: 'al', label: '원정패', render: (r) => parseRecord(r.away_record).l },
                  { key: 'ap', label: '원정승률', render: (r) => fmtRate(parseRecord(r.away_record).pct) },
                ]}
                rows={[...d.standings].sort((a, b) => (parseRecord(b.home_record).pct || 0) - (parseRecord(a.home_record).pct || 0))}
              />
            </article>
          </section>

          {/* 리그 평균 · 시즌 하이라이트 · 선발 안정성 */}
          <section className="panel-grid-4">
            <article className="panel">
              <div className="panel-head"><h3>리그 타격 평균</h3></div>
              <StatRows rows={[['AVG', fmtRate(league.avg)], ['OBP', fmtRate(league.obp)], ['SLG', fmtRate(league.slg)], ['OPS', fmtRate(league.ops)], ['BABIP', fmtRate(league.babip)]]} />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>리그 투구 평균</h3></div>
              <StatRows rows={[['ERA', fmtTwo(league.era)], ['WHIP', fmtTwo(league.whip)], ['K%', fmtPct(league.kPct)], ['BB%', fmtPct(league.bbPct)], ['HR/9', fmtTwo(league.hr9)]]} />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>시즌 하이라이트</h3></div>
              <ul className="hl-list">
                <HlItem label="타율" player={highlights.avg} val={fmtRate(highlights.avg?.AVG)} />
                <HlItem label="ERA" player={highlights.era} val={fmtTwo(highlights.era?.ERA)} />
                <HlItem label="홈런" player={highlights.hr} val={`${highlights.hr?.HR ?? '-'}`} />
                <HlItem label="탈삼진" player={highlights.so} val={`${highlights.so?.SO ?? '-'}`} />
                <HlItem label="도루" player={highlights.sb} val={`${highlights.sb?.SB ?? '-'}`} />
              </ul>
            </article>
            <article className="panel">
              <div className="panel-head"><h3>선발 안정성 (QS%)</h3><p>QS / 등판</p></div>
              <BarList items={discipline.qs.map((x) => ({ label: `${x.name} (${x.team})`, value: x.v, color: teamColor(x.team) }))} fmt={fmtPct} />
            </article>
          </section>

          {/* 선구안 · 제구력 · 득실차 */}
          <section className="panel-grid-3">
            <article className="panel">
              <div className="panel-head"><h3>타자 선구안 (BB/K)</h3><p>규정 타석 · 상위</p></div>
              <BarList items={discipline.bbk.map((x) => ({ label: `${x.name} (${x.team})`, value: x.v, color: teamColor(x.team) }))} fmt={fmtTwo} />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>투수 제구력 (K/BB)</h3><p>규정 이닝 · 상위</p></div>
              <BarList items={discipline.kbb.map((x) => ({ label: `${x['선수명']} (${x['팀명']})`, value: x['K/BB'] || 0, color: teamColor(x['팀명']) }))} fmt={fmtTwo} />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>팀 득실차</h3><p>득점 − 실점</p></div>
              {d.failed.includes('경기 결과')
                ? <Note rows={null} />
                : <BarList items={teamAgg.runDiff} fmt={(v) => (v > 0 ? `+${v}` : `${v}`)} />}
            </article>
          </section>

          {/* 타자 분석 */}
          <section className="panel">
            <div className="panel-head"><h3>타자 OPS 분포</h3><p>{hitQ.length}명 (AB 50+) · 팀 색상</p></div>
            <Beeswarm points={hitQ.map((h) => ({ value: h.OPS, color: teamColor(h['팀명']), label: h['선수명'] }))} label="OPS" fmt={fmtRate} />
          </section>

          <section className="panel-grid-2">
            <article className="panel">
              <div className="panel-head"><h3>ISO vs AVG</h3><p>장타력 vs 정확성</p></div>
              <Scatter points={hitQ.map((h) => ({ x: h.AVG, y: h.ISO, color: teamColor(h['팀명']), label: h['선수명'] }))} xLabel="AVG" yLabel="ISO" fmt={fmtRate} />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>OBP vs SLG</h3><p>출루 vs 장타</p></div>
              <Scatter points={hitQ.map((h) => ({ x: h.OBP, y: h.SLG, color: teamColor(h['팀명']), label: h['선수명'] }))} xLabel="OBP" yLabel="SLG" fmt={fmtRate} />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>선구안 (BB vs SO)</h3><p>볼넷 vs 삼진</p></div>
              <Scatter points={hitQ.map((h) => ({ x: h.SO, y: h.BB, color: teamColor(h['팀명']), label: h['선수명'] }))} xLabel="SO" yLabel="BB" fmt={fmtInt} showMeans />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>WHIP vs ERA</h3><p>{pitQ.length}명 (20이닝+)</p></div>
              <Scatter points={pitQ.map((p) => ({ x: p.WHIP, y: p.ERA, color: teamColor(p['팀명']), label: p['선수명'] }))} xLabel="WHIP" yLabel="ERA" fmt={fmtTwo} />
            </article>
          </section>

          {/* 홈런 경쟁 */}
          <section className="panel">
            <div className="panel-head"><h3>홈런 경쟁</h3><p>홈런 상위 10명 · 팀 색상</p></div>
            <BarList
              items={[...d.hitters].sort((a, b) => (b.HR || 0) - (a.HR || 0)).slice(0, 10).map((h) => ({ label: `${h['선수명']} (${h['팀명']})`, value: h.HR || 0, color: teamColor(h['팀명']) }))}
              fmt={fmtInt}
            />
          </section>

          {/* 리더보드 */}
          <section className="panel-grid-2">
            <article className="panel">
              <div className="panel-head"><h3>타격 리더 (OPS)</h3></div>
              <MiniTable
                columns={[
                  { key: 'rk', label: '#', render: (_, i) => i + 1 },
                  { key: '선수명', label: '선수', left: true },
                  { key: '팀명', label: '팀', left: true },
                  { key: 'OPS', label: 'OPS', render: (r) => fmtRate(r.OPS) },
                  { key: 'HR', label: 'HR' },
                  { key: 'WAR', label: 'WAR', render: (r) => fmtTwo(r.WAR) },
                ]}
                rows={[...hitQ].sort((a, b) => (b.OPS || 0) - (a.OPS || 0)).slice(0, 10)}
              />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>평균자책점 리더 (ERA)</h3></div>
              <MiniTable
                columns={[
                  { key: 'rk', label: '#', render: (_, i) => i + 1 },
                  { key: '선수명', label: '선수', left: true },
                  { key: '팀명', label: '팀', left: true },
                  { key: 'ERA', label: 'ERA', render: (r) => fmtTwo(r.ERA) },
                  { key: 'SO', label: 'SO' },
                  { key: 'WAR', label: 'WAR', render: (r) => fmtTwo(r.WAR) },
                ]}
                rows={[...pitQ].sort((a, b) => (a.ERA || 99) - (b.ERA || 99)).slice(0, 10)}
              />
            </article>
            <article className="panel">
              <div className="panel-head"><h3>도루 리더</h3></div>
              <BarList
                items={[...d.hitters].sort((a, b) => (b.SB || 0) - (a.SB || 0)).slice(0, 8).map((h) => ({ label: `${h['선수명']} (${h['팀명']})`, value: h.SB || 0, color: teamColor(h['팀명']) }))}
                fmt={fmtInt}
              />
            </article>
            <article className="panel ops-summary">
              <div className="panel-head">
                <h3>운영 요약</h3>
                {/* 상세(월별 관중·연도별 경기시간)는 리그 운영 화면으로 보낸다 */}
                {onOpsClick && <button className="panel-link" onClick={onOpsClick}>리그 운영 →</button>}
              </div>
              <div className="ops-boxes">
                <div className="ops-box"><span>총 관중</span><strong>{fmtInt(ops.totalAtt)}</strong></div>
                <div className="ops-box"><span>최다 관중 팀</span><strong>{ops.topAtt?.Team || '-'}</strong></div>
                <div className="ops-box"><span>평균 경기시간</span><strong>{fmtMinutes(ops.avgGameMin)}</strong></div>
                <div className="ops-box"><span>리그 평균 타율</span><strong>{fmtRate(league.avg)}</strong></div>
              </div>
            </article>
          </section>

          {/* 규칙 가이드 */}
          <section className="panel">
            <div className="panel-head"><h3>야구 규칙 가이드</h3><p>KBO 주요 규정</p></div>
            <div className="rules-grid">
              {RULES.map(([t, desc]) => (
                <article className="rule-card" key={t}><strong>{t}</strong><span>{desc}</span></article>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  )
}

export default Home
