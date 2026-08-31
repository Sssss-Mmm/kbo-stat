// 화면 상단 시즌 표기 (FR-12 AC2 / DR-06 AC2). 순수 표시용.
// info: seasonState() 결과, selected: 페이지에서 사용자가 고른 시즌, note: 화면별 안내 문구.
function SeasonBanner({ info, selected, note }) {
  if (!info) return null
  // 사용자가 활성 시즌이 아닌 과거 시즌을 고르면 그 사실을 그대로 표기한다.
  const stale = selected != null && selected !== info.dataSeason
  const notice = stale ? '과거 시즌 기록' : [info.notice, note].filter(Boolean).join(' · ')
  return (
    <div className={`season-banner ${info.state}`}>
      <span className="sb-tag">{stale ? `${selected} 정규시즌 최종` : info.label}</span>
      {notice && <span className="sb-note">{notice}</span>}
    </div>
  )
}

export default SeasonBanner
