// 투구 존 히트맵. 격자 크기(gridN)는 데이터에서 받는다(build_zone_metrics.py 의 GRID_N).
// 안쪽 gridN-2 칸이 스트라이크존, 바깥 테두리 한 겹이 존 밖(유인구)이라 테두리는 굵은 선으로 구분한다.
// 리그 평균을 중앙값으로 한 발산(파랑→빨강) 색상.
// index.css 의 --scale-lo/--scale-mid/--scale-hi 와 같은 값이다. 셀 배경을 JS 가
// 계산하므로 CSS 변수를 읽을 수 없어 여기에 한 벌 더 둔다 — 한쪽만 바꾸면 어긋난다.
const COLOR_LOW = [58, 110, 165]   // #3a6ea5
const COLOR_MID = [238, 240, 242]  // #eef0f2
const COLOR_HIGH = [180, 71, 47]   // #b4472f
const METRIC_SPREAD = { hit: 0.25, swing: 0.3 }
const MIN_SAMPLE = { hit: 2, swing: 3 }

function fmtRate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, '') : '-'
}

// 두 RGB 색을 t(0~1)로 선형 보간.
function lerp(a, b, t) {
  return a.map((channel, index) => Math.round(channel + (b[index] - channel) * t))
}

// 셀 값과 리그 평균의 차이를 spread로 정규화해 파랑(낮음)↔빨강(높음) 발산 색을 만든다.
function cellColor(value, avg, metric) {
  const spread = METRIC_SPREAD[metric]
  const t = Math.max(-1, Math.min(1, (value - avg) / spread))  // -1~1 로 클램프
  const rgb = t >= 0 ? lerp(COLOR_MID, COLOR_HIGH, t) : lerp(COLOR_MID, COLOR_LOW, -t)
  return `rgb(${rgb.join(',')})`
}

function ZoneHeatmap({ cells, metric, leagueAvg, gridN = 5 }) {
  const byZone = new Map(cells.map((cell) => [cell.Zone, cell]))
  const minSample = MIN_SAMPLE[metric]
  const axis = Array.from({ length: gridN }, (_, i) => i + 1)
  // 존 안쪽(스트라이크존) 칸 번호는 2 ~ gridN-1, 1 과 gridN 은 존 밖 테두리.
  const inZone = (r, c) => r > 1 && r < gridN && c > 1 && c < gridN

  // row 1=상단, gridN=하단 / col 1=좌, gridN=우 (투수 시점 기준).
  const grid = axis.flatMap((r) =>
    axis.map((c) => {
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
          <div key={key} className={`heat-cell empty${inZone(r, c) ? ' in-zone' : ''}`}>
            <span className="val">—</span>
            <span className="sub">{pitches}구</span>
          </div>
        )
      }
      return (
        <div key={key} className={`heat-cell${inZone(r, c) ? ' in-zone' : ''}`} style={{ background: cellColor(value, leagueAvg, metric) }}>
          <span className="val">{fmtRate(value)}</span>
          <span className="sub">{sample}</span>
        </div>
      )
    })
  )

  return (
    <div className="heat-frame">
      <div className="axis">높은 코스</div>
      <div className="heat-grid" style={{ '--grid-n': gridN }}>{grid}</div>
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
