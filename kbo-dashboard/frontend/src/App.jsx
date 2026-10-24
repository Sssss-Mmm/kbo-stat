// URL 기반 페이지 이동과 공통 헤더.
// 상단 헤더(네비게이션 + 다크/라이트 테마 토글)와 본문 페이지로 구성된다.
import { useState, useEffect } from 'react'
import axios from 'axios'
import Home from './pages/Home'
import Standings from './pages/Standings'
import Race from './pages/Race'
import Teams from './pages/Teams'
import Schedule from './pages/Schedule'
import Players from './pages/Players'
import Zones from './pages/Zones'
import Ops from './pages/Ops'
import Ask from './pages/Ask'
import Leaders from './pages/Leaders'
import PlayerV2 from './pages/PlayerV2'
import GameBox from './pages/GameBox'
import DataQuality from './pages/DataQuality'
import TeamDetail from './pages/TeamDetail'
import PlayerSearch from './pages/PlayerSearch'
import Compare from './pages/Compare'
import { DataBasisBar } from './components/V2Bits'
import { seasonState, kstToday } from './lib/season'
import './App.css'
import { useRoute } from './lib/useRoute'
import { navigate, pageUrl, followLink } from './lib/navigation'

// 초기 테마 결정: 저장된 선택 > OS 선호(prefers-color-scheme) 순.
function getInitialTheme() {
  const saved = localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function App() {
  const { page: currentPage, query } = useRoute()
  const setCurrentPage = (page) => navigate(pageUrl(page))
  const openTeam = (team) => navigate(pageUrl('teams', { team }))
  // 시즌을 고르는 화면(순위표·홈)은 그 화면이 실제로 보여 주는 시즌의 팀 상세로(URL 에 시즌이 없을 때의 기본값 포함)
  const openTeamSeason = (team, season) => navigate(pageUrl('team', { team, season }))
  const [theme, setTheme] = useState(getInitialTheme)
  const [seasonInfo, setSeasonInfo] = useState(null)  // 시즌 상태 판정 결과(FR-12). 앱 전체가 공유.

  // 시즌 판정은 앱 진입 시 한 번. season 파라미터를 주지 않아 백엔드 활성 시즌(DR-06)을 그대로 받는다.
  useEffect(() => {
    axios
      .get('/api/schedule-games', { timeout: 15000 })
      .then((res) => setSeasonInfo(seasonState(kstToday(), res.data.data || [])))
      // 일정 조회가 실패해도 화면은 뜨지만, 그 사실을 숨기지 않는다. 빈 배열을 넘기면
      // seasonState 가 달력만 보고 판정해 isFallback=false 로 "2026 정규시즌" 을
      // 단언해 버린다(DR-06 AC2 위반). 어느 시즌인지 모른다는 걸 배너에 남긴다.
      .catch(() =>
        setSeasonInfo({
          ...seasonState(kstToday(), []),
          notice: '일정을 불러오지 못해 달력 기준으로 표시합니다 — 데이터가 비어 있을 수 있습니다',
        }),
      )
  }, [])

  // 테마 변경 시 <html data-theme>에 반영하고 선택을 저장(CSS 변수로 스타일 분기).
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  return (
    <div className="app">
      <header className="header">
        <h1>
          <span className="wm-kbo">KBO</span>
          <span className="wm-rest">Dashboard</span>
        </h1>
        <nav className="nav">
          <a
            className={currentPage === 'home' ? 'active' : ''}
            aria-current={currentPage === 'home' ? 'page' : undefined}
            href={pageUrl('home')}
            onClick={followLink}
          >
            홈
          </a>
          <a
            className={currentPage === 'standings' ? 'active' : ''}
            aria-current={currentPage === 'standings' ? 'page' : undefined}
            href={pageUrl('standings')}
            onClick={followLink}
          >
            순위표
          </a>
          <a
            className={currentPage === 'race' ? 'active' : ''}
            aria-current={currentPage === 'race' ? 'page' : undefined}
            href={pageUrl('race')}
            onClick={followLink}
          >
            가을야구
          </a>
          <a
            className={currentPage === 'teams' ? 'active' : ''}
            aria-current={currentPage === 'teams' ? 'page' : undefined}
            href={pageUrl('teams')}
            onClick={followLink}
          >
            팀 분석
          </a>
          <a
            className={currentPage === 'schedule' ? 'active' : ''}
            aria-current={currentPage === 'schedule' ? 'page' : undefined}
            href={pageUrl('schedule')}
            onClick={followLink}
          >
            경기일정
          </a>
          <a
            className={currentPage === 'players' ? 'active' : ''}
            aria-current={currentPage === 'players' ? 'page' : undefined}
            href={pageUrl('players')}
            onClick={followLink}
          >
            선수 기록
          </a>
          <a
            className={currentPage === 'zones' ? 'active' : ''}
            aria-current={currentPage === 'zones' ? 'page' : undefined}
            href={pageUrl('zones')}
            onClick={followLink}
          >
            투구 분석
          </a>
          <a
            className={currentPage === 'ops' ? 'active' : ''}
            aria-current={currentPage === 'ops' ? 'page' : undefined}
            href={pageUrl('ops')}
            onClick={followLink}
          >
            리그 운영
          </a>
          <a
            className={currentPage === 'ask' ? 'active' : ''}
            aria-current={currentPage === 'ask' ? 'page' : undefined}
            href={pageUrl('ask')}
            onClick={followLink}
          >
            질의응답
          </a>
          <a
            className={['search', 'compare'].includes(currentPage) ? 'active' : ''}
            aria-current={currentPage === 'search' ? 'page' : undefined}
            href={pageUrl('search')}
            onClick={followLink}
          >
            선수 찾기
          </a>
          <a
            className={['leaders', 'player', 'game'].includes(currentPage) ? 'active' : ''}
            aria-current={currentPage === 'leaders' ? 'page' : undefined}
            href={pageUrl('leaders')}
            onClick={followLink}
          >
            박스스코어 기록
          </a>
          <a
            className={currentPage === 'quality' ? 'active' : ''}
            aria-current={currentPage === 'quality' ? 'page' : undefined}
            href={pageUrl('quality')}
            onClick={followLink}
          >
            데이터 검증
          </a>
        </nav>
        <button
          className="theme-toggle"
          onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
          aria-label="테마 전환"
          title={theme === 'dark' ? '라이트 모드' : '다크 모드'}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </header>
      <main className="main">
        <DataBasisBar />
        {/* 페이지들이 시즌 상태를 초기값으로 쓰므로 판정 전에는 렌더하지 않는다. */}
        {!seasonInfo && <p className="loading">로딩중...</p>}
        {seasonInfo && currentPage === 'home' && <Home seasonInfo={seasonInfo} onOpsClick={() => setCurrentPage('ops')} onNavigate={setCurrentPage} onTeamClick={openTeamSeason} />}
        {seasonInfo && currentPage === 'standings' && (
          <Standings seasonInfo={seasonInfo} onTeamClick={openTeamSeason} />
        )}
        {seasonInfo && currentPage === 'race' && (
          <Race seasonInfo={seasonInfo} onTeamClick={openTeam} />
        )}
        {seasonInfo && currentPage === 'teams' && <Teams seasonInfo={seasonInfo} initialTeam={query.get('team')} />}
        {seasonInfo && currentPage === 'schedule' && <Schedule seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'players' && <Players seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'zones' && <Zones seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'ops' && <Ops seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'ask' && <Ask seasonInfo={seasonInfo} />}
        {/* /api/v2 화면: 시즌 판정(v1 일정)에 기대지 않는다 — v2 데이터가 적재된 시즌을 직접 고른다. */}
        {currentPage === 'leaders' && <Leaders />}
        {currentPage === 'player' && <PlayerV2 />}
        {currentPage === 'game' && <GameBox />}
        {currentPage === 'quality' && <DataQuality />}
        {currentPage === 'team' && <TeamDetail />}
        {currentPage === 'search' && <PlayerSearch />}
        {currentPage === 'compare' && <Compare />}
      </main>
    </div>
  )
}

export default App
