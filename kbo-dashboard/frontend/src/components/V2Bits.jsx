// /api/v2 화면 공용 조각: 검증 배지·출처 줄·시점 입력·미확정 값 표시·링크·조회 훅.
import { useEffect, useState } from 'react'
import { apiError } from '../lib/apiError'
import { followLink, pageUrl } from '../lib/navigation'
import { fetchSeasons, fmtKst, fmtStat, kboLabel, TIME_HELP, UNKNOWN, verificationInfo } from '../lib/v2'
import { ADVANCED_STATUS, fmtAdvanced } from '../lib/p2d'

/** 비동기 조회. deps 가 바뀌면 다시 부르고, 늦게 온 이전 응답은 버린다. */
export function useV2(fetcher, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, error: null, loading: true }))
    fetcher()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((err) => alive && setState({ data: null, error: apiError(err), loading: false, status: err?.response?.status }))
    return () => { alive = false }
  }, deps)  // 호출하는 쪽이 fetcher 가 쓰는 값을 deps 로 넘긴다
  return state
}

/** 로딩·오류 공통 표시. 아무것도 아니면 null. */
export function LoadState({ state, empty }) {
  if (state.loading) return <p className="loading">불러오는 중…</p>
  if (state.error) return <p className="v2-error" role="alert">{state.error}</p>
  if (empty) return <p className="v2-empty">{empty}</p>
  return null
}

/** 숫자 칸. null 은 '미확정' 으로(0 이 아니다). */
export function Stat({ value, rate = false, digits = null, unknown = UNKNOWN }) {
  const text = fmtStat(value, { rate, digits, unknown })
  return <span className={value === null || value === undefined ? 'v2-unknown' : undefined}>{text}</span>
}

export function VerificationBadge({ status }) {
  const info = verificationInfo(status)
  return <span className={`v2-badge v2-${info.tone}`} title={info.label}>{info.short}</span>
}

export function KboBadge({ kbo }) {
  const verified = kbo?.status === 'kbo_verified'
  return <span className={`v2-badge ${verified ? 'v2-ok' : 'v2-muted'}`} title="KBO 공식 사이트 원본과 직접 대조한 결과">{kboLabel(kbo)}</span>
}

export function SourceLine({ label, fetchedAt, extra }) {
  return (
    <p className="v2-source">
      <span className="v2-source-label">출처</span> {label}
      {fetchedAt && <> · 수집 {fmtKst(fetchedAt)}</>}
      {extra && <> · {extra}</>}
    </p>
  )
}

export function PlayerLink({ id, name, season, role }) {
  return <a href={pageUrl('player', { id, season, role })} onClick={followLink}>{name || id}</a>
}

export function GameLink({ id, children }) {
  return <a href={pageUrl('game', { id })} onClick={followLink}>{children || id}</a>
}

/**
 * 시점 입력: as_of(데이터 확보 시점)과 through_date(경기 날짜 기준)를 따로 받고 뜻을 함께 보여 준다.
 * asOfInput 은 datetime-local 값(KST), throughDate 는 YYYY-MM-DD.
 */
export function TimeControls({ asOfInput, throughDate, onChange, showThrough = true }) {
  return (
    <details className="v2-time">
      <summary>기준 시점 {asOfInput || throughDate ? '(적용 중)' : ''}</summary>
      <div className="v2-time-grid">
        {showThrough && (
          <label>
            <span>경기 날짜 기준 (through_date)</span>
            <input type="date" value={throughDate || ''} onChange={(e) => onChange({ through: e.target.value })} />
            <small>{TIME_HELP.throughDate}</small>
          </label>
        )}
        <label>
          <span>데이터 확보 시점 (as_of, KST)</span>
          <input type="datetime-local" value={asOfInput || ''} onChange={(e) => onChange({ asof: e.target.value })} />
          <small>{TIME_HELP.asOf}</small>
        </label>
      </div>
    </details>
  )
}

/** 모든 화면 위 '자료 기준' 줄: 수집이 멈춰 있으므로 실시간·오늘 기준이 아님을 늘 보여 준다. 조회 실패면 그 사실만. */
export function DataBasisBar() {
  const state = useV2(fetchSeasons, [])
  if (state.loading) return null
  const meta = state.data?.meta
  const latest = state.data?.data?.at(-1)
  if (!meta || !latest) return <p className="v2-basis" role="note">자료 기준 시점을 확인하지 못했습니다 — 표시 기록은 실시간 정보가 아닙니다.</p>
  return (
    <p className="v2-basis" role="note">
      자료 기준 <b>{fmtKst(meta.last_collected_at)}</b> 수집
      {latest.schedule?.last_played_date && <> · {latest.season} 마지막 경기 <b>{latest.schedule.last_played_date}</b></>}
      {' '}· 자동 수집 중단 — 실시간 정보가 아닙니다 · 포스트시즌 자료 없음
    </p>
  )
}

/** P3-A 타자 고급 지표 값 하나. 계산 불가·분모 0 은 '-'(0 으로 보이지 않게) + 사유, 출처 값은 '출처' 배지로 계산값과 구분. */
export function AdvancedValue({ metricKey, m, showNote = false }) {
  const f = fmtAdvanced(metricKey, m)
  const empty = f.text === '-'
  return (
    <span className={`p3a-adv p3a-${f.kind}`} title={f.note} aria-label={`${empty ? '값 없음' : f.text} — ${f.note}`}>
      {f.text}
      {f.kind === 'source' && <span className="v2-badge v2-info p3a-src">출처</span>}
      {showNote && empty && <small className="p3a-note">{f.note}</small>}
    </span>
  )
}

/** 고급 지표 표 아래 범례. */
export function AdvancedLegend() {
  return (
    <p className="v2-note p3a-legend">
      고급 지표: 숫자 = {ADVANCED_STATUS.calculated}(개수로 직접 계산) · <span className="v2-badge v2-info">출처</span> = {ADVANCED_STATUS.source}
      {' '}· '-' = 계산 불가 또는 분모 0(사유는 값에 표시·툴팁). 계산할 수 없는 값은 0 으로 표시하지 않습니다.
      {' '}ISO 는 자체 계산값이라 출처(네이버) ISO 와 0.001 다를 수 있습니다 — 출처는 반올림한 장타율에서 반올림한 타율을 빼서 계산합니다.
    </p>
  )
}
