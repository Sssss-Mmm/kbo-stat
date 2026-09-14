export function conversationHistory(turns) {
  return turns.slice(-2).flatMap((turn) => [
    { role: 'user', content: turn.question.slice(0, 1000) },
    { role: 'assistant', content: `${turn.season}시즌. ${turn.answer?.title || ''} ${turn.answer?.summary || ''}`.slice(0, 1000) },
  ])
}
