// 구종 아스널 패널 (투구 분석 페이지의 두 번째 탭).
// /api/pitch-arsenal 의 (선수, 구종, 볼카운트 버킷) 행을 받아, 왼쪽 목록에서 고른
// 선수의 구종 배합·구속·결과를 오른쪽 카드에 표시한다.
// 투수는 "뭘 던지나", 타자는 "뭘 못 치나" — 같은 데이터의 축만 반대다.
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { MiniTable, Note } from './MiniTable'
import { fmtRate, fmtOne, fmtPct, fmtInt } from '../lib/format'
import { teamColor } from '../lib/teamColors'

const MIN_PLAYER_PITCHES = 100 // 목록 기본 필터. 3구 던지고 구사율 100%인 선수를 숨긴다.
const MIN_CELL_PITCHES = 30 // 이 미만 구종 셀은 회색 처리(핫/콜드존과 같은 규칙)
const MIN_SWINGS = 10 // 헛스윙률 분모 하한
const MIN_INPLAY = 10 // 인플레이 타율 분모 하한

// 볼카운트 버킷. 빌더의 BUCKETS 와 같은 이름이고, 서로 배타가 아니라 합이 전체가 아니다.
const BUCKETS = [
  ['초구', '0-0'],
  ['유리', '2S'],
  ['불리', '3B'],
  ['결정구', '삼진 처리'],
]

// 표본이 모자란 값은 숫자를 적지 않는다 — 회색 '-' 가 잘못된 .000 보다 정직하다.
const cell = (value, enough, fmt) =>
  enough && Number.isFinite(value) ? fmt(value) : <span className="ars-thin">-</span>

function PitchArsenal({ role, season }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [team, setTeam] = useState('all')
  const [showThin, setShowThin] = useState(false) // 표본 부족 선수 포함
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    axios
      .get('/api/pitch-arsenal', { params: { role, season } })
      .then((res) => {
        if (!active) return
        setRows(res.data.data || [])
        setSelectedId(null)
      })
      // 부분 실패(NFR-06): 존 탭은 그대로 두고 이 패널만 안내한다.
      // 404 는 고장이 아니라 "그 시즌 데이터가 아직 없다"이므로 구분해서 알린다.
      .catch((err) => {
        if (!active) return
        if (err.response?.status === 404) setRows([])
        else setError(true)
      })
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [role, season])

  // 카드/목록의 기본 축은 '전체' 버킷. 나머지 버킷은 배합 표에서만 쓴다.
  const totals = useMemo(() => rows.filter((r) => r.CountBucket === '전체'), [rows])

  const players = useMemo(() => {
    const byId = new Map()
    for (const r of totals) {
      if (!byId.has(r.PlayerId)) {
        byId.set(r.PlayerId, { id: r.PlayerId, name: r.Player, team: r.Team, side: r.Side, pitches: 0, types: 0 })
      }
      const p = byId.get(r.PlayerId)
      p.pitches += r.Pitches || 0
      p.types += 1
    }
    return [...byId.values()].sort((a, b) => b.pitches - a.pitches)
  }, [totals])

  const teams = useMemo(
    () => [...new Set(totals.map((r) => r.Team).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko')),
    [totals]
  )

  const visible = useMemo(
    () =>
      players.filter(
        (p) => (team === 'all' || p.team === team) && (showThin || p.pitches >= MIN_PLAYER_PITCHES)
      ),
    [players, team, showThin]
  )

  const selectedId2 = visible.some((p) => p.id === selectedId) ? selectedId : visible[0]?.id ?? null
  const selected = visible.find((p) => p.id === selectedId2)
  const mine = useMemo(() => rows.filter((r) => r.PlayerId === selectedId2), [rows, selectedId2])
  const myTotals = mine.filter((r) => r.CountBucket === '전체').sort((a, b) => b.Pitches - a.Pitches)

  // 커버리지는 행마다 같은 값으로 실려 온다(빌더가 넣는다).
  const cov = rows[0]

  // 배합 표: 행 = 볼카운트 버킷, 열 = 그 선수가 가장 많이 쓴 구종 5개.
  const mixTypes = myTotals.slice(0, 5).map((r) => r.PitchType)
  const mixRows = BUCKETS.map(([bucket, hint]) => {
    const inBucket = mine.filter((r) => r.CountBucket === bucket)
    const row = { bucket, hint, n: inBucket[0]?.BucketPitches ?? 0 }
    for (const t of mixTypes) row[t] = inBucket.find((r) => r.PitchType === t)?.UsageRate ?? null
    return row
  }).filter((r) => r.n > 0)

  // 인플레이 타율은 타구가 된 공만의 안타율이라 시즌 타율·피안타율과 다르다.
  const hitLabel = role === 'pitcher' ? '피안타' : '타율'

  const columns = [
    {
      key: 'PitchType',
      label: '구종',
      left: true,
      render: (r) => (
        <span className="ars-type">
          <b>{r.PitchType}</b>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(r.UsageRate || 0) * 100}%`, background: teamColor(selected?.team) }} />
          </span>
        </span>
      ),
    },
    { key: 'UsageRate', label: '비율', render: (r) => fmtPct(r.UsageRate) },
    { key: 'Pitches', label: '투구', render: (r) => fmtInt(r.Pitches) },
    { key: 'AvgKmh', label: '평균', render: (r) => fmtOne(r.AvgKmh) },
    { key: 'MaxKmh', label: '최고', render: (r) => fmtOne(r.MaxKmh) },
    { key: 'WhiffRate', label: '헛스윙', render: (r) => cell(r.WhiffRate, r.Swings >= MIN_SWINGS, fmtPct) },
    { key: 'StrikeRate', label: '스트라이크', render: (r) => cell(r.StrikeRate, r.Pitches >= MIN_CELL_PITCHES, fmtPct) },
    { key: 'BipAvg', label: `인플레이 ${hitLabel}`, render: (r) => cell(r.BipAvg, r.InPlay >= MIN_INPLAY, fmtRate) },
  ]

  const mixColumns = [
    { key: 'bucket', label: '카운트', left: true, render: (r) => <><b>{r.bucket}</b> <span className="ars-thin">{r.hint}</span></> },
    ...mixTypes.map((t) => ({ key: t, label: t, render: (r) => cell(r[t], r.n >= MIN_CELL_PITCHES, fmtPct) })),
    { key: 'n', label: '표본', render: (r) => fmtInt(r.n) },
  ]

  if (loading) return <p className="loading">로딩중...</p>
  if (error) return <Note rows={null} />
  if (!rows.length) return <Note rows={[]} empty={`${season}시즌 구종 데이터가 아직 없습니다.`} />

  return (
    <>
      <div className="ars-toolbar">
        <select value={team} onChange={(e) => { setTeam(e.target.value); setSelectedId(null) }}>
          <option value="all">전체 구단</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label className="ars-check">
          <input type="checkbox" checked={showThin} onChange={(e) => setShowThin(e.target.checked)} />
          표본 부족 선수 포함({MIN_PLAYER_PITCHES}구 미만)
        </label>
        <span className="ars-count">{visible.length}명</span>
      </div>

      <div className="zones-layout">
        <div className="zone-list">
          <table>
            <thead>
              <tr><th>#</th><th>선수</th><th>팀</th><th>투구</th><th>구종</th></tr>
            </thead>
            <tbody>
              {visible.map((p, i) => (
                <tr key={p.id} className={p.id === selectedId2 ? 'selected' : ''} onClick={() => setSelectedId(p.id)}>
                  <td>{i + 1}</td>
                  <td><strong>{p.name || '-'}</strong></td>
                  <td>{p.team || '-'}</td>
                  <td className={p.pitches < MIN_PLAYER_PITCHES ? 'ars-thin' : ''}>{fmtInt(p.pitches)}</td>
                  <td>{p.types}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="zone-card">
          {!selected ? (
            <p className="zones-empty">선수를 선택하세요.</p>
          ) : (
            <>
              <h3>
                {selected.name} · {selected.team}
                {selected.side ? ` · ${selected.side}타` : ''}
              </h3>
              <p className="sub">
                {role === 'pitcher' ? '구사율·구속·결과' : '상대한 구종별 성적'} · 총 {fmtInt(selected.pitches)}구 ·
                {' '}인플레이 {hitLabel} = 타구가 된 공만의 안타율(삼진·볼넷 제외) ·
                {' '}구종 {MIN_CELL_PITCHES}구(스윙·인플레이 {MIN_SWINGS}) 미만은 표본 부족으로 수치를 생략
              </p>
              <div className="ars-scroll">
                <MiniTable columns={columns} rows={myTotals} />
              </div>

              <h4 className="ars-sub">볼카운트별 배합</h4>
              {mixRows.length ? (
                <div className="ars-scroll">
                  <MiniTable columns={mixColumns} rows={mixRows} />
                </div>
              ) : (
                <p className="empty">볼카운트 표본이 없습니다.</p>
              )}
              <p className="ars-foot">
                버킷은 서로 배타가 아니다(결정구는 유리 카운트와 겹친다) — 세로 합이 전체가 되지 않는다.
              </p>

              {/* 부분 수집 데이터라 '시즌 누적'으로 오독되지 않게 표본 기간을 고정 노출한다. */}
              {cov && (
                <p className="ars-coverage">
                  ⚠ 수집 {cov.Days}경기일 표본 ({cov.FirstDate} ~ {cov.LastDate}) · 전 경기가 아니다
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}

export default PitchArsenal
