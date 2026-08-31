// 여러 페이지가 공유하는 소형 표시 컴포넌트들 (순수 표시용, 자체 상태 없음).
import { teamColor, teamEmblem } from '../lib/teamColors'
import { fmtRate } from '../lib/format'

// 컬럼 정의(columns: {key,label,render,left})로 그리는 소형 표.
export function MiniTable({ columns, rows }) {
  return (
    <table className="mini-table">
      <thead>
        <tr>{columns.map((c) => <th key={c.key} className={c.left ? 'lalign' : ''}>{c.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {columns.map((c) => <td key={c.key} className={c.left ? 'lalign' : ''}>{c.render ? c.render(r, i) : r[c.key]}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// 가로 막대 리스트. 최대값을 100%로 잡아 상대 길이를 그린다.
export function BarList({ items, fmt = fmtRate }) {
  const max = Math.max(...items.map((i) => i.value), 0.0001)
  return (
    <div className="bar-list">
      {items.map((it) => (
        <div className="bar-row" key={it.label}>
          <span className="bar-team">{it.label}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(it.value / max) * 100}%`, background: it.color }} />
          </span>
          <span className="bar-val">{fmt(it.value)}</span>
        </div>
      ))}
    </div>
  )
}

// 패널 안내문. 로드 실패(null)와 "데이터가 원래 없음"([])을 구분해 보여준다(NFR-06).
export function Note({ rows, empty }) {
  return rows === null
    ? <p className="error">불러오지 못했습니다.</p>
    : <p className="empty">{empty}</p>
}

// 팀 엠블럼 + 팀 색상 이름 셀.
export function TeamCell({ team }) {
  return (
    <span className="team-cell">
      {teamEmblem(team) && <img src={teamEmblem(team)} alt="" />}
      <b style={{ color: teamColor(team) }}>{team}</b>
    </span>
  )
}
