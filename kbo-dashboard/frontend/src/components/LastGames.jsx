// 홈 상단(P2-C): 실시간 '오늘의 경기' 대신 보유 자료의 마지막 경기일 결과. /api/v2/home.
// 수집이 멈춰 있으므로 '오늘'·'현재' 를 쓰지 않고 날짜와 수집 시점을 함께 적는다.
import { GameLink, LoadState, useV2 } from './V2Bits'
import { fetchHome, fmtKst, GAME_STATUS } from '../lib/v2'
import { pageUrl, followLink } from '../lib/navigation'
import { teamColor, teamEmblem } from '../lib/teamColors'
import '../styles/V2.css'

// season: 홈이 고른 시즌(홈 전체 카드와 같은 값). 시즌 선택은 홈 상단 하나뿐이다.
function LastGames({ season }) {
  const state = useV2(() => fetchHome(season || undefined), [season])
  const body = state.data
  return (
    <section className="v2-section last-games" aria-label="마지막 경기 결과">
      <div className="v2-head">
        <h3>{body ? `${body.season} 시즌 마지막 경기 결과 · ${body.last_games.date || '-'}` : '마지막 경기 결과'}</h3>
      </div>
      <LoadState state={state} empty={body && !body.last_games.games.length ? '이 시즌에는 끝난 경기가 없습니다.' : null} />
      {body && (
        <>
          <p className="v2-note">
            보유 자료의 마지막 경기일입니다(실시간 아님) · {body.season} 자료 수집 {fmtKst(body.banner.season_collected_at)}
            {body.banner.remaining_scheduled > 0 ? ` · 남은 예정 경기 ${body.banner.remaining_scheduled}` : ' · 정규시즌 종료'} · 포스트시즌 자료 없음
          </p>
          <div className="lg-grid">
            {body.last_games.games.map((g, i) => {
              const done = g.status === 'final' || g.status === 'tie'
              return (
                <article key={g.game_id || i} className="lg-card">
                  {[g.away, g.home].map((side, k) => (
                    <div key={k} className={`lg-team${done && side.score > (k ? g.away : g.home).score ? ' win' : ''}`}
                      style={{ '--team-c': teamColor(side.team) }}>
                      {teamEmblem(side.team) && <img className="g-emblem" src={teamEmblem(side.team)} alt="" />}
                      <span>{side.team}</span><b>{side.score ?? '-'}</b>
                    </div>
                  ))}
                  <p className="lg-meta">
                    {GAME_STATUS[g.status]}{g.cancel_reason && ` (${g.cancel_reason})`}{g.doubleheader && ` · DH ${g.doubleheader}차전`} · {g.ballpark}
                    {' · '}{g.has_box ? <GameLink id={g.game_id}>박스스코어</GameLink> : <span className="muted">상세 기록 없음</span>}
                  </p>
                </article>
              )
            })}
          </div>
          <p className="v2-foot">
            <a href={pageUrl('schedule', { season: body.season, date: body.last_games.date })} onClick={followLink}>이 날 일정 전체</a>
            {' · '}<a href={pageUrl('standings', { season: body.season })} onClick={followLink}>{body.season} 순위표</a>
          </p>
        </>
      )}
    </section>
  )
}

export default LastGames
