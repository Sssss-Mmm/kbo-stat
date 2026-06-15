// 앱 루트. 라우터 없이 currentPage 상태로 5개 페이지를 전환하는 단일 SPA 셸.
// 상단 헤더(네비게이션 + 다크/라이트 테마 토글)와 본문 페이지로 구성된다.
import { useState, useEffect } from 'react'
import Home from './pages/Home'
import Standings from './pages/Standings'
import Schedule from './pages/Schedule'
import Players from './pages/Players'
import Zones from './pages/Zones'
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
        {currentPage === 'home' && <Home />}
        {currentPage === 'standings' && <Standings />}
        {currentPage === 'schedule' && <Schedule />}
        {currentPage === 'players' && <Players />}
        {currentPage === 'zones' && <Zones />}
      </main>
    </div>
  )
}

export default App
