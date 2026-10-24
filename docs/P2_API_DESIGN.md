# P2 API 설계안 — `/api/v2` (구현 전, 승인 대기)

작성: 2026-10-24 · 근거 데이터: P1-A~C 로 적재한 PostgreSQL `ref`·`ingest`·`official`·`derived`·`verify` (2025 720경기)

## 0. 원칙

1. **v1 은 그대로 둔다.** 새 라우터 `routers/v2.py` 하나를 `/api/v2` 로 추가한다. `public` 테이블을 읽지 않는다.
2. **출처·수집 시각·검증 상태를 값과 함께 돌려준다.** 외부 기록(`official`)과 자체 계산(`derived`)은 한 객체에 섞지 않는다.
3. **`kbo_verified` 는 KBO 원본으로 직접 대조한 행에만 붙는다.** 현재 KBO 원본은 0건이라 모든 응답에서
   `kbo.status = "not_checked"` 이다. 네이버 대조 결과는 `naver_*` 상태로만 표현한다.
4. **확정되지 않은 값은 비운다.** `derived.outs` 가 NULL 이면 그대로 null — 외부 값으로 채우지 않는다.
5. **시점 조회(`as_of`)** 를 모든 엔드포인트가 받는다: 외부 기록은 `fetched_at <= as_of` 중 최신 원본,
   계산·대조는 `derived.build.loaded_at <= as_of` 중 최신 빌드. 생략하면 `*_current` 뷰.

## 1. 공통 응답 형식

아래 JSON 의 선수·숫자는 형식을 보이기 위한 가상 예시다(공개 문서에 수집 기록을 옮기지 않는다).

```json
{
  "data": { },
  "meta": {
    "season": 2025,
    "as_of": null,
    "generated_at": "2026-10-24T03:00:00Z",
    "sources": [
      {"source": "naver_boxscore", "kind": "official_secondary",
       "note": "KBO 공식 기록의 2차 출처(네이버). KBO 원본 직접 검증 아님",
       "fetched_at_min": "...", "fetched_at_max": "..."},
      {"source": "pitch_relay", "kind": "calc_input", "calc_rule": "…", "build_id": "…"}
    ],
    "kbo_direct_verification": "not_available"
  }
}
```

검증 상태 어휘(그대로 노출):

| 상태 | 뜻 |
| --- | --- |
| `observed_naver_match` / `observed_naver_conflict` | 투구 데이터로 입증된 계산값이 네이버와 같음 / 다름 |
| `naver_verified` / `naver_conflict` | 입증 못 한 계산값이 네이버와 같음 / 다름(계산값은 여전히 미확정) |
| `naver_unusable` | 원본 팀 합계 불일치로 그 항목의 네이버 값을 기준으로 안 씀 |
| `calc_missing` / `naver_missing` | 한쪽에만 있음 |
| `unverified` | 대조할 외부 기록 없음 |
| `kbo_verified` | (예약) KBO 원본 직접 대조 일치 — 현재 발급 0건 |

## 2. 엔드포인트

### 2.1 `GET /api/v2/games/{game_id}/box`

- 입력: `game_id`(KBO 13자, 예 `20250719HHKT0`) · `as_of`(선택)
- 데이터: `ref.game` + `official.game_{pitcher,batter}_line(_current)` + `derived.player_game(_current)` +
  `verify.player_game_check(_current)` + `verify.exception(_current)`(그 경기)
- 응답 `data`:

```json
{
  "game": {"game_id": "...", "date": "2025-07-19", "dh": 0, "away": "한화", "home": "KT",
           "score": {"away": 6, "home": 5}, "status": "final",
           "flags": ["called_game"]},
  "official": {"source": "naver_boxscore", "fetched_at": "...", "raw_file": "...", "sha256": "...",
               "team_sum_mismatch": {"home": "", "away": ""}},
  "pitchers": [
    {"player_id": 90001, "name": "투수A", "side": "home",
     "official": {"ip": "1", "outs": 3, "bf": 5, "h": 1, "bb": 1, "bbhp": 1, "so": 0, "r": 0, "er": 0, "np": 24, "decision": ""},
     "calc": {"outs": null, "outs_complete": false, "...": "..."},
     "verification": {"Outs": "naver_conflict", "...": "..."},
     "kbo": {"status": "not_checked"}}
  ],
  "batters": [ { "...": "같은 구조" } ],
  "exceptions": [{"kind": "called_game", "detail": "home_pitching_outs=16 away_pitching_outs=15"}]
}
```

- 404: `ref.game` 에 없음. 박스스코어 원본이 없으면 `official: null`, 상태 `unverified`.

### 2.2 `GET /api/v2/players/{player_id}/games`

- 입력: `season`(필수) · `role`=`batter|pitcher`(선택) · `from`/`to`(날짜) · `as_of` · `limit`(≤200)/`cursor`
- 데이터: 위와 같은 테이블을 `player_id` 로 거른다.
- 응답 `data.games[]`: 2.1 의 선수 행 + `game_id`·`date`·`opponent`·`home_away`. `data.player` 는 `ref.player` +
  `ref.player_name` 이력.

### 2.3 `GET /api/v2/players/{player_id}/season`

- 입력: `season` · `role` · `as_of`
- 응답 `data`:

```json
{
  "official": {"source": "naver_boxscore", "games": 41, "games_missing_official": 0,
               "totals": {"outs": 512, "ip": "170 2/3", "bf": 700, "h": 150, "bb": 40, "so": 160}},
  "calc": {"calc_rule": "...", "games": 41, "games_outs_complete": 39,
           "totals": {"outs": 480}, "complete": false},
  "verification": {"Outs": {"observed_naver_match": 38, "naver_verified": 2, "naver_conflict": 1}},
  "kbo": {"status": "not_checked"}
}
```

- 규칙: `official.totals` 는 경기별 외부 기록의 합(같은 출처), `calc.totals` 는 확정된 경기만 더하고
  `complete=false` 이면 하한임을 표시. 시즌 누적 공식 페이지 값(`kbo_naver_*`·KBO 리더보드 CSV)은 P2 범위에서 쓰지 않는다
  (덮어쓰기 저장이라 시점 보존이 안 됨 — P3).

### 2.4 `GET /api/v2/leaders`

- 입력: `season` · `role` · `stat`(예 `so`, `h`, `outs`, `hr`) · `basis`=`official`(기본)|`calc` · `min_games`·`min_outs`·`min_pa` ·
  `limit`(≤50) · `as_of`
- `basis=official`: 경기별 외부 기록 합으로 순위. `basis=calc`: 확정값만 — 미확정 경기가 있는 선수는 `complete=false` 표시.
- 응답: `data.leaders[] = {rank, player_id, name, team, value, games, coverage, complete}` · `meta` 에 기준 설명.

### 2.5 `GET /api/v2/data-quality`

- 입력: `season`
- 응답 `data`:

```json
{
  "coverage": {"final_games": 720, "official_raw": 720, "pitch_relay_games": 720},
  "collection": {"kbo_automated_fetch": "disabled_pending_approval",
                 "naver_last_fetched_at": "...", "fetch_log": {"saved": 720, "error": 0, "retry": 0}},
  "builds": [{"kind": "player_game", "build_id": "...", "calc_rule": "...", "loaded_at": "..."}],
  "verification": {"by_metric": {"pitcher.Outs": {"observed_naver_match": 6842, "observed_naver_conflict": 3}}},
  "outs_uncertain": {"naver_verified": 131, "naver_conflict": 49},
  "exceptions": {"auto_ibb_no_pitch": 122, "called_game": 7, "tie": 22, "walkoff": 37},
  "kbo_verified": 0
}
```

## 3. 구현 계획(승인 후)

| 단계 | 내용 | 검증 |
| --- | --- | --- |
| 1 | `routers/v2.py` + 조회 함수(SQLAlchemy Core, 읽기 전용 쿼리), `main.py` 에 라우터 1줄 | 기존 v1 테스트 그대로 통과 |
| 2 | `as_of` 해석 함수 1개(원본·빌드 선택) | 빌드 2개 픽스처로 과거/현재 응답 비교 테스트 |
| 3 | 응답 스키마 Pydantic 모델 | 상태 어휘 외 값·`kbo_verified` 자동 발급이 없음을 테스트 |
| 4 | 인덱스(`official.*(player_id)`, `derived.player_game(player_id, season)`) | 소규모 DDL — 별도 승인 |
| 5 | React 화면(경기 박스·선수 경기 기록·데이터 품질 배지) | P2 2차 |

DB 가 없으면 v2 는 503 을 돌려준다(v1 CSV 라우터처럼 조용히 빈 값을 주지 않는다).

## 4. 열린 질문

- 네이버 수집 지속 여부(이용약관 검토 결과에 따라 `official_secondary` 출처 자체가 바뀔 수 있다).
- KBO 수동 표본 검증 결과를 넣을 테이블(`verify.kbo_manual_check`: 확인자·시각·근거 URL/캡처)의 형태.
