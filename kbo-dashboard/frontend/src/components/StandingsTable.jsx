// 순위표 표 컴포넌트. data(순위 배열)를 받아 팀별 한 행씩 렌더한다.
// 열 헤더 클릭으로 정렬하고, 팀명을 누르면 onTeamClick(팀명)을 호출한다.
import { useState } from 'react'
import { teamEmblem, teamColor } from '../lib/teamColors'
import { fmtRate, parseRecord, streakScore, recentWinRate } from '../lib/format'
import '../styles/StandingsTable.css'

const fmtGB = (v) => (Number.isFinite(v) ? (v === 0 ? '-' : v.toFixed(1)) : '-')  // 게임차(0이면 '-')

// 기록 문자열("33-1-21", 승-무-패)을 "33-21 .611" 로. 승-패 원기록 + 승률을 같이 보여준다.
const RecordCell = ({ value }) => {
  const { w, l, pct } = parseRecord(value)
  if (!value) return <span className="muted">-</span>
  return <>{w}-{l} <span className="rec-pct">{fmtRate(pct)}</span></>
}

// 열 정의. sort 는 정렬 기준값(문자열 기록은 의미 있는 수치로 환산), desc 는 첫 클릭 방향.
const COLUMNS = [
  { key: 'rank', label: '순위', left: true, sort: (r) => r.rank, render: (r) => r.rank },
  { key: 'team', label: '팀명', left: true, sort: (r) => r.team },
  { key: 'games', label: '경기', sort: (r) => r.games, desc: true },
  { key: 'wins', label: '승', cls: 'win', sort: (r) => r.wins, desc: true },
  { key: 'losses', label: '패', cls: 'loss', sort: (r) => r.losses, desc: true },
  { key: 'draws', label: '무', cls: 'draw', sort: (r) => r.draws, desc: true },
  { key: 'win_rate', label: '승률', cls: 'winrate', sort: (r) => r.win_rate, desc: true, render: (r) => fmtRate(r.win_rate) },
  { key: 'games_behind', label: '게임차', sort: (r) => r.games_behind, render: (r) => fmtGB(r.games_behind) },
  { key: 'last_10_games', label: '최근10', sort: (r) => recentWinRate(r.last_10_games), desc: true, render: (r) => r.last_10_games || '-' },
  {
    key: 'streak', label: '연속', sort: (r) => streakScore(r.streak), desc: true,
    render: (r) => <span className={streakScore(r.streak) > 0 ? 'win' : streakScore(r.streak) < 0 ? 'loss' : 'draw'}>{r.streak || '-'}</span>,
  },
  { key: 'home_record', label: '홈', sort: (r) => parseRecord(r.home_record).pct || 0, desc: true, render: (r) => <RecordCell value={r.home_record} /> },
  { key: 'away_record', label: '원정', sort: (r) => parseRecord(r.away_record).pct || 0, desc: true, render: (r) => <RecordCell value={r.away_record} /> },
]

function StandingsTable({ data, onTeamClick }) {
  const [sort, setSort] = useState({ key: 'rank', desc: false })  // 기본: 순위 오름차순

  // 같은 열을 다시 누르면 역순, 다른 열이면 그 열의 기본 방향으로.
  const toggle = (col) => setSort((s) => (s.key === col.key ? { key: s.key, desc: !s.desc } : { key: col.key, desc: !!col.desc }))

  const col = COLUMNS.find((c) => c.key === sort.key) || COLUMNS[0]
  const rows = [...data].sort((a, b) => {
    const [x, y] = [col.sort(a), col.sort(b)]
    const d = typeof x === 'string' ? x.localeCompare(y, 'ko') : (x ?? 0) - (y ?? 0)
    return sort.desc ? -d : d
  })

  return (
    <div className="standings-scroll">
      <table className={`standings-table${sort.key === 'rank' && !sort.desc ? ' by-rank' : ''}`}>
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                className={c.left ? 'lalign' : ''}
                aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}
              >
                <button type="button" className="sort-btn" onClick={() => toggle(c)}>
                  {c.label}
                  <span className="sort-mark" aria-hidden="true">{sort.key === c.key ? (sort.desc ? '▼' : '▲') : ''}</span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((team) => (
            <tr
              key={team.team}
              className={`rank-${team.rank}`}
              style={{ '--team-c': teamColor(team.team) }}
            >
              {COLUMNS.map((c) => (
                <td key={c.key} className={[c.cls, c.left ? 'lalign' : ''].filter(Boolean).join(' ')}>
                  {c.key === 'team' ? (
                    <button type="button" className="team-link" onClick={() => onTeamClick?.(team.team)} title={`${team.team} 팀 분석 보기`}>
                      {teamEmblem(team.team) && <img className="team-emblem" src={teamEmblem(team.team)} alt="" loading="lazy" />}
                      {team.team}
                    </button>
                  ) : c.render ? c.render(team) : team[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default StandingsTable
