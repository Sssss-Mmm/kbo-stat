import { useState, useEffect } from 'react'
import Home from './pages/Home'
import Standings from './pages/Standings'
import Schedule from './pages/Schedule'
import Players from './pages/Players'
import Zones from './pages/Zones'
import './App.css'

function getInitialTheme() {
  const saved = localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function App() {
  const [currentPage, setCurrentPage] = useState('home')
  const [theme, setTheme] = useState(getInitialTheme)

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
