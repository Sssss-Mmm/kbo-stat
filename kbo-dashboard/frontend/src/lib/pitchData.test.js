// 투구 분석 지표 명칭·데이터 범위 문구 점검. `node src/lib/pitchData.test.js` 로 실행.
import assert from 'node:assert/strict'
import { HIT_RATE_NOTE, COVERAGE_UNKNOWN, hitRateLabel, coverageText, analysisKey, staleText } from './pitchData.js'

// 지표 명칭: Hits/InPlay 는 '타율'이 아니다.
assert.equal(hitRateLabel('batter'), '인플레이 안타율')
assert.equal(hitRateLabel('pitcher'), '피인플레이 안타율')
assert.equal(HIT_RATE_NOTE, '인플레이 타구 중 안타 비율(삼진·볼넷 제외, 홈런 포함). 공식 타율 및 BABIP와 다른 지표입니다.')

// 2026-10-26 /api/pitch-coverage?season=2026 응답(로컬 원본 기준).
const COV_2026 = { season: 2026, first_date: '2026-03-28', last_date: '2026-09-24', games: 663, regular_games: 663, regular_total: 720, rate: 0.9208, unscheduled_games: 0, other_games: 0 }
assert.equal(coverageText(COV_2026), '투구 데이터: 2026.03.28~09.24 · 663/720경기(92.1%)')

// 2025 는 포스트시즌 16경기가 원본에 섞여 있다 — 수집률은 정규시즌만, 나머지는 따로 밝힌다.
const COV_2025 = { season: 2025, first_date: '2025-03-22', last_date: '2025-10-31', games: 736, regular_games: 720, regular_total: 720, rate: 1, unscheduled_games: 0, other_games: 16 }
assert.equal(coverageText(COV_2025), '투구 데이터: 2025.03.22~10.31 · 720/720경기(100.0%) · 정규시즌 외 16경기 포함')

// 일정 CSV 가 늦어 일정에 없는 정규시즌 ID 는 '정규시즌 외'와 따로 밝힌다.
assert.equal(coverageText({ ...COV_2026, games: 665, regular_total: 700, unscheduled_games: 2 }),
  '투구 데이터: 2026.03.28~09.24 · 663/700경기(94.7%) · 일정 미반영 2경기 포함')

// 정규시즌 일정이 없으면 수집률 없이 경기 수만.
assert.equal(coverageText({ ...COV_2026, regular_games: null, regular_total: null, rate: null, other_games: null }),
  '투구 데이터: 2026.03.28~09.24 · 663경기')
assert.equal(coverageText({ ...COV_2026, regular_games: 0, regular_total: 0 }), '투구 데이터: 2026.03.28~09.24 · 663경기')

// 해를 넘기는 범위는 끝 연도를 남긴다.
assert.equal(coverageText({ ...COV_2026, last_date: '2027-01-02', regular_total: null }), '투구 데이터: 2026.03.28~2027.01.02 · 663경기')

// 원본 없음(API data=null)·API 실패·메타 불완전 → '확인 불가'. 숨기지 않는다.
assert.equal(COVERAGE_UNKNOWN, '투구 데이터 범위 확인 불가')
for (const bad of [null, undefined, {}, { ...COV_2026, first_date: null }, { ...COV_2026, last_date: '' }, { ...COV_2026, games: null }]) {
  assert.equal(coverageText(bad), COVERAGE_UNKNOWN)
}

// 분석 CSV 가 원본보다 오래됐을 때: 표시 중인 범위 + 갱신 필요, 원본 줄은 '투구 원본'.
assert.equal(coverageText(COV_2026, '투구 원본'), '투구 원본: 2026.03.28~09.24 · 663/720경기(92.1%)')
assert.equal(staleText({ first_date: '2026-03-28', last_date: '2026-09-20', days: 140, stale: true }),
  '표시 중인 분석 데이터: 2026.03.28~09.20(140일) · 분석 데이터 갱신 필요')
assert.equal(staleText({ pitches: 200000, raw_pitches: 204072, stale: true }),
  '표시 중인 분석 데이터: 200,000구(원본 204,072구) · 분석 데이터 갱신 필요')
assert.equal(staleText(null), '표시할 분석 데이터 없음 · 분석 데이터 갱신 필요')
for (const ok of [undefined, { first_date: '2026-03-28', last_date: '2026-09-24', days: 143, stale: false }]) {
  assert.equal(staleText(ok), null)
}

// 탭·역할 → 실제로 읽는 분석 CSV.
assert.equal(analysisKey('zone', 'batter'), 'batter_zones')
assert.equal(analysisKey('zone', 'pitcher'), 'pitcher_zones')
assert.equal(analysisKey('arsenal', 'pitcher'), 'pitcher_arsenal')
assert.equal(analysisKey('arsenal', 'batter'), 'batter_vs_pitch')
assert.equal(analysisKey('count', 'pitcher'), 'count_baseball')

console.log('pitchData.test ok')
