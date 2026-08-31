// 연도별 추이 멀티라인(SVG). series: [{label, color, points:[{x,y}]}].
// x 는 연도(정수), y 는 값. 시리즈마다 x 범위가 달라도 된다(경기시간의 정규이닝 계열은 2010~).
const W = 760
const H = 300
const PAD = { l: 46, r: 16, t: 28, b: 30 }

function TrendLine({ series, yLabel, fmt = (v) => v, xTickStep = 5 }) {
  const lines = series
    .map((s) => ({ ...s, points: s.points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y)).sort((a, b) => a.x - b.x) }))
    .filter((s) => s.points.length)
  const all = lines.flatMap((s) => s.points)
  if (all.length < 2) return <p className="empty">추이 데이터가 부족합니다.</p>

  const xs = all.map((p) => p.x)
  const ys = all.map((p) => p.y)
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  const yMin = Math.min(...ys)
  const yMax = Math.max(...ys)
  const gap = (yMax - yMin) * 0.1 || 1
  const y0 = yMin - gap
  const y1 = yMax + gap
  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b
  const sx = (v) => PAD.l + ((v - x0) / (x1 - x0 || 1)) * innerW
  const sy = (v) => PAD.t + (1 - (v - y0) / (y1 - y0 || 1)) * innerH

  const yTicks = Array.from({ length: 4 }, (_, i) => y0 + ((y1 - y0) * i) / 3)
  const xTicks = []
  for (let x = Math.ceil(x0 / xTickStep) * xTickStep; x <= x1; x += xTickStep) xTicks.push(x)

  // 범례는 SVG 상단에 직접 배치한다(라벨 폭은 한글 기준 근사).
  let legendX = PAD.l

  return (
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${yLabel} 연도별 추이`}>
      {yTicks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} y1={sy(v)} x2={W - PAD.r} y2={sy(v)} stroke="var(--line)" strokeOpacity={0.6} />
          <text x={PAD.l - 6} y={sy(v) + 4} textAnchor="end" className="axis-label">{fmt(v)}</text>
        </g>
      ))}
      {xTicks.map((x) => (
        <text key={x} x={sx(x)} y={H - 10} textAnchor="middle" className="axis-label">{x}</text>
      ))}
      <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="var(--line)" />

      {lines.map((s) => (
        <g key={s.label}>
          <path
            d={s.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(p.x)} ${sy(p.y)}`).join(' ')}
            fill="none"
            stroke={s.color}
            strokeWidth={2.2}
            strokeLinejoin="round"
          />
          {s.points.map((p) => (
            <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r={2.4} fill={s.color}>
              <title>{`${p.x} · ${s.label} ${fmt(p.y)}`}</title>
            </circle>
          ))}
        </g>
      ))}

      {lines.map((s) => {
        const x = legendX
        legendX += 26 + s.label.length * 11
        return (
          <g key={`lg-${s.label}`}>
            <line x1={x} y1={12} x2={x + 16} y2={12} stroke={s.color} strokeWidth={2.6} />
            <text x={x + 21} y={16} className="axis-label">{s.label}</text>
          </g>
        )
      })}
      <text x={12} y={PAD.t + innerH / 2} textAnchor="middle" className="axis-label" transform={`rotate(-90 12 ${PAD.t + innerH / 2})`}>{yLabel}</text>
    </svg>
  )
}

export default TrendLine
