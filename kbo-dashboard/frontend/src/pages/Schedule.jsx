import { useState, useEffect } from 'react'
import axios from 'axios'
import '../styles/Schedule.css'

function Schedule() {
  const [schedule, setSchedule] = useState([])
  const [season, setSeason] = useState(new Date().getFullYear())
  const [team, setTeam] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchSchedule()
  }, [season, team])

  const fetchSchedule = async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { season }
      if (team) params.team = team

      const response = await axios.get('/api/schedule', { params })
      if (response.data.status === 'success') {
        setSchedule(response.data.data)
      } else {
        setError('경기 일정을 가져오는데 실패했습니다.')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="schedule-container">
      <div className="schedule-filters">
        <h2>{season}시즌 경기일정</h2>
        <div className="filter-group">
          <select value={season} onChange={(e) => setSeason(parseInt(e.target.value))}>
            {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
          <input 
            type="text" 
            placeholder="팀명 검색"
            value={team}
            onChange={(e) => setTeam(e.target.value)}
          />
        </div>
      </div>

      {loading && <p className="loading">로딩중...</p>}
      {error && <p className="error">{error}</p>}
      {schedule.length > 0 && (
        <table className="schedule-table">
          <thead>
            <tr>
              <th>날짜</th>
              <th>경기</th>
              <th>결과</th>
            </tr>
          </thead>
          <tbody>
            {schedule.map((game, index) => (
              <tr key={index}>
                <td>{game.date}</td>
                <td>{game.home} vs {game.away}</td>
                <td>{game.result}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default Schedule
