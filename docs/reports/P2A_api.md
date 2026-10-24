# P2-A 보고서 — `/api/v2` 통계 API · P1-D 후속

작성: 2026-10-24 · 설계: `docs/P2_API_DESIGN.md` · 코드: `kbo-dashboard/backend/routers/v2.py`, `services/v2_service.py`

## 1. 구현 범위

| 엔드포인트 | 입력 검증 | 페이지·정렬 |
| --- | --- | --- |
| `GET /api/v2/games/{game_id}/box` | GameId 형식(`\d{8}[A-Z]{4}\d`), `as_of` 시간대 필수 | 팀·등판/타순 순 |
| `GET /api/v2/players/{player_id}/games` | season, role, date_from ≤ date_to | `limit` 1–200 · `offset` · `sort=date\|-date` |
| `GET /api/v2/players/{player_id}/season` | season, role, `through_date` | — |
| `GET /api/v2/leaders` | role·basis 별 허용 stat, `qualified` 는 투수·official 만 | `limit` 1–100 · `offset`, 동점 같은 순위 |
| `GET /api/v2/data-quality` | season | — |

- v1 라우터·`public` 테이블 미사용. `main.py` 에 라우터 1줄. DB 끊김 503(기존 처리), v2 스키마 없음 503, 없는 경기·선수 404, 입력 오류 422.
- 외부 기록(`official`, 출처 `naver_boxscore` = KBO 공식 기록의 2차 출처)과 자체 계산(`calc`)을 별도 객체로. 미확정 계산값은 null.
- 모든 응답 `meta`: 출처·원본 수·수집 시각 범위·계산 빌드(`build_id`·`calc_rule`·`loaded_at`)·수집 정책·`kbo_direct_verification`.
- `kbo_verified`: KBO 원본(source `kbo*`)이 0건이라 모든 행 `kbo.status = not_checked`, data-quality `kbo_verified = 0`.
- 이닝은 정수 아웃으로 계산하고 표기(`ip_from_outs`, 17 → "5 2/3")만 바꾼다. ERA = 자책×27/아웃, WHIP = (안타+볼넷)×3/아웃, 타율 = 안타/타수 — 분모 0 이면 null.

## 2. 시점 정책

- `as_of`: 시스템이 실제로 확보한 시각. 외부 기록은 `fetched_at ≤ as_of` 인 경기별 최신 원본, 계산·대조는 `loaded_at ≤ as_of` 인 최신 빌드.
  그 시점에 그 경기·선수에 대한 원본·빌드가 하나도 없으면 **404** — 2026 에 백필한 2025 기록을 2025 시점에 있던 것처럼 보이지 않는다.
- `through_date`: 경기 날짜 기준 집계(`ref.game.game_date ≤ through_date`).
- 대조·예외 빌드는 **보여 주는 계산 빌드와 연결된 것만** 쓴다(`derived.build.basis_build_id`, 적재 때 기록).
- 한계: `ref.game`·`ref.player` 는 버전이 없다. 데이터가 있던 시점이면 경기 메타·선수 이름은 현재 값으로 나온다. 예측용 과거 재구성은 별도 기능.

## 3. 집계 기준·자격

- 시즌 합계(official): 경기별 최신 원본의 줄 합. `team_sum_mismatch_games` 로 원본 팀 합계가 어긋난 경기 수를 항목별로 표시.
- 시즌 합계(calc): 한 경기라도 아웃 미확정이면 `totals.outs = null`, 확정분 합은 `outs_lower_bound`. 결과 불명 타석이 있으면 `stats_exact=false` 이고 타율 null.
- 리더보드: official 은 경기별 외부 기록 합, calc 는 확정값(`stats_exact` 이고 아웃 확정)만 순위 — 나머지는 `excluded_not_exact` 로 센다.
  원본 팀 합계가 어긋난 항목(비율은 분자·분모)은 순위에서 빼고 `excluded_team_sum_mismatch` 로 센다.
  `qualified=true` = 아웃 ≥ 3 × 팀 완료 경기 수(KBO 규정이닝, 팀 = 가장 최근 경기 팀). 타자 규정타석은 외부 기록에 타석 수가 없어 지원하지 않는다(422, `min_ab` 사용).

## 4. 응답 형식 예시 (키 구조는 실제 응답 그대로, 값·선수는 가상)

공개 문서에는 수집 기록을 옮기지 않는다 — 아래 선수·수치는 지어낸 값이다. 실데이터 확인은 통합 테스트(`tests/test_v2_pg.py`)로 한다.

`GET /api/v2/games/{game_id}/box` (콜드게임 예)
```json
{"game": {"game_id": "20250101AAAA0", "date": "2025-01-01", "away": "원정팀", "home": "홈팀", "score": {"away": 6, "home": 5}},
 "official": {"source": "naver_boxscore", "fetched_at": "2026-10-23T00:00:00+00:00", "raw_file": "2025/20250101AAAA0/…json"},
 "pitchers": [{"player_id": 90001, "name": "투수A", "side": "away",
   "official": {"ip": "1 ⅓", "outs": 4, "bf": 5, "h": 2, "so": 1, "decision": "승", "ip_from_outs": "1 1/3"},
   "calc": {"outs": 4, "outs_complete": true, "bf": 5, "stats_complete": true},
   "verification": {"Outs": "observed_naver_match", "BF": "observed_naver_match"}, "kbo": {"status": "not_checked"}},
  {"player_id": 90002, "name": "투수B", "official": {"outs": 3}, "calc": {"outs": null, "outs_complete": false},
   "verification": {"Outs": "naver_conflict"}}],
 "exceptions": [{"kind": "called_game"}]}
```

`GET /api/v2/players/{player_id}/season?season=2025&role=pitcher`
```json
{"official": {"source": "naver_boxscore", "games": 20,
  "totals": {"outs": 300, "bf": 420, "h": 90, "bb": 30, "so": 110, "er": 40, "ip_from_outs": "100"},
  "rates": {"era": 3.6, "whip": 1.2}, "team_sum_mismatch_games": {}},
 "calc": {"games": 20, "stats_exact": true, "totals": {"outs": 300, "so": 110}, "outs_lower_bound": 300},
 "verification": {"Outs": {"observed_naver_match": 20}}, "kbo": {"status": "not_checked"}}
```
— 실데이터에서 경기별 박스스코어 합이 네이버 시즌 누적 값과 일치함을 통합 테스트로 확인했다.

`GET /api/v2/leaders?season=2025&role=pitcher&stat=era&qualified=true&limit=3`
```json
{"leaders": [{"rank": 1, "player_id": 90001, "name": "투수A", "team": "팀A", "value": 1.90},
             {"rank": 2, "player_id": 90002, "name": "투수B", "team": "팀B", "value": 2.25},
             {"rank": 2, "player_id": 90003, "name": "투수C", "team": "팀C", "value": 2.25}],
 "criteria": {"basis": "official", "order": "asc", "qualified": true,
              "qualification_rule": "outs >= 3 x team final games (ref.game)", "excluded_team_sum_mismatch": 0}}
```

`GET /api/v2/players/{player_id}/season?season=2025&as_of=2025-10-31T23:59:59+09:00` → **404** (그 시점엔 확보한 기록이 없었다)

`GET /api/v2/data-quality?season=2025`
```json
{"coverage": {"final_games": 720, "official_raw_games": 720, "calc_games": 720},
 "collection": {"policy": {"kbo_official_site": "disabled_pending_approval", "naver_sports": "paused_pending_terms_review"},
                "fetch_log": {"saved": 720, "skipped_existing": 84}},
 "outs_uncertain": {"naver_verified": 131, "naver_conflict": 49}, "kbo_verified": 0}
```

## 5. 성능 (2025 · 원본 720 · 타자 줄 18,506 · 투수 줄 7,026, TestClient 5회 중앙값)

| 엔드포인트 | 중앙값 |
| --- | --- |
| box | 15 ms |
| players/games | 22 ms |
| players/season | 31 ms |
| leaders (official 타자 avg) | 109 ms (DB 31 ms) |
| leaders (qualified era) | 53 ms |
| leaders (calc) | 15 ms |
| data-quality | 44 ms |

EXPLAIN: 선수 조회는 기본키 인덱스(`game_*_line_pkey`) 사용, 리더보드는 18,506행 Seq Scan(약 1 ms). **인덱스를 추가하지 않았다.**
여러 시즌을 적재해 줄 수가 수십만이 되면 `official.game_*_line(player_id)`·`(game_id)` 를 다시 본다.

## 6. P1-D 후속

| 항목 | 결과 |
| --- | --- |
| 네이버 자동 수집 | `src/naver_access.py`(공통 `fetch_guard.py`). 투구·박스스코어·선수 시즌 크롤러가 이 스위치를 거친다. 일일 스크립트·`update_daily --pitch-zones`·박스스코어 백필 진입점은 요청 없이 건너뛴다 |
| 차단 범위 | 모든 HTTP 메서드(get/post/put/patch/delete/head/options/request)·`Session.request`/`send`. `requests.api` 같은 우회 이름은 막는다 |
| Docker 사전 점검 | `update_kbo_daily.sh` DB 단계 앞: compose 플러그인(stdout 문구)·데몬 확인, 없으면 exit 5 |
| 재시작 정책 | `postgres`·`backend` 에 `restart: unless-stopped`. 다음 `compose up` 에서 두 컨테이너가 **재생성**된다(아래 7절에서 실제로 일어남) |
| DB 비밀번호 | 출력·수정 안 함 |
| KBO 수동 검증 양식 | `docs/KBO_MANUAL_VERIFICATION.md`, `docs/templates/kbo_manual_check.csv` |
| 데이터 이용 문의 초안 | `docs/drafts/kbo_data_use_inquiry.md` (KBO·스포츠투아이, 발송 안 함) |
| 박스스코어 수집 보강 | 진행 중 경기(statusCode≠4) 저장 안 함, 손상된 최신 파일만 있으면 다시 받음(손상 파일 보존) |

## 7. 운영 사건 — 02:00 일일 cron 이 컨테이너를 재생성하고 DB 를 다시 적재함

- 2026-10-24 02:00 KST 일일 cron(`update_kbo_daily.sh`)이 새 코드로 돌았다: KBO·네이버 단계는 의도대로 건너뜀.
- DB 단계에서 백엔드가 꺼져 있어 기존 로직대로 `docker compose up -d backend` 를 실행했고, **방금 추가한 재시작 정책 때문에
  `kbo_dashboard_db`·`kbo_backend` 가 재생성·기동됐다**(전에는 꺼진 백엔드만 켰을 것). DB 는 약 1초 내려갔다 올라왔고
  같은 순간 진행 중이던 v2 적재 1회가 연결 끊김으로 전체 롤백됐다(재실행 성공).
- 이어서 기존 `migrate.py` 가 `public` 테이블을 기존 CSV 로 다시 적재했다(정상 일일 동작 — DB 가 09-24 이후 갱신되지 않던 상태였다).
  예: hitters 1,924→1,926 · pitchers 1,021→1,022 · team_games 32,014→32,128 · schedule_games 17,246→17,257.
- 데이터 손실 없음(볼륨 유지, 신규 스키마 행 수 그대로, 적재 전 백업 `db-backup-before-p1.sql.gz` 보관).
- **현재 `kbo_backend` 가 떠 있다**(2026-09-22 이미지 — v1 API 만, v2 코드는 아직 이미지에 없다). 내가 직접 재시작한 것은 아니지만
  재시작 정책 변경이 이 재생성을 일으켰다. 계속 띄워 둘지·멈출지 결정이 필요하다.

## 8. 남은 위험

- `ref.game`·`ref.player` 무버전 — `as_of` 재현에서 경기 메타·이름은 현재 값.
- 계산 빌드 1개가 같은 내용으로 한 번 더 생겼다(빌드 해시에 기준 빌드 칸을 더하면서, 23,484행). 이력으로 두었고 이후 재실행은 그대로다.
- 일일 cron 은 계속 돈다(수집은 막혀 있고 가공·`public` 재적재만). 원하면 cron 자체를 멈추는 것도 결정 대상.
- v2 를 서비스하려면 백엔드 이미지 재빌드가 필요하다(승인 대상).

## 9. 검증

- 테스트: src 99개 · backend 80개(+ PostgreSQL 실데이터 통합 7개, `V2_PG_TESTS=1`) · 크롤러 자체 점검 통과.
- Codex(P1-D current 뷰 재검증 포함, 2사이클 6라운드):
  - 진행 중 경기 저장·손상 최신 파일 판정 → 수정 · 계산+규정이닝 조합·팀 합계 불일치 순위·손상 파일 건너뜀 → 수정
  - HTTP 메서드 우회·계산/대조 빌드 혼합·as_of 이전 경기/선수 노출 → 수정(`basis_build_id` 열 추가, as_of 404)
  - 시즌·시점 무관 KBO 원본 판정·as_of 의 현재 일정 수 → 수정 · 다른 출처 원본이 네이버 줄을 가림 → 수정(쿼리·뷰 출처 고정)
  - 마지막 라운드: "v2 적재가 일일 작업에 연결되지 않음" — **결정대로 의도된 상태**(일일 파이프라인 연결은 승인 전, 네이버 수집도 중단). 수정하지 않음.
