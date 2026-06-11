// 타이틀 레이스: 날짜별 순위 변동 멀티라인(SVG). 1위가 위로.
const W = 760
const H = 320
const PAD = { l: 26, r: 64, t: 14, b: 24 }

function RankRace({ series, dateCount, teamCount }) {
  if (!series.length || dateCount < 2) return <p className="empty">순위 변동 데이터가 부족합니다.</p>

  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b
  const sx = (i) => PAD.l + (i / (dateCount - 1)) * innerW
  const sy = (rank) => PAD.t + ((rank - 1) / (teamCount - 1)) * innerH

  return (
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="순위 변화">
      {Array.from({ length: teamCount }, (_, r) => (
        <g key={r}>
          <line x1={PAD.l} y1={sy(r + 1)} x2={W - PAD.r} y2={sy(r + 1)} stroke="var(--line)" strokeOpacity={0.5} />
          <text x={PAD.l - 6} y={sy(r + 1) + 4} textAnchor="end" className="axis-label">{r + 1}</text>
        </g>
      ))}
      {series.map((s) => {
        const d = s.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(p.index)} ${sy(p.rank)}`).join(' ')
        const last = s.points[s.points.length - 1]
        return (
          <g key={s.team}>
            <path d={d} fill="none" stroke={s.color} strokeWidth={2.2} strokeLinejoin="round" strokeOpacity={0.9} />
            <circle cx={sx(last.index)} cy={sy(last.rank)} r={3} fill={s.color} />
            <text x={sx(last.index) + 6} y={sy(last.rank) + 4} className="race-label" fill={s.color}>{s.team}</text>
          </g>
        )
      })}
    </svg>
  )
}

export default RankRace
