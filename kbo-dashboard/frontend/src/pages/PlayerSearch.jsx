// 선수 찾기(P2-D): 이름·팀·시즌·역할로 찾는다. 동명이인은 선수 ID 로 나누고 팀·포지션·생년월일·시즌 범위를 같이 보인다.
// 조건은 URL 쿼리(q, team, season, role). 검색 범위 = 선수 ID 가 있는 네이버 시즌 기록(2007–).
import { useEffect, useState } from 'react'
import { LoadState, SourceLine, useV2 } from '../components/V2Bits'
import { useRoute } from '../lib/useRoute'
import { followLink, pageUrl, updateQuery } from '../lib/navigation'
import { intParam } from '../lib/v2'
import { latestCollected, NAVER_SEASON_LABEL, playerLabel, ROLE_LABEL, searchPlayers, seasonSpan } from '../lib/p2d'
import '../styles/V2.css'
import '../styles/P2D.css'

const TEAMS = ['KIA', 'KT', 'LG', 'NC', 'SSG', '두산', '롯데', '삼성', '키움', '한화']

function PlayerSearch() {
  const { query } = useRoute()
  const q = query.get('q') || ''
  const team = query.get('team') || ''
  const season = intParam(query, 'season')
  const role = ['batter', 'pitcher'].includes(query.get('role')) ? query.get('role') : null
  const [text, setText] = useState(q)
  useEffect(() => setText(q), [q])
  useEffect(() => {  // 입력이 멈추면 URL 에 반영(뒤로 가기 기록은 남기지 않는다)
    const t = setTimeout(() => text.trim() !== q && updateQuery({ q: text.trim() || null }, true), 300)
    return () => clearTimeout(t)
  }, [text, q])
  const ready = Boolean(q || team)
  const state = useV2(() => (ready ? searchPlayers({ q, team, season, role }) : Promise.resolve(null)), [q, team, season, role])
  const body = state.data
  const seasons = body?.coverage?.seasons || []

  return (
    <div className="v2-page">
      <div className="v2-head">
        <h2>선수 찾기</h2>
        <div className="v2-controls">
          <input type="search" className="p2d-search" placeholder="선수 이름" value={text} aria-label="선수 이름"
            onChange={(e) => setText(e.target.value)} maxLength={30} />
          <select value={team} onChange={(e) => updateQuery({ team: e.target.value || null })} aria-label="팀">
            <option value="">전체 팀</option>
            {TEAMS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input type="number" className="p2d-season" placeholder="시즌" value={season ?? ''} min={2007} max={2026} aria-label="시즌"
            onChange={(e) => updateQuery({ season: e.target.value || null })} />
          <div className="v2-seg">
            {[[null, '전체'], ['batter', '타자'], ['pitcher', '투수']].map(([k, label]) => (
              <button key={label} className={role === k ? 'on' : ''} onClick={() => updateQuery({ role: k })}>{label}</button>))}
          </div>
        </div>
      </div>
      <p className="v2-note">
        이름 일부로 찾을 수 있습니다(띄어쓰기 무시). 같은 이름의 다른 선수는 선수 ID 로 나눠 따로 보입니다 — 팀·포지션·생년월일로 구분하세요.
        {' '}팀 이름은 그 시즌 기준입니다(SK → SSG 등 바뀐 이름은 따로 찾습니다).
      </p>

      {!ready && <p className="v2-empty">선수 이름을 입력하거나 팀을 고르세요.</p>}
      {ready && <LoadState state={state} empty={body && !body.data.length ? '조건에 맞는 선수가 없습니다.' : null} />}
      {body && body.data.length > 0 && (
        <>
          <p className="v2-foot">{body.total}명{body.truncated ? ` 중 ${body.data.length}명만 표시 — 조건을 좁혀 주세요` : ''}</p>
          <div className="v2-table-wrap">
            <table className="v2-table p2d-results">
              <thead><tr><th className="lalign">선수</th><th className="lalign">최근 시즌</th><th className="lalign">기록 범위</th>
                <th className="lalign">투타</th><th className="lalign">비교</th></tr></thead>
              <tbody>
                {body.data.map((p) => {
                  const latest = p.seasons[0]
                  return (
                    <tr key={p.player_id}>
                      <td className="lalign">
                        <a href={pageUrl('player', { id: p.player_id, season: latest.season, role: latest.role })} onClick={followLink}>
                          {playerLabel(p)}</a>
                        {p.same_name > 0 && <span className="v2-badge v2-info" title="같은 이름의 다른 선수가 있습니다">동명이인 {p.same_name + 1}명</span>}
                        <div className="v2-metric">ID {p.player_id}</div>
                      </td>
                      <td className="lalign">{latest.season} {latest.team} · {ROLE_LABEL[latest.role]}{latest.back_no ? ` · No.${latest.back_no}` : ''}</td>
                      <td className="lalign">{seasonSpan(p.seasons)}</td>
                      <td className="lalign">{p.pitch_bat || '-'}</td>
                      <td className="lalign">
                        {[...new Set(p.seasons.map((s) => s.role))].map((r) => (
                          <a key={r} className="p2d-compare-link" href={pageUrl('compare', { role: r, a: p.player_id })} onClick={followLink}>
                            {ROLE_LABEL[r]} 비교</a>))}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      {body && (
        <SourceLine label={NAVER_SEASON_LABEL} fetchedAt={latestCollected(body.meta.sources)}
          extra={`검색 범위 ${seasons[0] ?? '-'}–${seasons.at(-1) ?? '-'} · 생년월일·투타는 KBO 등록선수 명단(2026 일부)에 있는 선수만`} />
      )}
    </div>
  )
}

export default PlayerSearch
