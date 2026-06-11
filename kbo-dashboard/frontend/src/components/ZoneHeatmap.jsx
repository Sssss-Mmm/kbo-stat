// 3×3 스트라이크존 히트맵. 리그 평균을 중앙값으로 한 발산(파랑→빨강) 색상.
const COLOR_LOW = [59, 111, 212]
const COLOR_MID = [242, 244, 246]
const COLOR_HIGH = [216, 64, 58]
const METRIC_SPREAD = { hit: 0.25, swing: 0.3 }
const MIN_SAMPLE = { hit: 2, swing: 3 }

function fmtRate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, '') : '-'
}

function lerp(a, b, t) {
  return a.map((channel, index) => Math.round(channel + (b[index] - channel) * t))
}

function cellColor(value, avg, metric) {
  const spread = METRIC_SPREAD[metric]
  const t = Math.max(-1, Math.min(1, (value - avg) / spread))
  const rgb = t >= 0 ? lerp(COLOR_MID, COLOR_HIGH, t) : lerp(COLOR_MID, COLOR_LOW, -t)
  return `rgb(${rgb.join(',')})`
}

function ZoneHeatmap({ cells, metric, leagueAvg }) {
  const byZone = new Map(cells.map((cell) => [cell.Zone, cell]))
  const minSample = MIN_SAMPLE[metric]

  // row 3=상단, 1=하단 / col 1=좌, 3=우 (투수 시점 기준).
  const grid = [3, 2, 1].flatMap((r) =>
    [1, 2, 3].map((c) => {
      const cell = byZone.get(`${r}-${c}`)
      const pitches = cell?.Pitches || 0
      const inPlay = cell?.InPlay || 0
      const swings = cell?.Swings || 0
      const hits = cell?.Hits || 0

      let value = null
      let sample
      if (metric === 'swing') {
        sample = `${swings}/${pitches}`
        if (pitches >= minSample) value = pitches ? swings / pitches : null
      } else {
        sample = `${hits}/${inPlay}`
        if (inPlay >= minSample) value = inPlay ? hits / inPlay : null
      }

      const key = `${r}-${c}`
      if (value === null) {
        return (
          <div key={key} className="heat-cell empty">
            <span className="val">—</span>
            <span className="sub">{pitches}구</span>
          </div>
        )
      }
      return (
        <div key={key} className="heat-cell" style={{ background: cellColor(value, leagueAvg, metric) }}>
          <span className="val">{fmtRate(value)}</span>
          <span className="sub">{sample}</span>
        </div>
      )
    })
  )

  return (
    <div className="heat-frame">
      <div className="axis">높은 코스</div>
      <div className="heat-grid">{grid}</div>
      <div className="axis">낮은 코스</div>
      <div className="heat-legend">
        <span>낮음</span>
        <span className="bar" />
        <span>높음</span>
        <span style={{ marginLeft: 10 }}>리그 평균 {fmtRate(leagueAvg)}</span>
      </div>
    </div>
  )
}

export default ZoneHeatmap
