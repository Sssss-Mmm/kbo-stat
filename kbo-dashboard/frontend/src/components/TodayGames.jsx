// 오늘의 경기 카드 섹션 (HOME 상단).
// /api/today-games(라이브 경기/스코어/선발)와 /api/today-story(AI 프리뷰/리뷰)를
// 따로 받아 날짜별 카드로 보여준다. 경기 전이면 시즌 성적 기반 예상 승률 막대를 표시.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { teamColor, teamEmblem } from '../lib/teamColors'
import '../styles/TodayGames.css'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']
const pad = (n) => String(n).padStart(2, '0')
const toKey = (dt) => `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`

// "19-0-10"(승-무-패) -> 승률
function recordWinRate(s) {
  if (!s) return null
  const [w, , l] = String(s).split('-').map((x) => parseInt(x, 10) || 0)
  return w + l ? w / (w + l) : null
}

// log5: 승률 a 팀이 승률 b 팀을 이길 확률
function log5(a, b) {
  const d = a * (1 - b) + b * (1 - a)
  return d ? (a * (1 - b)) / d : 0.5
}

function TodayGames({ standings = [] }) {
  const [date, setDate] = useState(toKey(new Date()))
  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [stories, setStories] = useState({}) // gameId -> story
  const [storyLoading, setStoryLoading] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    axios
      .get('/api/today-games', { params: { date } })
      .then((r) => active && setGames(r.data.data || []))
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [date])

  // AI 데일리 스토리: 경기 목록과 별개로(느릴 수 있어) 받아 gameId로 매핑.
  useEffect(() => {
    let active = true
    setStories({})
    setStoryLoading(true)
    axios
      .get('/api/today-story', { params: { date } })
      .then((r) => {
        if (!active) return
        const map = {}
        for (const s of r.data.data || []) map[s.gameId] = s
        setStories(map)
      })
      .catch(() => active && setStories({}))
      .finally(() => active && setStoryLoading(false))
    return () => {
      active = false
    }
  }, [date])

  const standMap = useMemo(() => {
    const m = {}
    for (const s of standings) m[s.team] = s
    return m
  }, [standings])

  // 홈 관점 예상 승률. 홈/원정 성적이 있으면 그걸, 없으면 전체 승률 사용.
  const homeWinProb = (g) => {
    const h = standMap[g.home?.name]
    const a = standMap[g.away?.name]
    if (!h || !a) return null
    const hr = recordWinRate(h.home_record) ?? h.win_rate
    const ar = recordWinRate(a.away_record) ?? a.win_rate
    if (!Number.isFinite(hr) || !Number.isFinite(ar)) return null
    // log5 + 소폭 홈 어드밴티지
    let p = log5(hr, ar) + 0.04
    return Math.min(0.85, Math.max(0.15, p))
  }

  const shift = (days) => {
    const [y, m, d] = date.split('-').map(Number)
    const dt = new Date(y, m - 1, d + days)
    setDate(toKey(dt))
  }

  const label = useMemo(() => {
    const [y, m, d] = date.split('-').map(Number)
    const wd = WEEKDAYS[new Date(y, m - 1, d).getDay()]
    return `${y}년 ${m}월 ${d}일 (${wd})`
  }, [date])

  return (
    <section className="today-games">
      <div className="tg-head">
        <h3>{label}</h3>
        <div className="tg-nav">
          <button onClick={() => shift(-1)} aria-label="이전 날">‹</button>
          <button className="tg-today" onClick={() => setDate(toKey(new Date()))}>오늘</button>
          <button onClick={() => shift(1)} aria-label="다음 날">›</button>
        </div>
      </div>

      {loading && <p className="tg-msg">로딩중...</p>}
      {error && <p className="tg-msg error">{error}</p>}
      {!loading && !error && games.length === 0 && <p className="tg-msg">이 날 예정된 경기가 없습니다.</p>}

      {!loading && !error && games.length > 0 && (
        <div className="tg-cards">
          {games.map((g) => {
            const done = g.statusCode === 'RESULT'
            const started = g.statusCode && g.statusCode !== 'BEFORE'
            const hp = homeWinProb(g)
            const ap = hp == null ? null : 1 - hp
            const awayWon = done && g.winner === 'AWAY'
            const homeWon = done && g.winner === 'HOME'
            return (
              <article className="tg-card" key={g.gameId}>
                <div className="tg-meta">
                  <span>{g.cancel ? '취소' : g.time}</span>
                  <span className="tg-stadium">{g.stadium}{started && !done ? ' · 진행중' : ''}</span>
                </div>

                <div className="tg-match">
                  <Team t={g.away} won={awayWon} loser={done && !awayWon} />
                  <div className="tg-center">
                    {started ? (
                      <span className="tg-score"><b className={awayWon ? 'w' : ''}>{g.away.score ?? '-'}</b> : <b className={homeWon ? 'w' : ''}>{g.home.score ?? '-'}</b></span>
                    ) : (
                      <span className="tg-vs">VS</span>
                    )}
                  </div>
                  <Team t={g.home} won={homeWon} loser={done && !homeWon} home />
                </div>

                {!started && ap != null && (
                  <div className="tg-prob" title="예상 승률 (시즌 성적 기반)">
                    <div className="tg-prob-bar">
                      <span className="tg-prob-fill away" style={{ width: `${ap * 100}%`, background: teamColor(g.away.name) }} />
                      <span className="tg-prob-fill home" style={{ width: `${hp * 100}%`, background: teamColor(g.home.name) }} />
                    </div>
                    <div className="tg-prob-nums">
                      <span>{Math.round(ap * 100)}%</span>
                      <span className="tg-prob-tag">예상 승률</span>
                      <span>{Math.round(hp * 100)}%</span>
                    </div>
                  </div>
                )}

                {(g.away.starter || g.home.starter) && (
                  <div className="tg-starters">
                    <span className="tg-pit away">{g.away.starter || '미정'}</span>
                    <span className="tg-pit-label">선발</span>
                    <span className="tg-pit home">{g.home.starter || '미정'}</span>
                  </div>
                )}

                <div className="tg-story">
                  <span className="tg-story-tag">{done ? 'AI 리뷰' : 'AI 프리뷰'}</span>
                  {stories[g.gameId]?.story ? (
                    <p>{stories[g.gameId].story}</p>
                  ) : (
                    <p className="tg-story-skel">{storyLoading ? 'AI가 이야기를 쓰는 중...' : '—'}</p>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

function Team({ t, won, loser, home }) {
  const emblem = teamEmblem(t.name) || t.emblem
  return (
    <div className={`tg-team${won ? ' won' : ''}${loser ? ' loser' : ''}`}>
      {emblem && <img src={emblem} alt={t.name} loading="lazy" />}
      <span className="tg-name" style={{ color: teamColor(t.name) }}>{t.name}</span>
      <span className="tg-ha">{home ? '홈' : '원정'}</span>
    </div>
  )
}

export default TodayGames
