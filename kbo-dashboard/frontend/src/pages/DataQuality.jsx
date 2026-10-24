// 데이터 출처·검증 상태(/api/v2/data-quality). 수치는 계산하지 않고 API 가 준 그대로 보여 준다.
import { useRoute } from '../lib/useRoute'
import { updateQuery } from '../lib/navigation'
import { EXCEPTION_LABEL, fetchDataQuality, fmtKst, intParam, kstInputToIso, OFFICIAL_SOURCE_LABEL, VERIFICATION } from '../lib/v2'
import { LoadState, TimeControls, useV2, VerificationBadge } from '../components/V2Bits'
import '../styles/V2.css'

const POLICY = {
  disabled_pending_approval: '자동 수집 중단(승인 전)',
  paused_pending_terms_review: '자동 수집 일시 중단(이용 조건 확인 전)',
}
const SOURCE_NAME = { kbo_official_site: 'KBO 공식 사이트', naver_sports: '네이버 스포츠' }
const STATUS_ORDER = Object.keys(VERIFICATION)

function DataQuality() {
  const { query } = useRoute()
  const season = intParam(query, 'season', 2025)
  const asOfInput = query.get('asof') || ''
  const state = useV2(() => fetchDataQuality(season, { asOf: kstInputToIso(asOfInput) }), [season, asOfInput])
  const d = state.data?.data

  return (
    <div className="v2-page">
      <div className="v2-head">
        <h2>데이터 출처·검증</h2>
        <div className="v2-controls"><span className="v2-pill">{season} 시즌</span></div>
      </div>
      <TimeControls asOfInput={asOfInput} showThrough={false} onChange={({ asof }) => updateQuery({ asof })} />
      <LoadState state={state} />
      {d && (
        <>
          <div className="v2-cards">
            <section className="v2-card">
              <h3>범위</h3>
              <dl className="v2-dl">
                <div><dt>완료 경기(일정)</dt><dd>{d.coverage.final_games ?? '이 시점 기준 알 수 없음'}</dd></div>
                <div><dt>박스스코어 원본</dt><dd>{d.coverage.official_raw_games}</dd></div>
                <div><dt>자체 계산 경기</dt><dd>{d.coverage.calc_games}</dd></div>
              </dl>
              <p className="v2-card-sub">기준 기록: {OFFICIAL_SOURCE_LABEL}</p>
            </section>
            <section className="v2-card">
              <h3>수집 상태</h3>
              <ul className="v2-verify-list">
                {Object.entries(d.collection.policy).map(([k, v]) => <li key={k}><b>{SOURCE_NAME[k] || k}</b> {POLICY[v] || v}</li>)}
                <li><b>마지막 원본 수집</b> {fmtKst(d.collection.official_fetched_at_max)}</li>
              </ul>
            </section>
            <section className="v2-card">
              <h3>KBO 직접 검증</h3>
              <p className="v2-big">{d.kbo_verified ?? '-'}건</p>
              <p className="v2-card-sub">KBO 공식 사이트 원본과 직접 대조한 기록이 아직 없습니다. 아래 상태는 모두 네이버 박스스코어와의 대조입니다.</p>
            </section>
          </div>

          <h3 className="v2-section">항목별 대조 (자체 계산 ↔ 네이버)</h3>
          <div className="v2-table-wrap">
            <table className="v2-table">
              <thead>
                <tr><th className="lalign">항목</th>{STATUS_ORDER.map((s) => <th key={s}><VerificationBadge status={s} /></th>)}</tr>
              </thead>
              <tbody>
                {Object.entries(d.verification.by_metric).sort().map(([metric, counts]) => (
                  <tr key={metric}>
                    <td className="lalign">{metric.replace('pitcher.', '투수 ').replace('batter.', '타자 ')}</td>
                    {STATUS_ORDER.map((s) => <td key={s} className="v2-num">{counts[s] ?? ''}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="v2-legend">
            {STATUS_ORDER.map((s) => <div key={s}><dt><VerificationBadge status={s} /></dt><dd>{VERIFICATION[s].label}</dd></div>)}
          </dl>

          <div className="v2-cards">
            <section className="v2-card">
              <h3>아웃 미확정 투수-경기</h3>
              <ul className="v2-verify-list">
                {Object.entries(d.outs_uncertain).map(([s, n]) => <li key={s}><VerificationBadge status={s} /> {n}</li>)}
              </ul>
              <p className="v2-card-sub">자체 계산 아웃은 미확정으로 남기고, 네이버 값과의 대조만 표시합니다.</p>
            </section>
            <section className="v2-card">
              <h3>예외 사례</h3>
              <ul className="v2-verify-list">
                {Object.entries(d.exceptions).map(([k, n]) => <li key={k}><b>{EXCEPTION_LABEL[k] || k}</b> {n}</li>)}
              </ul>
            </section>
            <section className="v2-card">
              <h3>계산·대조 빌드</h3>
              <ul className="v2-verify-list">
                {Object.entries(d.builds).map(([k, b]) => (
                  <li key={k}><b>{k}</b> {b ? `${b.build_id} · 규칙 ${b.calc_rule} · ${fmtKst(b.loaded_at)}` : '없음'}</li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  )
}

export default DataQuality
