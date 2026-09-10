// 선수 기록 페이지.
// /api/player-stats 의 타자/투수 전체 스탯을 표로 보여준다. 구단 필터, 규정충족
// 필터, 컬럼 헤더 클릭 정렬을 지원한다. 표시 컬럼/형식은 아래 COLUMNS 로 정의.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import SeasonBanner from '../components/SeasonBanner'
import { sortRows, nextSort } from '../lib/list'
import '../styles/Players.css'
import { apiError } from '../lib/apiError'
import { useRoute } from '../lib/useRoute'
import { updateQuery } from '../lib/navigation'
import { filterPlayers, playerKey, toggleComparison, BASIC_COLUMNS, STAT_LABELS } from '../lib/players'

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

function Players({ seasonInfo }) {
  const { query } = useRoute()
  const role = query.get('role') === 'pitcher' ? 'pitcher' : 'hitter'
  // 선수 기록은 백엔드가 판정한 활성 시즌 하나뿐이라 고를 게 없다.
  const season = seasonInfo.dataSeason
  const team = query.get('team') || 'all'
  const search = query.get('q') || ''
  const qualifiedOnly = query.get('qualified') === '1'
  const detailed = query.get('detail') === '1'
  const sortKey = query.get('sort')
  const sortDir = query.get('dir')
  const sort = useMemo(() => ({
    key: COLUMNS[role].some((col) => col.key === sortKey) ? sortKey : DEFAULT_SORT.key,
    dir: sortDir === 'asc' ? 'asc' : 'desc',
  }), [role, sortKey, sortDir])
  const selected = [...new Set((query.get('compare') || '').split(',').filter(Boolean))].slice(0, 2)
  const setTeam = (value) => updateQuery({ team: value === 'all' ? null : value })
  const setQualifiedOnly = (value) => updateQuery({ qualified: value ? '1' : null })
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const fetchRows = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await axios.get('/api/player-stats', { params: { role, season }, timeout: 15000 })
        if (!active) return
        if (response.data.status === 'success') {
          setRows(response.data.data)
        } else {
          setError('선수 데이터를 가져오는데 실패했습니다.')
        }
      } catch (err) {
        if (active) setError(apiError(err))
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
    updateQuery({ role: next, team: null, sort: null, dir: null, compare: null })
  }

  const teams = useMemo(
    () => [...new Set(rows.map((r) => r['팀명']).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko')),
    [rows]
  )

  // 구단/규정충족 필터 적용 후 정렬(정렬 규칙은 lib/list.js — 투구 분석 목록과 공유한다).
  const visibleRows = useMemo(() => {
    return sortRows(filterPlayers(rows, { team, query: search, qualified: qualifiedOnly }), sort)
  }, [rows, team, search, qualifiedOnly, sort])

  const toggleSort = (key) => {
    const next = nextSort(sort, key)
    updateQuery({ sort: next.key, dir: next.dir })
  }
  const togglePlayer = (row) => updateQuery({ compare: toggleComparison(selected, playerKey(row)).join(',') })
  const compared = selected.map((id) => rows.find((row) => playerKey(row) === id)).filter(Boolean)
  const columns = COLUMNS[role].filter((col) => detailed || BASIC_COLUMNS[role].includes(col.key))

  return (
    <div className="players-container">
      <SeasonBanner info={seasonInfo} selected={season} />
      <div className="players-header">
        <h2>선수 기록</h2>
        <span className="season-static">{season}시즌</span>
        <div className="toggle-group">
          <button className={role === 'hitter' ? 'active' : ''} onClick={() => switchRole('hitter')}>타자</button>
          <button className={role === 'pitcher' ? 'active' : ''} onClick={() => switchRole('pitcher')}>투수</button>
        </div>
        <select aria-label="구단 필터" value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="all">전체 구단</option>
          {teams.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <div className="toggle-group">
          <button className={!qualifiedOnly ? 'active' : ''} onClick={() => setQualifiedOnly(false)}>전체</button>
          <button className={qualifiedOnly ? 'active' : ''} onClick={() => setQualifiedOnly(true)}>규정충족</button>
        </div>
        <input type="search" aria-label="선수명 검색" placeholder="선수 이름 검색" value={search}
          onChange={(e) => updateQuery({ q: e.target.value }, true)} />
        <button className="record-mode" aria-pressed={detailed} onClick={() => updateQuery({ detail: detailed ? null : '1' })}>
          {detailed ? '기본 지표 보기' : '상세 지표 보기'}
        </button>
      </div>

      <details className="players-glossary">
        <summary>지표 설명</summary>
        <dl>{columns.filter((col) => !['선수명', '팀명', '포지션'].includes(col.key)).map((col) => (
          <div key={col.key}><dt>{col.label}</dt><dd>{STAT_LABELS[col.key]}</dd></div>
        ))}</dl>
      </details>

      {loading && <p className="loading">로딩중...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        rows.length === 0 ? (
          <p className="players-empty">{season}시즌 {role === 'hitter' ? '타자' : '투수'} 데이터가 아직 없습니다.</p>
        ) : (
          <>
            <section className="players-comparison" aria-label="선수 비교">
              <div className="players-comparison-head">
                <h3>선수 비교 <span>{compared.length}/2</span></h3>
                {selected.length > 0 && <button onClick={() => updateQuery({ compare: null })}>선택 초기화</button>}
              </div>
              {compared.length === 0 ? <p className="players-note">목록에서 같은 역할의 선수 2명을 선택해 기록을 비교하세요.</p> : (
                <>
                  {compared.length === 1 && <p className="players-note">비교할 선수를 한 명 더 선택하세요. 구단이나 검색어를 바꿔도 선택은 유지됩니다.</p>}
                  <div className="players-table-wrap">
                    <table className="players-table">
                      <caption className="players-note">{season}시즌 {role === 'hitter' ? '타자' : '투수'} 기록 비교 · 같은 시즌 누적 기록</caption>
                      <thead><tr><th scope="col">지표</th>{compared.map((row) => (
                        <th scope="col" key={playerKey(row)}>{row['선수명']} ({row['팀명']}) <button aria-label={`${row['선수명']} 비교에서 제외`} onClick={() => togglePlayer(row)}>×</button></th>
                      ))}</tr></thead>
                      <tbody>{columns.filter((col) => !['선수명', '팀명', '포지션'].includes(col.key)).map((col) => (
                        <tr key={col.key}><th scope="row" title={STAT_LABELS[col.key]}>{col.label}</th>
                          {compared.map((row) => <td key={playerKey(row)}>{fmtValue(row[col.key], col.fmt)}</td>)}
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                </>
              )}
            </section>
            <p className="players-note">
              {team === 'all' ? '전체 구단' : team} · {visibleRows.length}명
              {qualifiedOnly ? ' · 규정충족' : ''} · 헤더를 눌러 정렬
            </p>
            {visibleRows.length === 0 && <p className="players-empty">조건에 맞는 선수가 없습니다. <button onClick={() => updateQuery({ team: null, q: null, qualified: null })}>필터 초기화</button></p>}
            <div className="players-table-wrap">
              <table className="players-table">
                <thead>
                  <tr>
                    <th scope="col">비교</th>
                    <th scope="col">#</th>
                    {columns.map((col) => (
                      <th
                        key={col.key}
                        className={`${sort.key === col.key ? 'sorted ' : ''}${col.align === 'left' ? 'lalign' : ''}`}
                        scope="col"
                        aria-sort={sort.key === col.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >
                        <button title={STAT_LABELS[col.key]} onClick={() => toggleSort(col.key)}>
                          {col.label}{sort.key === col.key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row, index) => (
                    <tr key={`${row.PlayerId ?? row['선수명']}-${index}`}>
                      <td><input type="checkbox" aria-label={`${row['선수명']} (${row['팀명']}) 비교 선택`}
                        checked={selected.includes(playerKey(row))}
                        disabled={selected.length === 2 && !selected.includes(playerKey(row))}
                        onChange={() => togglePlayer(row)} /></td>
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
