// 범용 산점도(SVG). points: [{x, y, color, label}]. 평균 십자선 옵션.
const W = 360
const H = 260
const PAD = { l: 44, r: 14, t: 12, b: 34 }

function niceDomain(values) {
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return [min - 1, max + 1]
  }
  const pad = (max - min) * 0.06
  return [min - pad, max + pad]
}

function Scatter({ points, xLabel, yLabel, xInvert = false, yInvert = false, showMeans = true, fmt = (v) => v }) {
  const pts = points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
  if (!pts.length) return <p className="empty">데이터 없음</p>

  const xs = pts.map((p) => p.x)
  const ys = pts.map((p) => p.y)
  const [x0, x1] = niceDomain(xs)
  const [y0, y1] = niceDomain(ys)
  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b

  const sx = (v) => {
    const t = (v - x0) / (x1 - x0 || 1)
    return PAD.l + (xInvert ? 1 - t : t) * innerW
  }
  const sy = (v) => {
    const t = (v - y0) / (y1 - y0 || 1)
    return PAD.t + (yInvert ? t : 1 - t) * innerH
  }

  const meanX = xs.reduce((a, b) => a + b, 0) / xs.length
  const meanY = ys.reduce((a, b) => a + b, 0) / ys.length

  return (
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${xLabel} vs ${yLabel}`}>
      {/* 축 */}
      <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="var(--line)" />
      <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} stroke="var(--line)" />

      {showMeans && (
        <>
          <line x1={sx(meanX)} y1={PAD.t} x2={sx(meanX)} y2={H - PAD.b} stroke="var(--line)" strokeDasharray="3 3" />
          <line x1={PAD.l} y1={sy(meanY)} x2={W - PAD.r} y2={sy(meanY)} stroke="var(--line)" strokeDasharray="3 3" />
        </>
      )}

      {pts.map((p, i) => (
        <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={3.4} fill={p.color} fillOpacity={0.8} stroke="#fff" strokeWidth={0.5}>
          <title>{`${p.label || ''} · ${xLabel} ${fmt(p.x)} · ${yLabel} ${fmt(p.y)}`}</title>
        </circle>
      ))}

      {/* 축 라벨 */}
      <text x={PAD.l + innerW / 2} y={H - 6} textAnchor="middle" className="axis-label">{xLabel}</text>
      <text x={12} y={PAD.t + innerH / 2} textAnchor="middle" className="axis-label" transform={`rotate(-90 12 ${PAD.t + innerH / 2})`}>{yLabel}</text>
    </svg>
  )
}

export default Scatter
