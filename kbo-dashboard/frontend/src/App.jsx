import { useState } from 'react'
import Standings from './pages/Standings'
import Schedule from './pages/Schedule'
import Players from './pages/Players'
import Zones from './pages/Zones'
import './App.css'

function App() {
  const [currentPage, setCurrentPage] = useState('standings')

  return (
    <div className="app">
      <header className="header">
        <h1>KBO Dashboard</h1>
        <nav className="nav">
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
      </header>
      <main className="main">
        {currentPage === 'standings' && <Standings />}
        {currentPage === 'schedule' && <Schedule />}
        {currentPage === 'players' && <Players />}
        {currentPage === 'zones' && <Zones />}
      </main>
    </div>
  )
}

export default App
