// 선수 비교 양방향 막대(div + CSS grid). A 는 가운데에서 왼쪽으로, B 는 오른쪽으로 자란다.
// 막대 길이 = 리그 백분위(lib/p2d metricPercentile — 수치표와 같은 계산). 백분위가 없으면 막대를 그리지 않고 사유를 적는다.
// rows: [{ m, a, b, win }]  a·b = metricPercentile 결과, win = 'a' | 'b' | 'tie' | null(수치표 winner 규칙 그대로)
// sides: { a: {name, player, season, color, thin, sample}, b: {...} }  thin = 규정 미달(막대를 빗금으로)
import { chartRowLabel, missingReasons } from '../../lib/p2d'

function Bar({ s, color, thin, dir }) {
  // 짧은 문구만 — 정확한 사유는 툴팁·아래 사유 목록·스크린리더 문장에 있다
  if (s.pct === null) return <span className={`cb-track cb-${dir} cb-none`} title={s.reason}><small>{s.short}</small></span>
  return (
    <span className={`cb-track cb-${dir}`}>
      <span className={`cb-fill${thin ? ' cb-thin' : ''}`} style={{ width: `${s.pct}%`, '--cb-color': color }} />
    </span>
  )
}

// 우세는 두 자리에 둔다: 데스크톱은 백분위 줄의 ' · 우세', 600px 이하는 값 옆 테두리 배지(CSS 로 하나만 보인다).
// 좁은 칸에서 '94백분위 · 우세' 가 중간에서 끊기지 않게 하려는 것 — 어느 쪽이든 글자로 남아 색에만 기대지 않는다.
function Value({ s, won }) {
  return (
    <span className={`cb-val${won ? ' cb-won' : ''}`}>
      <b>{s.text}{won && <em className="cb-win-m">우세</em>}</b>
      <small>{s.pct === null ? '백분위 없음' : `${s.pct}백분위`}{won && <span className="cb-win-d"> · 우세</span>}</small>
    </span>
  )
}

function CompareBars({ rows, sides }) {
  const names = [sides.a.name, sides.b.name]
  const reasons = missingReasons(rows, [`${sides.a.player} · ${sides.a.season}`, `${sides.b.player} · ${sides.b.season}`])
  return (
    <div className="cb">
      <div className="cb-head" aria-hidden="true">
        <span style={{ '--cb-color': sides.a.color }}>{names[0]}</span>
        <span>← 백분위 100 · 0 · 100 →</span>
        <span style={{ '--cb-color': sides.b.color }}>{names[1]}</span>
      </div>
      <ul className="cb-rows" aria-label="리그 백분위 비교">
        {rows.map(({ m, a, b, win }) => {
          const n = a.n === b.n || b.n === null ? a.n : a.n === null ? b.n : `${a.n} · ${b.n}`
          return (
            <li key={m.key} className="cb-row">
              <span className="cb-sr">{chartRowLabel(m, names, a, b, win)}</span>
              <span className="cb-vis" aria-hidden="true">
                <Value s={a} won={win === 'a'} />
                <Bar s={a} color={sides.a.color} thin={sides.a.thin} dir="a" />
                <span className="cb-label">
                  {m.label}
                  {m.better === 'low' && <small>낮을수록 좋음</small>}
                  {n !== null && <small>n {n}</small>}
                </span>
                <Bar s={b} color={sides.b.color} thin={sides.b.thin} dir="b" />
                <Value s={b} won={win === 'b'} />
              </span>
            </li>
          )
        })}
      </ul>
      {reasons.length > 0 && (
        <div className="cb-reasons">
          <b>백분위 없음 사유</b> — 막대를 0 으로 그리지 않고 비워 둡니다.
          <ul>{reasons.map((r) => <li key={r.reason}>{r.items.join(', ')}: {r.reason}</li>)}</ul>
        </div>
      )}
      <div className="cb-foot">
        {['a', 'b'].map((k) => (
          <span key={k} style={{ '--cb-color': sides[k].color }}>
            <b>{sides[k].name}</b> {sides[k].sample}
            {sides[k].thin && <> · <span className="cb-thin-key" aria-hidden="true" /> 빗금 막대 = 참고값(백분위는 규정 충족 선수 기준)</>}
          </span>
        ))}
      </div>
    </div>
  )
}

export default CompareBars
