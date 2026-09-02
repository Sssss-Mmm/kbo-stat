// RAG 질의응답 페이지 (FR-09).
// 자연어 질문을 /api/rag/ask 에 보내고, 답변과 "그 답변이 실제로 어떤 CSV 행에
// 근거하는지"를 나란히 보여준다. 백엔드 RAG 는 LLM 이 아니라 CSV 규칙 기반이라
// 답변 자체는 결정적이지만, 검색된 근거와 답변 주체가 어긋날 수 있다.
// 그래서 AC2 를 위해 (1) 근거를 표로 펼치고 (2) 답변 주체와 일치하는 근거를 표시하고
// (3) 근거가 하나도 없으면 그 사실을 경고한다.
import { useState, useMemo } from 'react'
import axios from 'axios'
import { MiniTable, TeamCell } from '../components/MiniTable'
import { fmtRate, fmtTwo, fmtInt } from '../lib/format'
import SeasonBanner from '../components/SeasonBanner'
import '../styles/Home.css'
import '../styles/Ask.css'

// 클릭 한 번으로 던져볼 수 있는 예시 질문. 백엔드가 분기하는 세 의도(팀/최근/MVP)에 대응한다.
const SAMPLES = ['왜 한화가 강하지?', '삼성 홈 성적은?', '최근 가장 뜨거운 팀은?', 'MVP는 누구야?']

function Ask({ seasonInfo }) {
  const [season] = useState(seasonInfo.dataSeason)
  const [question, setQuestion] = useState('')
  const [res, setRes] = useState(null)      // 성공 응답 전체
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)  // AC3: 실패 사유 문자열

  const ask = async (q) => {
    const text = (q ?? question).trim()
    if (!text || loading) return
    setQuestion(text)
    setLoading(true)
    setError(null)
    try {
      const r = await axios.post('/api/rag/ask', { question: text, season })
      if (r.data?.status !== 'success') throw new Error('서버가 실패를 응답했습니다.')
      setRes(r.data)
    } catch (err) {
      // 응답을 못 받았거나 status 가 success 가 아니면 이전 답변을 지운다.
      // 낡은 답변이 새 질문의 답처럼 보이면 안 된다.
      setRes(null)
      setError(err.response ? `요청 실패 (HTTP ${err.response.status})` : '서버에 연결하지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  // 근거를 유형별로 가른다. 팀/타자는 지표가 달라 한 표에 못 담는다.
  const teamRows = useMemo(
    () => (res?.evidence || []).filter((e) => e.payload?.type === 'team'),
    [res],
  )
  const hitterRows = useMemo(
    () => (res?.evidence || []).filter((e) => e.payload?.type === 'hitter'),
    [res],
  )

  // AC2: 답변이 지목한 대상(팀·선수)이 근거 목록에 실제로 있는지 확인한다.
  // 백엔드는 검색 점수 순으로만 근거를 주기 때문에, 답변 주체가 8번째에 묻혀 있거나
  // 아예 빠져 있을 수 있다. 답변 제목에 이름이 포함되면 "답변 근거"로 표시한다.
  const answerText = res ? `${res.answer?.title || ''} ${res.answer?.summary || ''}` : ''
  const isCited = (name) => Boolean(name) && answerText.includes(name)
  // 표에 실제로 배지가 붙는 조건과 같아야 한다. 타자 행은 소속팀이 아니라 선수명으로만 판정한다
  // (답변이 '삼성'을 말했다고 삼성 타자 8명이 근거가 되는 건 아니다).
  const citedCount = (res?.evidence || []).filter((e) =>
    e.payload?.type === 'hitter' ? isCited(e.payload.player) : isCited(e.payload?.team),
  ).length

  const sources = res?.data_sources || {}
  const sourceTotal = Object.values(sources).reduce((a, b) => a + b, 0)

  return (
    <div className="ask-container">
      <SeasonBanner info={seasonInfo} selected={season} note="수집된 CSV 데이터에만 근거해 답합니다" />

      <div className="ask-header">
        <h2>{season}시즌 데이터 질의응답</h2>
        <p>순위·경기·타자 지표 CSV를 검색해 답합니다. 답변 아래에 사용된 데이터가 함께 표시됩니다.</p>
      </div>

      <form
        className="ask-form"
        onSubmit={(e) => { e.preventDefault(); ask() }}
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="예: 왜 한화가 강하지?"
          aria-label="질문"
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? '검색중...' : '질문하기'}
        </button>
      </form>

      <div className="ask-samples">
        {SAMPLES.map((s) => (
          <button key={s} type="button" onClick={() => ask(s)} disabled={loading}>{s}</button>
        ))}
      </div>

      {loading && <p className="loading">데이터를 검색하고 답변을 만드는 중입니다...</p>}
      {/* AC3: 실패를 화면에 명시한다. */}
      {error && <p className="error">답변에 실패했습니다 — {error}</p>}
      {!loading && !error && !res && <p className="empty">질문을 입력하면 답변과 근거 데이터가 표시됩니다.</p>}

      {!loading && res && (
        <>
          <section className="panel ask-answer">
            <div className="panel-head">
              <h3>답변</h3>
              <p>질문: {res.question}</p>
            </div>
            <p className="ask-title">{res.answer?.title}</p>
            {res.answer?.summary && <p className="ask-summary">{res.answer.summary}</p>}
            {res.answer?.bullets?.length > 0 && (
              <ul className="ask-bullets">
                {res.answer.bullets.map((b, i) => <li key={i}>{b}</li>)}
              </ul>
            )}
            {/* AC2: 근거 없는 단정을 그대로 두지 않는다.
                근거 0건 자체는 백엔드가 답변에서 밝히고 아래 근거 섹션도 비었다고 알리므로
                여기서 또 경고하지 않는다. 남은 건 "근거는 있는데 답변 주체가 그 안에 없는" 경우다. */}
            {res.evidence?.length > 0 && citedCount === 0 && (
              <p className="ask-warn">
                답변이 지목한 대상이 아래 근거 목록에 없습니다. 질문과 답변의 초점이 어긋났을 수 있으니 수치를 직접 확인하세요.
              </p>
            )}
          </section>

          <section className="panel">
            <div className="panel-head">
              <h3>근거 데이터</h3>
              <p>
                {sourceTotal > 0
                  ? `${season}시즌 CSV ${fmtInt(sourceTotal)}행에서 검색 · 순위 ${sources.standings}, 경기 ${sources.team_games}, 타자 ${sources.hitters}`
                  : `${season}시즌 CSV가 없습니다`}
              </p>
            </div>

            {!res.evidence?.length && (
              <p className="empty">검색된 근거 문서가 없습니다.</p>
            )}

            {teamRows.length > 0 && (
              <div className="ask-evidence">
                <h4>팀 순위 · 득실 <span>출처: {teamRows[0].source}</span></h4>
                <div className="ask-scroll">
                  <MiniTable
                    columns={[
                      {
                        key: 'team', label: '팀', left: true,
                        render: (r) => (
                          <span className="ask-cited-cell">
                            <TeamCell team={r.payload.team} />
                            {isCited(r.payload.team) && <em className="ask-cited">답변 근거</em>}
                          </span>
                        ),
                      },
                      { key: 'rank', label: '순위', render: (r) => fmtInt(r.payload.rank) },
                      { key: 'wl', label: '승-무-패', render: (r) => `${fmtInt(r.payload.wins)}-${fmtInt(r.payload.draws)}-${fmtInt(r.payload.losses)}` },
                      { key: 'win_rate', label: '승률', render: (r) => fmtRate(r.payload.win_rate) },
                      { key: 'recent', label: '최근10', render: (r) => r.payload.recent || '-' },
                      { key: 'streak', label: '연속', render: (r) => r.payload.streak || '-' },
                      { key: 'runs', label: '득-실', render: (r) => `${fmtInt(r.payload.runs_for)}-${fmtInt(r.payload.runs_against)}` },
                      {
                        key: 'run_diff', label: '득실차',
                        render: (r) => (
                          <b className={r.payload.run_diff >= 0 ? 'pos' : 'neg'}>
                            {r.payload.run_diff > 0 ? '+' : ''}{fmtInt(r.payload.run_diff)}
                          </b>
                        ),
                      },
                      { key: 'score', label: '검색점수', render: (r) => fmtInt(r.score) },
                    ]}
                    rows={teamRows}
                  />
                </div>
              </div>
            )}

            {hitterRows.length > 0 && (
              <div className="ask-evidence">
                <h4>타자 지표 <span>출처: {hitterRows[0].source}</span></h4>
                <div className="ask-scroll">
                  <MiniTable
                    columns={[
                      {
                        key: 'player', label: '선수', left: true,
                        render: (r) => (
                          <span className="ask-cited-cell">
                            <b>{r.payload.player}</b>
                            {isCited(r.payload.player) && <em className="ask-cited">답변 근거</em>}
                          </span>
                        ),
                      },
                      { key: 'team', label: '팀', left: true, render: (r) => <TeamCell team={r.payload.team} /> },
                      { key: 'war_proxy', label: 'WAR*', render: (r) => fmtTwo(r.payload.war_proxy) },
                      { key: 'ops', label: 'OPS', render: (r) => fmtRate(r.payload.ops) },
                      { key: 'avg', label: 'AVG', render: (r) => fmtRate(r.payload.avg) },
                      { key: 'hr', label: 'HR', render: (r) => fmtInt(r.payload.hr) },
                      { key: 'rbi', label: 'RBI', render: (r) => fmtInt(r.payload.rbi) },
                      { key: 'score', label: '검색점수', render: (r) => fmtInt(r.score) },
                    ]}
                    rows={hitterRows}
                  />
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default Ask
