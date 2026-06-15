// 핫/콜드존 페이지.
// /api/zones 의 (선수, 3×3 존) 셀 데이터를 받아, 왼쪽 선수 목록에서 한 명을 고르면
// 오른쪽에 9분할 스트라이크존 히트맵(ZoneHeatmap)을 보여준다.
// 지표는 타율/피안타율(hit) 또는 스윙률(swing) 중 선택, 역할은 타자/투수.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import ZoneHeatmap from '../components/ZoneHeatmap'
import '../styles/Zones.css'

// .325 처럼 앞 0을 떼고 소수 3자리로 표시.
function fmtRate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, '') : '-'
}

// 역할/지표 조합에 맞는 한글 라벨.
function metricLabel(role, metric) {
  if (metric === 'swing') return '스윙률'
  return role === 'batter' ? '타율' : '피안타율'
}

function Zones() {
  const [role, setRole] = useState('batter') // batter | pitcher
  const [season, setSeason] = useState(new Date().getFullYear())
  const [metric, setMetric] = useState('hit') // hit | swing
  const [team, setTeam] = useState('all')
  const [selectedId, setSelectedId] = useState(null)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const fetchZones = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await axios.get('/api/zones', { params: { role, season } })
        if (!active) return
        if (response.data.status === 'success') {
          setRows(response.data.data)
          setSelectedId(null)
        } else {
          setError('존 데이터를 가져오는데 실패했습니다.')
        }
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    fetchZones()
    return () => {
      active = false
    }
  }, [role, season])

  // 선수별 합계 집계.
  const players = useMemo(() => {
    const byId = new Map()
    for (const row of rows) {
      if (!byId.has(row.PlayerId)) {
        byId.set(row.PlayerId, { id: row.PlayerId, name: row.Player, team: row.Team, pitches: 0, inPlay: 0, hits: 0, swings: 0 })
      }
      const agg = byId.get(row.PlayerId)
      agg.pitches += row.Pitches || 0
      agg.inPlay += row.InPlay || 0
      agg.hits += row.Hits || 0
      agg.swings += row.Swings || 0
    }
    return [...byId.values()]
  }, [rows])

  // 선수 전체 합계 기준 대표 지표(스윙률 또는 타율/피안타율).
  const overallMetric = (agg) => {
    if (metric === 'swing') return agg.pitches ? agg.swings / agg.pitches : null
    return agg.inPlay ? agg.hits / agg.inPlay : null
  }

  // 히트맵 색상의 중앙값으로 쓸 리그 평균(전체 셀 합산 기준).
  const leagueAvg = useMemo(() => {
    let num = 0
    let den = 0
    for (const row of rows) {
      if (metric === 'swing') {
        num += row.Swings || 0
        den += row.Pitches || 0
      } else {
        num += row.Hits || 0
        den += row.InPlay || 0
      }
    }
    return den ? num / den : 0
  }, [rows, metric])

  const teams = useMemo(
    () => [...new Set(rows.map((row) => row.Team).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko')),
    [rows]
  )

  const visiblePlayers = useMemo(() => {
    let list = team === 'all' ? players : players.filter((agg) => agg.team === team)
    return [...list].sort((a, b) => (overallMetric(b) ?? -1) - (overallMetric(a) ?? -1) || b.pitches - a.pitches)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [players, team, metric])

  // 선택이 비었으면 첫 선수 자동 선택.
  const effectiveSelectedId = selectedId ?? (visiblePlayers[0]?.id ?? null)
  const selectedCells = rows.filter((row) => row.PlayerId === effectiveSelectedId)
  const selectedAgg = selectedCells[0]

  return (
    <div className="zones-container">
      <div className="zones-header">
        <h2>핫/콜드존</h2>
        <select value={season} onChange={(e) => setSeason(parseInt(e.target.value))}>
          {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map((year) => (
            <option key={year} value={year}>{year}시즌</option>
          ))}
        </select>
        <div className="toggle-group">
          <button className={role === 'batter' ? 'active' : ''} onClick={() => { setRole('batter'); setTeam('all') }}>타자</button>
          <button className={role === 'pitcher' ? 'active' : ''} onClick={() => { setRole('pitcher'); setTeam('all') }}>투수</button>
        </div>
        <select value={team} onChange={(e) => { setTeam(e.target.value); setSelectedId(null) }}>
          <option value="all">전체 구단</option>
          {teams.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <div className="toggle-group">
          <button className={metric === 'hit' ? 'active' : ''} onClick={() => setMetric('hit')}>타율/피안타율</button>
          <button className={metric === 'swing' ? 'active' : ''} onClick={() => setMetric('swing')}>스윙률</button>
        </div>
      </div>

      {loading && <p className="loading">로딩중...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        rows.length === 0 ? (
          <p className="zones-empty">{season}시즌 존 데이터가 아직 없습니다.</p>
        ) : (
          <div className="zones-layout">
            <div className="zone-list">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>선수</th>
                    <th>팀</th>
                    <th>투구</th>
                    <th>{metricLabel(role, metric)}</th>
                  </tr>
                </thead>
                <tbody>
                  {visiblePlayers.map((agg, index) => (
                    <tr
                      key={agg.id}
                      className={agg.id === effectiveSelectedId ? 'selected' : ''}
                      onClick={() => setSelectedId(agg.id)}
                    >
                      <td>{index + 1}</td>
                      <td><strong>{agg.name || '-'}</strong></td>
                      <td>{agg.team || '-'}</td>
                      <td>{agg.pitches}</td>
                      <td>{fmtRate(overallMetric(agg))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="zone-card">
              {selectedAgg ? (
                <>
                  <h3>{selectedAgg.Player} · {selectedAgg.Team}{selectedAgg.Side ? ` · ${selectedAgg.Side}타` : ''}</h3>
                  <p className="sub">
                    {role === 'batter' ? '타자' : '투수'} · {metricLabel(role, metric)} · 투수 시점 기준 ·
                    {' '}표본 {metric === 'swing' ? '3구' : '2타구'} 미만은 회색
                  </p>
                  <ZoneHeatmap cells={selectedCells} metric={metric} leagueAvg={leagueAvg} />
                </>
              ) : (
                <p className="zones-empty">선수를 선택하세요.</p>
              )}
            </div>
          </div>
        )
      )}
    </div>
  )
}

export default Zones
