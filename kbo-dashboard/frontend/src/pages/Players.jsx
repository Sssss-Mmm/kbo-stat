// 선수 기록 페이지.
// /api/player-stats 의 타자/투수 전체 스탯을 표로 보여준다. 구단 필터, 규정충족
// 필터, 컬럼 헤더 클릭 정렬을 지원한다. 표시 컬럼/형식은 아래 COLUMNS 로 정의.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import '../styles/Players.css'

// 역할별 컬럼 정의. key=API 응답 필드, label=헤더, fmt=표시 형식.
const COLUMNS = {
  hitter: [
    { key: '선수명', label: '선수', align: 'left' },
    { key: '팀명', label: '팀', align: 'left' },
    { key: '포지션', label: '포지션', align: 'left', fmt: 'text' },
    { key: 'G', label: 'G' },
    { key: 'AVG', label: 'AVG', fmt: 'rate' },
    { key: 'AB', label: 'AB' },
    { key: 'H', label: 'H' },
    { key: '2B', label: '2B' },
    { key: '3B', label: '3B' },
    { key: 'HR', label: 'HR' },
    { key: 'RBI', label: 'RBI' },
    { key: 'R', label: 'R' },
    { key: 'SB', label: 'SB' },
    { key: 'BB', label: 'BB' },
    { key: 'SO', label: 'SO' },
    { key: 'OBP', label: 'OBP', fmt: 'rate' },
    { key: 'SLG', label: 'SLG', fmt: 'rate' },
    { key: 'OPS', label: 'OPS', fmt: 'rate' },
    { key: 'wRC+', label: 'wRC+', fmt: 'one' },
    { key: 'WAR', label: 'WAR', fmt: 'two' },
  ],
  pitcher: [
    { key: '선수명', label: '선수', align: 'left' },
    { key: '팀명', label: '팀', align: 'left' },
    { key: 'G', label: 'G' },
    { key: 'W', label: 'W' },
    { key: 'L', label: 'L' },
    { key: 'SV', label: 'SV' },
    { key: 'HLD', label: 'HLD' },
    { key: 'IP', label: 'IP', fmt: 'text' },
    { key: 'ERA', label: 'ERA', fmt: 'two' },
    { key: 'WHIP', label: 'WHIP', fmt: 'two' },
    { key: 'SO', label: 'SO' },
    { key: 'BB', label: 'BB' },
    { key: 'H', label: 'H' },
    { key: 'HR', label: 'HR' },
    { key: 'ER', label: 'ER' },
    { key: 'QS', label: 'QS' },
    { key: 'K/9', label: 'K/9', fmt: 'two' },
    { key: 'BB/9', label: 'BB/9', fmt: 'two' },
    { key: 'K/BB', label: 'K/BB', fmt: 'two' },
    { key: 'WAR', label: 'WAR', fmt: 'two' },
  ],
}

// 기본 정렬: WAR 내림차순.
const DEFAULT_SORT = { key: 'WAR', dir: 'desc' }

// fmt 종류(rate/two/one/text)에 맞춰 셀 값을 문자열로 변환. 빈값은 '-'.
function fmtValue(value, fmt) {
  if (value === null || value === undefined || value === '') return '-'
  if (fmt === 'text') return value
  if (typeof value !== 'number') return value
  if (fmt === 'rate') return value.toFixed(3).replace(/^0/, '')
  if (fmt === 'two') return value.toFixed(2)
  if (fmt === 'one') return value.toFixed(1)
  return value
}

function Players() {
  const [role, setRole] = useState('hitter')
  const [season, setSeason] = useState(new Date().getFullYear())
  const [team, setTeam] = useState('all')
  const [qualifiedOnly, setQualifiedOnly] = useState(false)
  const [sort, setSort] = useState(DEFAULT_SORT)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const fetchRows = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await axios.get('/api/player-stats', { params: { role, season } })
        if (!active) return
        if (response.data.status === 'success') {
          setRows(response.data.data)
        } else {
          setError('선수 데이터를 가져오는데 실패했습니다.')
        }
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    fetchRows()
    return () => {
      active = false
    }
  }, [role, season])

  const switchRole = (next) => {
    setRole(next)
    setTeam('all')
    setSort(DEFAULT_SORT)
  }

  const teams = useMemo(
    () => [...new Set(rows.map((r) => r['팀명']).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko')),
    [rows]
  )

  const visibleRows = useMemo(() => {
    let list = rows
    if (team !== 'all') list = list.filter((r) => r['팀명'] === team)
    if (qualifiedOnly) list = list.filter((r) => r['규정충족'] === true)
    const { key, dir } = sort
    const factor = dir === 'asc' ? 1 : -1
    return [...list].sort((a, b) => {
      const av = a[key]
      const bv = b[key]
      const an = av === null || av === undefined || av === ''
      const bn = bv === null || bv === undefined || bv === ''
      if (an && bn) return 0
      if (an) return 1
      if (bn) return -1
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * factor
      return String(av).localeCompare(String(bv), 'ko') * factor
    })
  }, [rows, team, qualifiedOnly, sort])

  const toggleSort = (key) => {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }
    )
  }

  const columns = COLUMNS[role]

  return (
    <div className="players-container">
      <div className="players-header">
        <h2>선수 기록</h2>
        <select value={season} onChange={(e) => setSeason(parseInt(e.target.value))}>
          {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map((year) => (
            <option key={year} value={year}>{year}시즌</option>
          ))}
        </select>
        <div className="toggle-group">
          <button className={role === 'hitter' ? 'active' : ''} onClick={() => switchRole('hitter')}>타자</button>
          <button className={role === 'pitcher' ? 'active' : ''} onClick={() => switchRole('pitcher')}>투수</button>
        </div>
        <select value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="all">전체 구단</option>
          {teams.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <div className="toggle-group">
          <button className={!qualifiedOnly ? 'active' : ''} onClick={() => setQualifiedOnly(false)}>전체</button>
          <button className={qualifiedOnly ? 'active' : ''} onClick={() => setQualifiedOnly(true)}>규정충족</button>
        </div>
      </div>

      {loading && <p className="loading">로딩중...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        rows.length === 0 ? (
          <p className="players-empty">{season}시즌 {role === 'hitter' ? '타자' : '투수'} 데이터가 아직 없습니다.</p>
        ) : (
          <>
            <p className="players-note">
              {team === 'all' ? '전체 구단' : team} · {visibleRows.length}명
              {qualifiedOnly ? ' · 규정충족' : ''} · 헤더를 눌러 정렬
            </p>
            <div className="players-table-wrap">
              <table className="players-table">
                <thead>
                  <tr>
                    <th>#</th>
                    {columns.map((col) => (
                      <th
                        key={col.key}
                        className={`${sort.key === col.key ? 'sorted ' : ''}${col.align === 'left' ? 'lalign' : ''}`}
                        onClick={() => toggleSort(col.key)}
                      >
                        {col.label}{sort.key === col.key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row, index) => (
                    <tr key={`${row.PlayerId ?? row['선수명']}-${index}`}>
                      <td>{index + 1}</td>
                      {columns.map((col) => (
                        <td
                          key={col.key}
                          className={`${col.key === '선수명' ? 'player ' : ''}${col.align === 'left' ? 'lalign' : ''}`}
                        >
                          {fmtValue(row[col.key], col.fmt)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )
      )}
    </div>
  )
}

export default Players
