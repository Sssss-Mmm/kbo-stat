// 볼카운트 야구 파생 계산. 버킷 이름·정의는 빌더(src/build_count_metrics.py)와 1:1이다.
// 응답 한 행 = (Scope, 선수, 버킷). Scope='리그' 행에는 12칸 매트릭스(0-0~3-2)가
// 함께 들어 있고, Scope='선수' 행에는 이름 붙인 버킷만 있다.
//
// 한 행에 낟알(grain)이 둘 섞여 있다 — 분모를 잘못 잡으면 조용히 틀린다.
//   투구 단위: Pitches/Swings/Fouls  → 그 카운트에서 던져진 공
//   타석 단위: PA/K/OnBase           → 그 카운트를 한 번이라도 거친 타석
// 그래서 표본 하한도 둘로 나눈다.

// 목록 필터의 폴백 하한(규정충족 플래그가 없는 시즌에만 기준이 된다) + 초구 스윙률 분포 하한.
export const MIN_PA = 50 // 타석 50 미만은 숨긴다(초구 스윙률 100%가 5타석일 수 있다).
export const MIN_BUCKET_PA = 20 // 타석 단위 지표 분모 하한
export const MIN_BUCKET_PITCHES = 30 // 투구 단위 지표 분모 하한

// [버킷, 설명]. 투수유리 ⊂ 2S 라 버킷은 서로 배타가 아니다(세로 합 != 전체).
export const BUCKETS = [
  ['전체', '모든 타석'],
  ['초구', '0-0'],
  ['2S', '2스트라이크'],
  ['투수유리', '0-2 · 1-2'],
  ['타자유리', '2-0 · 3-0 · 3-1'],
]

export const BALLS = [0, 1, 2, 3]
export const STRIKES = [0, 1, 2]

// 응답을 리그/선수로 가른다. 커버리지는 행마다 같은 값이라 첫 행에서 읽는다.
export function indexRows(rows) {
  const league = {}
  const byId = new Map()
  for (const r of rows) {
    if (r.Scope === '리그') {
      league[r.Bucket] = r
      continue
    }
    if (!byId.has(r.PlayerId)) {
      byId.set(r.PlayerId, {
        id: r.PlayerId, name: r.Player, team: r.Team, side: r.Side, pa: 0, buckets: {},
        // 규정충족은 PlayerId 로 조인돼 행마다 같은 값이다. 없는 시즌은 null(= 알 수 없음).
        qualified: r['규정충족'] ?? null,
      })
    }
    const p = byId.get(r.PlayerId)
    p.buckets[r.Bucket] = r
    if (r.Bucket === '전체') p.pa = r.PA
  }
  const players = [...byId.values()].sort((a, b) => b.pa - a.pa)
  return { league, players, coverage: rows[0] || null }
}

// 리그 12칸 매트릭스: 행 = 볼 0~3, 열 = 스트라이크 0~2. 없는 칸은 null.
export function matrixRows(league) {
  return BALLS.map((balls) => ({
    balls,
    cells: STRIKES.map((strikes) => league[`${balls}-${strikes}`] || null),
  }))
}

// 표본 하한. 분모가 모자라면 수치를 적지 않는다(0/0 을 .000 으로 찍지 않기 위해).
export const paEnough = (row) => !!row && row.PA >= MIN_BUCKET_PA
export const pitchEnough = (row) => !!row && row.Pitches >= MIN_BUCKET_PITCHES

// 선수 카드용 버킷 표. 리그 같은 버킷 행을 나란히 붙여 차이를 읽게 한다.
export function bucketTable(player, league) {
  return BUCKETS.map(([bucket, hint]) => ({
    bucket,
    hint,
    row: player?.buckets[bucket] || null,
    lg: league[bucket] || null,
  })).filter((r) => r.row)
}
