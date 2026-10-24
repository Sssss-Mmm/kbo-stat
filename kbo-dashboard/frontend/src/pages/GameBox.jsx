// 경기 박스스코어(/api/v2/games/{id}/box): 팀별 투수·타자 — 박스스코어 값 / 자체 계산 / 검증 상태를 나란히.
import { useRoute } from '../lib/useRoute'
import { updateQuery } from '../lib/navigation'
import { EXCEPTION_LABEL, fetchBox, inningsFromOuts, kboLabel, kstInputToIso, notFoundMessage, OFFICIAL_SOURCE_LABEL } from '../lib/v2'
import { KboBadge, LoadState, PlayerLink, SourceLine, Stat, TimeControls, useV2, VerificationBadge } from '../components/V2Bits'
import '../styles/V2.css'

const GAME_ID = /^\d{8}[A-Z]{4}\d$/

function PitcherTable({ rows, season }) {
  return (
    <div className="v2-table-wrap">
      <table className="v2-table">
        <thead>
          <tr><th className="lalign">투수</th><th>이닝</th><th>타자</th><th>피안타</th><th>볼넷</th><th>삼진</th><th>자책</th>
            <th className="lalign">결과</th><th>계산 이닝</th><th className="lalign">아웃 검증</th><th className="lalign">KBO</th></tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.player_id}>
              <td className="lalign"><PlayerLink id={p.player_id} name={p.name} season={season} role="pitcher" /></td>
              <td className="v2-num">{p.official ? inningsFromOuts(p.official.outs) ?? <Stat value={null} /> : '-'}</td>
              <td className="v2-num">{p.official ? <Stat value={p.official.bf} /> : '-'}</td>
              <td className="v2-num">{p.official ? <Stat value={p.official.h} /> : '-'}</td>
              <td className="v2-num">{p.official ? <Stat value={p.official.bb} /> : '-'}</td>
              <td className="v2-num">{p.official ? <Stat value={p.official.so} /> : '-'}</td>
              <td className="v2-num">{p.official ? <Stat value={p.official.er} /> : '-'}</td>
              <td className="lalign">{p.official?.decision || ''}</td>
              <td className="v2-num">{p.calc ? (inningsFromOuts(p.calc.outs) ?? <Stat value={null} />) : '-'}</td>
              <td className="lalign"><VerificationBadge status={p.verification.Outs} /></td>
              <td className="lalign v2-kbo" title={kboLabel(p.kbo)}>{p.kbo?.status === 'kbo_verified' ? '검증' : '전'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BatterTable({ rows, season }) {
  return (
    <div className="v2-table-wrap">
      <table className="v2-table">
        <thead>
          <tr><th>타순</th><th className="lalign">타자</th><th className="lalign">포지션</th><th>타수</th><th>안타</th><th>홈런</th>
            <th>타점</th><th>볼넷</th><th>삼진</th><th>계산 타석</th><th className="lalign">안타 검증</th></tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.player_id}>
              <td>{b.official?.bat_order ?? '-'}</td>
              <td className="lalign"><PlayerLink id={b.player_id} name={b.name} season={season} role="batter" /></td>
              <td className="lalign">{b.official?.pos || '-'}</td>
              {['ab', 'h', 'hr', 'rbi', 'bb', 'so'].map((k) => (
                <td key={k} className="v2-num">{b.official ? <Stat value={b.official[k]} /> : '-'}</td>
              ))}
              <td className="v2-num">{b.calc ? <Stat value={b.calc.pa} /> : '-'}</td>
              <td className="lalign"><VerificationBadge status={b.verification.H} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function GameBox() {
  const { query } = useRoute()
  const id = (query.get('id') || '').trim().toUpperCase()
  const asOfInput = query.get('asof') || ''
  const valid = GAME_ID.test(id)
  const state = useV2(() => (valid ? fetchBox(id, { asOf: kstInputToIso(asOfInput) }) : Promise.reject(new Error('id'))),
    [id, asOfInput])

  const onSubmit = (e) => {
    e.preventDefault()
    updateQuery({ id: e.currentTarget.elements.id.value })
  }
  const box = state.data?.data
  const season = box ? Number(box.game.date.slice(0, 4)) : null

  return (
    <div className="v2-page">
      <div className="v2-head">
        <h2>경기 박스스코어</h2>
        <form className="v2-controls" onSubmit={onSubmit}>
          <input name="id" defaultValue={id} placeholder="예: 20250719HHKT0" aria-label="경기 ID" pattern="\d{8}[A-Za-z]{4}\d" />
          <button type="submit">보기</button>
        </form>
      </div>
      <TimeControls asOfInput={asOfInput} showThrough={false} onChange={({ asof }) => updateQuery({ asof })} />
      {!valid && <p className="v2-empty">경기 ID(날짜 8자리 + 원정·홈 팀 코드 4자 + 더블헤더 번호)를 입력하거나 선수 경기 기록에서 날짜를 누르세요.</p>}
      {valid && (
        <LoadState state={state.status === 404 ? { ...state, error: notFoundMessage('game', kstInputToIso(asOfInput)) } : state} />
      )}
      {box && (
        <>
          <div className="v2-game-head">
            <span className="v2-game-date">{box.game.date}{box.game.dh ? ` (DH ${box.game.dh})` : ''} · {box.game.ballpark || ''}</span>
            <span className="v2-score">
              {box.game.away} <b>{box.game.score?.away ?? '-'}</b> : <b>{box.game.score?.home ?? '-'}</b> {box.game.home}
            </span>
            {box.exceptions.filter((e) => !e.player_id).map((e) => (
              <span key={e.kind} className="v2-badge v2-info">{EXCEPTION_LABEL[e.kind] || e.kind}</span>
            ))}
            <KboBadge kbo={box.kbo} />
          </div>
          {!box.official && <p className="v2-warn">이 시점의 박스스코어 원본이 없어 자체 계산만 보입니다.</p>}
          {!box.game.score && <p className="v2-note">기준 시점(as_of) 조회에서는 경기 점수·상태를 표시하지 않습니다 — 일정 정보는 이력이 없어 현재 값만 있습니다.</p>}
          {['away', 'home'].map((side) => {
            const team = side === 'away' ? box.game.away : box.game.home
            const pitchers = box.pitchers.filter((p) => p.side === side || (!p.side && p.team === team))
            const batters = box.batters.filter((p) => p.side === side || (!p.side && p.team === team))
            return (
              <section key={side} className="v2-side">
                <h3 className="v2-section">{team} {side === 'away' ? '(원정)' : '(홈)'}</h3>
                {box.official?.team_sum_mismatch?.[side]?.length > 0 && (
                  <p className="v2-warn">원본 팀 합계 불일치 항목: {box.official.team_sum_mismatch[side].join(', ')} — 이 항목은 비교 기준에서 제외</p>
                )}
                <PitcherTable rows={pitchers} season={season} />
                <BatterTable rows={batters} season={season} />
              </section>
            )
          })}
          {box.exceptions.some((e) => e.player_id) && (
            <details className="v2-time">
              <summary>선수별 예외 {box.exceptions.filter((e) => e.player_id).length}건</summary>
              <ul className="v2-verify-list">
                {box.exceptions.filter((e) => e.player_id).map((e, i) => (
                  <li key={i}>{e.player} — {EXCEPTION_LABEL[e.kind] || e.kind}{e.detail ? ` (${e.detail})` : ''}</li>
                ))}
              </ul>
            </details>
          )}
          <SourceLine label={OFFICIAL_SOURCE_LABEL} fetchedAt={box.official?.fetched_at}
            extra={box.official ? `원본 ${box.official.raw_file}` : '원본 없음'} />
        </>
      )}
    </div>
  )
}

export default GameBox
