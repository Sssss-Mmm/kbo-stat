// 타이틀 레이스: 날짜별 순위 변동 멀티라인(SVG). 1위가 위로.
// 팀(선/점/라벨)을 클릭하면 그 팀만 강조, 다시 클릭하면 전체 표시.
import { useState } from 'react'

const W = 760
const H = 320
const PAD = { l: 26, r: 64, t: 14, b: 24 }

function RankRace({ series, dateCount, teamCount }) {
  const [selected, setSelected] = useState(null)

  if (!series.length || dateCount < 2) return <p className="empty">순위 변동 데이터가 부족합니다.</p>

  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b
  const sx = (i) => PAD.l + (i / (dateCount - 1)) * innerW
  const sy = (rank) => PAD.t + ((rank - 1) / (teamCount - 1)) * innerH

  const toggle = (team) => setSelected((cur) => (cur === team ? null : team))

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
        const dim = selected && selected !== s.team
        const active = selected === s.team
        return (
          <g key={s.team} style={{ cursor: 'pointer' }} onClick={() => toggle(s.team)}>
            {/* 클릭 히트 영역 확대용 투명 굵은 선 */}
            <path d={d} fill="none" stroke="transparent" strokeWidth={12} />
            <path
              d={d}
              fill="none"
              stroke={s.color}
              strokeWidth={active ? 3.2 : 2.2}
              strokeLinejoin="round"
              strokeOpacity={dim ? 0.1 : 0.9}
            />
            <circle cx={sx(last.index)} cy={sy(last.rank)} r={active ? 4 : 3} fill={s.color} fillOpacity={dim ? 0.15 : 1} />
            <text
              x={sx(last.index) + 6}
              y={sy(last.rank) + 4}
              className="race-label"
              fill={s.color}
              fillOpacity={dim ? 0.35 : 1}
              fontWeight={active ? 800 : undefined}
            >
              {s.team}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default RankRace
