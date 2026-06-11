// 1차원 분포 beeswarm(SVG). points: [{value, color, label}].
// 값에 따라 x 배치, 같은 구간은 위/아래로 쌓아 겹침을 줄인다.
const W = 760
const H = 150
const PAD = { l: 16, r: 16, t: 10, b: 28 }
const R = 4

function Beeswarm({ points, label, fmt = (v) => v }) {
  const pts = points.filter((p) => Number.isFinite(p.value))
  if (!pts.length) return <p className="empty">데이터 없음</p>

  const values = pts.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const mean = values.reduce((a, b) => a + b, 0) / values.length
  const innerW = W - PAD.l - PAD.r
  const midY = PAD.t + (H - PAD.t - PAD.b) / 2
  const sx = (v) => PAD.l + ((v - min) / (max - min || 1)) * innerW

  // x 정렬 후 구간별 카운트로 위/아래 교차 배치.
  const sorted = [...pts].sort((a, b) => a.value - b.value)
  const binW = R * 1.6
  const binCount = {}
  const placed = sorted.map((p) => {
    const x = sx(p.value)
    const bin = Math.round(x / binW)
    const n = binCount[bin] || 0
    binCount[bin] = n + 1
    // 0, +1, -1, +2, -2 ... 순서로 중심에서 퍼지게
    const step = Math.ceil(n / 2)
    const dir = n % 2 === 0 ? -1 : 1
    const y = midY + dir * step * (R * 1.7)
    return { ...p, x, y }
  })

  return (
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} 분포`}>
      <line x1={PAD.l} y1={midY} x2={W - PAD.r} y2={midY} stroke="var(--line)" />
      {/* 평균선 */}
      <line x1={sx(mean)} y1={PAD.t} x2={sx(mean)} y2={H - PAD.b} stroke="var(--accent-2)" strokeDasharray="3 3" />
      <text x={sx(mean)} y={H - 14} textAnchor="middle" className="axis-label">평균 {fmt(mean)}</text>
      <text x={PAD.l} y={H - 14} textAnchor="start" className="axis-label">{fmt(min)}</text>
      <text x={W - PAD.r} y={H - 14} textAnchor="end" className="axis-label">{fmt(max)}</text>
      {placed.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={R} fill={p.color} fillOpacity={0.82} stroke="#fff" strokeWidth={0.5}>
          <title>{`${p.label || ''} · ${label} ${fmt(p.value)}`}</title>
        </circle>
      ))}
    </svg>
  )
}

export default Beeswarm
