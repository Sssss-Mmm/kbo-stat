import { useState, useEffect } from 'react'
import axios from 'axios'
import StandingsTable from '../components/StandingsTable'
import '../styles/Standings.css'

function Standings() {
  const [standings, setStandings] = useState([])
  const [season, setSeason] = useState(new Date().getFullYear())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchStandings()
  }, [season])

  const fetchStandings = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await axios.get('/api/standings', {
        params: { season }
      })
      if (response.data.status === 'success') {
        setStandings(response.data.data)
      } else {
        setError('순위표 데이터를 가져오는데 실패했습니다.')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="standings-container">
      <div className="standings-header">
        <h2>{season}시즌 순위표</h2>
        <select value={season} onChange={(e) => setSeason(parseInt(e.target.value))}>
          {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map(year => (
            <option key={year} value={year}>{year}</option>
          ))}
        </select>
      </div>

      {loading && <p className="loading">로딩중...</p>}
      {error && <p className="error">{error}</p>}
      {standings.length > 0 && <StandingsTable data={standings} />}
    </div>
  )
}

export default Standings
