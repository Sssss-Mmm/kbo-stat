// 앱 루트. 라우터 없이 currentPage 상태로 9개 페이지를 전환하는 단일 SPA 셸.
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
import { seasonState, kstToday } from './lib/season'
import './App.css'

// 초기 테마 결정: 저장된 선택 > OS 선호(prefers-color-scheme) 순.
function getInitialTheme() {
  const saved = localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function App() {
  const [currentPage, setCurrentPage] = useState('home')  // 현재 보이는 페이지
  const [theme, setTheme] = useState(getInitialTheme)
  const [focusTeam, setFocusTeam] = useState(null)  // 순위표에서 클릭한 팀(팀 분석 초기 선택)
  const [seasonInfo, setSeasonInfo] = useState(null)  // 시즌 상태 판정 결과(FR-12). 앱 전체가 공유.

  // 시즌 판정은 앱 진입 시 한 번. season 파라미터를 주지 않아 백엔드 활성 시즌(DR-06)을 그대로 받는다.
  useEffect(() => {
    axios
      .get('/api/schedule-games')
      .then((res) => setSeasonInfo(seasonState(kstToday(), res.data.data || [])))
      .catch(() => setSeasonInfo(seasonState(kstToday(), [])))  // 일정 조회 실패해도 화면은 뜬다
  }, [])

  // 테마 변경 시 <html data-theme>에 반영하고 선택을 저장(CSS 변수로 스타일 분기).
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  return (
    <div className="app">
      <header className="header">
        <h1>KBO Dashboard</h1>
        <nav className="nav">
          <button
            className={currentPage === 'home' ? 'active' : ''}
            onClick={() => setCurrentPage('home')}
          >
            HOME
          </button>
          <button
            className={currentPage === 'standings' ? 'active' : ''}
            onClick={() => setCurrentPage('standings')}
          >
            순위표
          </button>
          <button
            className={currentPage === 'race' ? 'active' : ''}
            onClick={() => setCurrentPage('race')}
          >
            가을야구
          </button>
          <button
            className={currentPage === 'teams' ? 'active' : ''}
            onClick={() => setCurrentPage('teams')}
          >
            팀 분석
          </button>
          <button
            className={currentPage === 'schedule' ? 'active' : ''}
            onClick={() => setCurrentPage('schedule')}
          >
            경기일정
          </button>
          <button
            className={currentPage === 'players' ? 'active' : ''}
            onClick={() => setCurrentPage('players')}
          >
            선수 기록
          </button>
          <button
            className={currentPage === 'zones' ? 'active' : ''}
            onClick={() => setCurrentPage('zones')}
          >
            핫/콜드존
          </button>
          <button
            className={currentPage === 'ops' ? 'active' : ''}
            onClick={() => setCurrentPage('ops')}
          >
            리그 운영
          </button>
          <button
            className={currentPage === 'ask' ? 'active' : ''}
            onClick={() => setCurrentPage('ask')}
          >
            질의응답
          </button>
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
      {/* FR-12 AC2 / DR-06 AC2: 지금 어느 시즌의 데이터를 보고 있는지 전 화면 공통으로 명시한다.
          페이지마다 배너를 두는 대신 셸에서 한 번만 그린다. */}
      {seasonInfo && (
        <div className={`season-banner${seasonInfo.state === 'regular' ? '' : ' off'}`}>
          <strong>{seasonInfo.label}</strong>
          {seasonInfo.notice && <span>{seasonInfo.notice}</span>}
        </div>
      )}
      <main className="main">
        {/* 페이지들이 시즌 상태를 초기값으로 쓰므로 판정 전에는 렌더하지 않는다. */}
        {!seasonInfo && <p className="loading">로딩중...</p>}
        {seasonInfo && currentPage === 'home' && <Home seasonInfo={seasonInfo} onOpsClick={() => setCurrentPage('ops')} />}
        {seasonInfo && currentPage === 'standings' && (
          <Standings seasonInfo={seasonInfo} onTeamClick={(t) => { setFocusTeam(t); setCurrentPage('teams') }} />
        )}
        {seasonInfo && currentPage === 'race' && (
          <Race seasonInfo={seasonInfo} onTeamClick={(t) => { setFocusTeam(t); setCurrentPage('teams') }} />
        )}
        {seasonInfo && currentPage === 'teams' && <Teams seasonInfo={seasonInfo} initialTeam={focusTeam} />}
        {seasonInfo && currentPage === 'schedule' && <Schedule seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'players' && <Players seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'zones' && <Zones seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'ops' && <Ops seasonInfo={seasonInfo} />}
        {seasonInfo && currentPage === 'ask' && <Ask seasonInfo={seasonInfo} />}
      </main>
    </div>
  )
}

export default App
