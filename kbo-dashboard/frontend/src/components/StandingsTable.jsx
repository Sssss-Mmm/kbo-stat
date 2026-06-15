// 순위표 표 컴포넌트. data(순위 배열)를 받아 팀별 한 행씩 렌더하는 순수 표시용.
import { teamEmblem } from '../lib/teamColors'
import '../styles/StandingsTable.css'

const fmtRate = (v) => (Number.isFinite(v) ? v.toFixed(3).replace(/^0/, '') : '-')  // 승률: .xxx
const fmtGB = (v) => (Number.isFinite(v) ? (v === 0 ? '-' : v.toFixed(1)) : '-')  // 게임차(0이면 '-')

function StandingsTable({ data }) {
  return (
    <table className="standings-table">
      <thead>
        <tr>
          <th>순위</th>
          <th>팀명</th>
          <th>경기</th>
          <th>승</th>
          <th>패</th>
          <th>무</th>
          <th>승률</th>
          <th>게임차</th>
        </tr>
      </thead>
      <tbody>
        {data.map((team, index) => (
          <tr key={index} className={`rank-${index + 1}`}>
            <td>{index + 1}</td>
            <td className="team-name">
              {teamEmblem(team.team) && <img className="team-emblem" src={teamEmblem(team.team)} alt={team.team} loading="lazy" />}
              {team.team}
            </td>
            <td>{team.games}</td>
            <td className="win">{team.wins}</td>
            <td className="loss">{team.losses}</td>
            <td className="draw">{team.draws}</td>
            <td className="winrate">{fmtRate(team.win_rate)}</td>
            <td>{fmtGB(team.games_behind)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default StandingsTable
