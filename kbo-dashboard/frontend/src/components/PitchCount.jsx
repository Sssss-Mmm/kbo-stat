// 볼카운트 야구 패널 (투구 분석 페이지의 세 번째 탭).
// /api/count-baseball 의 (Scope, 선수, 버킷) 행을 받아 세 가지를 보여준다.
//   1) 리그 12칸 카운트 매트릭스 — 카운트가 타석 결과를 얼마나 바꾸는가
//   2) 초구 스윙률 분포 — 초구부터 치는 타자 / 기다리는 타자
//   3) 선택한 타자의 버킷별 성향과 리그와의 차이
// 타자 기준 데이터만 있다(투수 쪽 카운트 배합은 '구종 아스널' 탭이 이미 낸다).
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { MiniTable, Note, SortHeader } from './MiniTable'
import Beeswarm from './charts/Beeswarm'
import { fmtRate, fmtPct, fmtInt } from '../lib/format'
import { teamColor } from '../lib/teamColors'
import { sortRows, nextSort, listFilter } from '../lib/list'
import {
  indexRows, matrixRows, bucketTable, paEnough, pitchEnough,
  MIN_PA, MIN_BUCKET_PA, MIN_BUCKET_PITCHES, STRIKES,
} from '../lib/count'

// 매트릭스에서 고를 수 있는 지표. grain 이 분모의 낟알이다 — 표본 하한이 달라진다.
//   pa    = 이 카운트를 거친 타석의 결과 (도달 시점 이후를 포함한 타석 단위)
//   pitch = 이 카운트에서 던져진 공 (투구 단위)
// 인플레이 타율(BipAvg)은 CSV 에 있지만 카운트별 차이가 .31~.38 로 좁아
// (삼진·볼넷이 분모에서 빠지기 때문) 매트릭스 토글에서는 뺐다.
const METRICS = {
  onbase: { label: '출루율', key: 'OnBaseRate', grain: 'pa', pct: false },
  k: { label: '삼진률', key: 'KRate', grain: 'pa', pct: true },
  swing: { label: '스윙률', key: 'SwingRate', grain: 'pitch', pct: true },
}

const enough = (row, grain) => (grain === 'pa' ? paEnough(row) : pitchEnough(row))
const fmtOf = (m) => (m.pct ? fmtPct : fmtRate)

// 표본이 모자란 값은 숫자를 적지 않는다 — 회색 '-' 가 잘못된 .000 보다 정직하다.
const thin = <span className="ars-thin">-</span>

// 리그 대비 차이. 부호를 붙여 "얼마나 다른가"만 읽히게 한다.
function delta(value, leagueValue, pct) {
  if (!Number.isFinite(value) || !Number.isFinite(leagueValue)) return null
  const d = value - leagueValue
  const mag = pct ? `${Math.abs(d * 100).toFixed(1)}%p` : Math.abs(d).toFixed(3).replace(/^0/, '')
  return `${d >= 0 ? '+' : '−'}${mag}`
}

// 값 + 리그 대비 차이 한 칸.
function Cell({ row, lg, metricKey, pct, ok }) {
  if (!ok) return thin
  const v = row[metricKey]
  if (!Number.isFinite(v)) return thin
  const d = lg ? delta(v, lg[metricKey], pct) : null
  return (
    <>
      {(pct ? fmtPct : fmtRate)(v)}
      {d && <span className="cnt-delta"> {d}</span>}
    </>
  )
}

const LIST_COLS = [
  { key: 'name', label: '타자' },
  { key: 'team', label: '팀' },
  { key: 'pa', label: '타석' },
  { key: 'firstSwing', label: '초구스윙' },
]

function PitchCount({ season }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [metric, setMetric] = useState('onbase')
  const [team, setTeam] = useState('all')
  const [showThin, setShowThin] = useState(false) // 필터 해제(표본 부족 / 규정 미달 포함)
  const [sort, setSort] = useState({ key: 'pa', dir: 'desc' })
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(false)
    axios
      .get('/api/count-baseball', { params: { season } })
      .then((res) => {
        if (!active) return
        setRows(res.data.data || [])
        setSelectedId(null)
      })
      // 부분 실패(NFR-06): 다른 탭은 그대로 두고 이 패널만 안내한다.
      // 404 는 고장이 아니라 "그 시즌 데이터가 아직 없다"이므로 구분한다.
      .catch((err) => {
        if (!active) return
        if (err.response?.status === 404) setRows([])
        else setError(true)
      })
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [season])

  const { league, players, coverage } = useMemo(() => indexRows(rows), [rows])

  const teams = useMemo(
    () => [...new Set(players.map((p) => p.team).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko')),
    [players]
  )

  // 규정충족 플래그가 있는 시즌이면 기준이 그걸로 승격되고, 없으면 MIN_PA 로 남는다.
  const filter = useMemo(
    () => listFilter(players, { min: MIN_PA, unit: '타석', noun: '타자', sample: (p) => p.pa }),
    [players]
  )

  const visible = useMemo(
    () =>
      sortRows(
        players
          .filter((p) => (team === 'all' || p.team === team) && (showThin || filter.keep(p)))
          // 목록에 보이는 값만 정렬할 수 있게 초구 스윙률을 펼쳐 둔다.
          .map((p) => ({ ...p, firstSwing: p.buckets['초구']?.SwingRate ?? null })),
        sort
      ),
    [players, team, showThin, filter, sort]
  )

  const selected = visible.find((p) => p.id === selectedId) || visible[0] || null
  const table = useMemo(() => bucketTable(selected, league), [selected, league])

  // 초구 스윙률 분포는 표본 하한을 넘긴 타자만 — 5타석짜리 100%가 축을 망친다.
  const swarm = useMemo(
    () =>
      players
        .filter((p) => p.pa >= MIN_PA && p.buckets['초구'])
        .map((p) => ({
          value: p.buckets['초구'].SwingRate,
          label: `${p.name} ${p.team || ''}`,
          color: p.id === selected?.id ? 'var(--text)' : teamColor(p.team),
        })),
    [players, selected]
  )

  const m = METRICS[metric]
  const matrix = useMemo(() => matrixRows(league), [league])

  const matrixColumns = [
    { key: 'balls', label: '볼', left: true, render: (r) => <b>{r.balls}B</b> },
    ...STRIKES.map((s, i) => ({
      key: `s${s}`,
      label: `${s}S`,
      render: (r) => {
        const cell = r.cells[i]
        if (!enough(cell, m.grain)) return thin
        return (
          <>
            {fmtOf(m)(cell[m.key])}
            <span className="cnt-n"> {fmtInt(m.grain === 'pa' ? cell.PA : cell.Pitches)}</span>
          </>
        )
      },
    })),
  ]

  const bucketColumns = [
    {
      key: 'bucket',
      label: '카운트',
      left: true,
      render: (r) => <><b>{r.bucket}</b> <span className="ars-thin">{r.hint}</span></>,
    },
    // 전체·초구는 모든 타석이 거치므로 도달률이 항상 100% — 적을 값이 없다.
    { key: 'PaShare', label: '도달률', render: (r) => (r.row.PaShare >= 1 ? thin : fmtPct(r.row.PaShare)) },
    { key: 'PA', label: '타석', render: (r) => fmtInt(r.row.PA) },
    { key: 'SwingRate', label: '스윙률', render: (r) => <Cell row={r.row} lg={r.lg} metricKey="SwingRate" pct ok={pitchEnough(r.row)} /> },
    { key: 'FoulRate', label: '커트율', render: (r) => <Cell row={r.row} lg={r.lg} metricKey="FoulRate" pct ok={pitchEnough(r.row)} /> },
    { key: 'KRate', label: '삼진률', render: (r) => <Cell row={r.row} lg={r.lg} metricKey="KRate" pct ok={paEnough(r.row)} /> },
    { key: 'OnBaseRate', label: '출루율', render: (r) => <Cell row={r.row} lg={r.lg} metricKey="OnBaseRate" ok={paEnough(r.row)} /> },
  ]

  if (loading) return <p className="loading">로딩중...</p>
  if (error) return <Note rows={null} />
  if (!rows.length) return <Note rows={[]} empty={`${season}시즌 볼카운트 데이터가 아직 없습니다.`} />

  const first = league['초구']
  const twoStrike = league['2S']
  const ahead = league['타자유리']
  const behind = league['투수유리']

  return (
    <>
      {/* 리그 기준선. 개인 값을 이 숫자와 비교해서 읽으라는 뜻으로 맨 위에 둔다. */}
      <div className="cnt-baseline">
        <span>초구 스윙률 <b>{fmtPct(first?.SwingRate)}</b></span>
        <span>2S 도달률 <b>{fmtPct(twoStrike?.PaShare)}</b></span>
        <span>2S 삼진률 <b>{fmtPct(twoStrike?.KRate)}</b></span>
        <span>타자유리 출루율 <b>{fmtRate(ahead?.OnBaseRate)}</b></span>
        <span>투수유리 출루율 <b>{fmtRate(behind?.OnBaseRate)}</b></span>
      </div>

      <div className="cnt-grid">
        <div className="cnt-panel">
          <div className="ars-toolbar">
            <h4 className="ars-sub">리그 카운트 매트릭스</h4>
            <div className="toggle-group">
              {Object.entries(METRICS).map(([key, cfg]) => (
                <button key={key} className={metric === key ? 'active' : ''} onClick={() => setMetric(key)}>
                  {cfg.label}
                </button>
              ))}
            </div>
          </div>
          <div className="ars-scroll cnt-matrix">
            <MiniTable columns={matrixColumns} rows={matrix} />
          </div>
          <p className="ars-foot">
            {m.grain === 'pa'
              ? '작은 숫자 = 그 카운트를 거친 타석 수. 한 타석이 여러 칸에 들어간다(가로·세로 합이 전체가 아니다).'
              : '작은 숫자 = 그 카운트에서 던져진 투구 수.'}
          </p>
        </div>

        <div className="cnt-panel">
          <h4 className="ars-sub">초구 스윙률 분포 ({swarm.length}명 · {MIN_PA}타석 이상)</h4>
          <Beeswarm points={swarm} label="초구 스윙률" fmt={fmtPct} />
          <p className="ars-foot">
            {selected
              ? <>강조된 점 = <b>{selected.name}</b> {fmtPct(selected.buckets['초구']?.SwingRate)}</>
              : '선수를 선택하면 위치가 표시된다.'}
          </p>
        </div>
      </div>

      <div className="ars-toolbar">
        <select value={team} onChange={(e) => { setTeam(e.target.value); setSelectedId(null) }}>
          <option value="all">전체 구단</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label className="ars-check">
          <input type="checkbox" checked={showThin} onChange={(e) => setShowThin(e.target.checked)} />
          {filter.label}
        </label>
        <span className="ars-count">{visible.length}명</span>
      </div>

      <div className="zones-layout">
        <div className="zone-list">
          {/* 필터로 0명이 되면 빈 표로 침묵하지 않는다. */}
          {!visible.length ? (
            <p className="zones-empty">{filter.empty}</p>
          ) : (
            <table>
              <SortHeader cols={LIST_COLS} sort={sort} onSort={(key) => setSort((s) => nextSort(s, key))} />
              <tbody>
                {visible.map((p, i) => (
                  <tr key={p.id} className={p.id === selected?.id ? 'selected' : ''} onClick={() => setSelectedId(p.id)}>
                    <td>{i + 1}</td>
                    <td><strong>{p.name || '-'}</strong></td>
                    <td>{p.team || '-'}</td>
                    <td className={p.pa < MIN_PA ? 'ars-thin' : ''}>{fmtInt(p.pa)}</td>
                    <td>{p.firstSwing === null ? '-' : fmtPct(p.firstSwing)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="zone-card">
          {!selected ? (
            <p className="zones-empty">타자를 선택하세요.</p>
          ) : (
            <>
              <h3>{selected.name} · {selected.team}{selected.side ? ` · ${selected.side}타` : ''}</h3>
              <p className="sub">
                총 {fmtInt(selected.pa)}타석 · 작은 숫자는 리그 평균과의 차이 ·
                {' '}투구 {MIN_BUCKET_PITCHES}구 / 타석 {MIN_BUCKET_PA} 미만은 표본 부족으로 수치를 생략
              </p>
              <div className="ars-scroll">
                <MiniTable columns={bucketColumns} rows={table} />
              </div>
              <p className="ars-foot">
                도달률 = 이 카운트를 거친 타석 비율(초구는 모든 타석이라 생략) ·
                {' '}스윙률·커트율은 그 카운트에서 던져진 공 기준, 삼진률·출루율은 그 카운트를 거친 타석 기준이다.
                {' '}투수유리(0-2·1-2)는 2S 의 부분집합이라 버킷이 서로 배타가 아니다 — 세로 합이 전체가 되지 않는다.
              </p>

              {/* 부분 수집 데이터라 '시즌 누적'으로 오독되지 않게 표본 기간을 고정 노출한다. */}
              {coverage && (
                <p className="ars-coverage">
                  ⚠ 수집 {coverage.Days}경기일 표본 ({coverage.FirstDate} ~ {coverage.LastDate}) · 전 경기가 아니다
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}

export default PitchCount
