import { useState, useEffect } from 'react'
import Standings from './pages/Standings'
import Schedule from './pages/Schedule'
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
        </nav>
      </header>
      <main className="main">
        {currentPage === 'standings' && <Standings />}
        {currentPage === 'schedule' && <Schedule />}
      </main>
    </div>
  )
}

export default App
