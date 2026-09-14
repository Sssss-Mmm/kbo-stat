import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import SeasonBanner from '../components/SeasonBanner'
import { apiError } from '../lib/apiError'
import { conversationHistory } from '../lib/qa'
import '../styles/Home.css'
import '../styles/Ask.css'

const SAMPLES = ['삼성 요즘 왜 못해?', '삼성과 LG의 시즌 성적 비교해줘', '한화 홈 원정 차이는?', '규정 이닝 투수 ERA 순위는?']

function Ask({ seasonInfo }) {
  const season = seasonInfo.dataSeason
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState([])
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const pending = useRef(null)

  useEffect(() => {
    setTurns([])
    setRes(null)
    setError(null)
    setLoading(false)
    return () => { pending.current?.abort(); pending.current = null }
  }, [season])

  const ask = async (q) => {
    const text = (q ?? question).trim()
    if (!text || pending.current) return
    const controller = new AbortController()
    pending.current = controller
    setQuestion(text)
    setLoading(true)
    setError(null)
    setRes(null)
    try {
      const { data } = await axios.post('/api/rag/ask', {
        question: text, season, history: conversationHistory(turns),
      }, { timeout: 55000, signal: controller.signal })
      if (data?.status !== 'success') throw new Error('서버가 실패를 응답했습니다.')
      if (pending.current !== controller) return
      setRes(data)
      setTurns((previous) => [...previous, data].slice(-6))
      setQuestion('')
    } catch (err) {
      if (!controller.signal.aborted) setError(apiError(err))
    } finally {
      if (pending.current === controller) {
        pending.current = null
        setLoading(false)
      }
    }
  }

  const reset = () => { setTurns([]); setRes(null); setError(null); setQuestion('') }
  const previous = res ? turns.slice(0, -1) : turns

  return (
    <div className="ask-container">
      <SeasonBanner info={seasonInfo} selected={res?.season ?? season} note="수집된 기록을 계산하고 근거와 함께 설명합니다" />
      <div className="ask-header">
        <h2>기록으로 보는 야구</h2>
        <p>팀의 상승·하락, 기간별 변화, 선수 비교를 물어보세요. “그럼 LG랑 비교하면?”처럼 이어서 질문할 수 있습니다.</p>
      </div>
      {turns.length > 0 && <div className="ask-conversation-head">
        <span>이 대화의 최근 두 문답을 이어서 참고합니다.</span>
        <button type="button" onClick={reset} disabled={loading}>새 대화</button>
      </div>}
      {previous.length > 0 && <div className="ask-history">
        {previous.map((turn, index) => <details key={index}>
          <summary>{turn.question}</summary><p>{turn.answer?.title}</p><p>{turn.answer?.summary}</p>
        </details>)}
      </div>}
      <form className="ask-form" onSubmit={(event) => { event.preventDefault(); ask() }}>
        <input type="text" value={question} maxLength={2000} onChange={(event) => setQuestion(event.target.value)}
          placeholder={turns.length ? '이어서 궁금한 점을 물어보세요' : '예: 삼성은 득점이 많은데 왜 순위가 낮아?'} aria-label="질문" />
        <button type="submit" disabled={loading || !question.trim()}>{loading ? '분석 중…' : '질문하기'}</button>
      </form>
      <div className="ask-samples">
        {SAMPLES.map((sample) => <button key={sample} type="button" onClick={() => ask(sample)} disabled={loading}>{sample}</button>)}
      </div>
      <div aria-live="polite" aria-busy={loading}>
        {loading && <p className="loading">질문을 해석하고 기록을 비교하고 있습니다. 잠시만 기다려 주세요.</p>}
        {error && <p className="error">답변을 받지 못했습니다 — {error}</p>}
        {!loading && !error && !res && !turns.length && <p className="empty">어떤 차이가 궁금한가요? 팀·선수와 기간을 함께 적으면 더 구체적으로 분석할 수 있습니다.</p>}
        {res && <section className="panel ask-answer">
          <div className="panel-head"><h3>{res.mode === 'clarification' ? '확인이 필요해요' : '분석 결과'}</h3><p>{res.question}</p></div>
          {res.scope && <p className="ask-scope">{res.scope}</p>}
          {res.notice && <p className="players-note">{res.notice}</p>}
          <p className="ask-title">{res.answer?.title}</p>
          {res.answer?.summary && <p className="ask-summary">{res.answer.summary}</p>}
          {res.answer?.bullets?.length > 0 && <ul className="ask-bullets">
            {res.answer.bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}
          </ul>}
          {res.answer?.limitations?.length > 0 && <div className="ask-limits">
            <h4>해석할 때 함께 볼 점</h4>
            <ul>{res.answer.limitations.map((note, index) => <li key={index}>{note}</li>)}</ul>
          </div>}
          {res.answer?.followups?.length > 0 && <div className="ask-samples ask-followups">
            {res.answer.followups.map((followup) => <button type="button" key={followup} onClick={() => ask(followup)} disabled={loading}>{followup}</button>)}
          </div>}
        </section>}
      </div>
      {!!res?.evidence?.length && <section className="panel">
        <div className="panel-head"><h3>계산에 사용한 근거</h3><p>답변의 [E번호]와 연결됩니다. 기간과 표본을 확인할 수 있습니다.</p></div>
        <div className="ask-evidence-list">
          {res.evidence.map((item) => <details key={item.id}>
            <summary><span className="ask-cited">{item.id}</span> {item.title}</summary>
            <p>{item.body}</p><p className="players-note">출처: {item.source}</p>
          </details>)}
        </div>
      </section>}
    </div>
  )
}

export default Ask
