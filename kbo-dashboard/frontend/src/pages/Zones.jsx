// 투구 분석 페이지. 같은 투구 원본에서 나온 세 화면을 탭으로 묶는다.
//   존 히트맵   — 코스별 강약 (/api/zones)
//   구종 아스널 — 구종별 배합·구속·결과 (/api/pitch-arsenal, PitchArsenal.jsx)
//   볼카운트    — 카운트가 타석을 어떻게 바꾸나 (/api/count-baseball, PitchCount.jsx)
// 셋 다 "이 타자를 어떻게 잡나"라는 같은 질문에 답하고 선수 선택 UI 도 같아서,
// 네비 항목을 늘리는 대신 한 페이지 안에 둔다.
// 볼카운트 탭은 타자 기준 데이터만 있어서 타자/투수 토글을 감춘다
// (투수 쪽 카운트별 배합은 구종 아스널 탭이 이미 낸다).
//
// (존 히트맵) /api/zones 의 (선수, 존) 셀 데이터를 받아, 왼쪽 선수 목록에서 한 명을 고르면
// 오른쪽에 존 히트맵(ZoneHeatmap)을 보여준다. 격자 크기는 하드코딩하지 않고
// 응답의 Zone 라벨 최대 번호에서 읽는다(빌더의 GRID_N 만 바꾸면 화면이 따라온다).
// 지표는 타율/피안타율(hit) 또는 스윙률(swing) 중 선택, 역할은 타자/투수.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import ZoneHeatmap from '../components/ZoneHeatmap'
import PitchArsenal from '../components/PitchArsenal'
import PitchCount from '../components/PitchCount'
import SeasonBanner from '../components/SeasonBanner'
import '../styles/Home.css'  // MiniTable / bar-track 공용 스타일
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

function Zones({ seasonInfo }) {
  const [view, setView] = useState('zone') // zone | arsenal | count
  const [role, setRole] = useState('batter') // batter | pitcher
  const [season, setSeason] = useState(seasonInfo.dataSeason)
  const [metric, setMetric] = useState('hit') // hit | swing
  const [team, setTeam] = useState('all')
  const [selectedId, setSelectedId] = useState(null)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (view !== 'zone') return
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
  }, [role, season, view])

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

  // 격자 한 변의 칸 수 = 리그 전체 셀에서 본 최대 row/col 번호.
  const gridN = useMemo(
    () => rows.reduce((max, row) => Math.max(max, ...String(row.Zone).split('-').map(Number)), 3),
    [rows]
  )

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
      <SeasonBanner info={seasonInfo} selected={season} />
      <div className="zones-header">
        <h2>투구 분석</h2>
        <div className="toggle-group">
          <button className={view === 'zone' ? 'active' : ''} onClick={() => setView('zone')}>존 히트맵</button>
          <button className={view === 'arsenal' ? 'active' : ''} onClick={() => setView('arsenal')}>구종 아스널</button>
          <button className={view === 'count' ? 'active' : ''} onClick={() => setView('count')}>볼카운트</button>
        </div>
        <select value={season} onChange={(e) => setSeason(parseInt(e.target.value))}>
          {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map((year) => (
            <option key={year} value={year}>{year}시즌</option>
          ))}
        </select>
        {view !== 'count' && (
          <div className="toggle-group">
            <button className={role === 'batter' ? 'active' : ''} onClick={() => { setRole('batter'); setTeam('all') }}>타자</button>
            <button className={role === 'pitcher' ? 'active' : ''} onClick={() => { setRole('pitcher'); setTeam('all') }}>투수</button>
          </div>
        )}
        {view === 'zone' && (
          <>
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
          </>
        )}
      </div>

      {view === 'arsenal' && <PitchArsenal role={role} season={season} />}
      {view === 'count' && <PitchCount season={season} />}

      {view === 'zone' && loading && <p className="loading">로딩중...</p>}
      {view === 'zone' && error && <p className="error">{error}</p>}

      {view === 'zone' && !loading && !error && (
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
                    {' '}{gridN}×{gridN}(테두리는 존 밖) ·
                    {' '}표본 {metric === 'swing' ? '3구' : '2타구'} 미만은 회색
                  </p>
                  <ZoneHeatmap cells={selectedCells} metric={metric} leagueAvg={leagueAvg} gridN={gridN} />
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
