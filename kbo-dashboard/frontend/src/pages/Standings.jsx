// 순위표 페이지. 시즌을 골라 /api/standings 를 조회하고 StandingsTable 로 렌더.
import { useState, useEffect } from 'react'
import axios from 'axios'
import StandingsTable from '../components/StandingsTable'
import SeasonBanner from '../components/SeasonBanner'
import '../styles/Standings.css'
import { apiError } from '../lib/apiError'

function Standings({ seasonInfo, onTeamClick }) {
  const [standings, setStandings] = useState([])
  const [season, setSeason] = useState(seasonInfo.dataSeason)
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
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="standings-container">
      {/* FR-12: 포스트시즌에도 정규시즌 최종 순위를 그대로 보여준다(AC4) */}
      <SeasonBanner
        info={seasonInfo}
        selected={season}
        note={seasonInfo.state === 'postseason' ? 'PO 진행 중 · 대진 데이터는 수집 범위 밖' : ''}
      />
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
      {!loading && !error && standings.length === 0 && <p className="empty">{season}시즌 순위 데이터가 없습니다.</p>}
      {standings.length > 0 && <StandingsTable data={standings} onTeamClick={onTeamClick} />}
    </div>
  )
}

export default Standings
