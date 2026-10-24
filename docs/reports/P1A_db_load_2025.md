# P1-A 데이터 품질 보고서 — PostgreSQL 영역 스키마와 2025 적재

작성: 2026-10-24 · 대상: 2025 정규시즌 · 외부 기록 출처: 네이버 박스스코어(`naver_boxscore`) 84경기(P0 백필분)

## 요약

| 항목 | 결과 |
| --- | --- |
| 새 스키마 | `ref` · `ingest` · `official` · `derived` · `verify` (11개 테이블 + 현재값 뷰 5개) |
| 기존 `public` 13개 테이블 | 읽기·쓰기 없음. 적재 전후 행 수 동일(teams 23 · hitters 1,924 · pitchers 1,021) |
| 재실행 안전성 | 같은 입력으로 3회 적재 → 11개 테이블 행 수 동일, 빌드 3개 그대로 |
| 원자성 | DDL 포함 한 트랜잭션. 실제 PostgreSQL 에서 강제 실패 시 스키마 5개 → 0개로 롤백 확인 |
| 원본 무결성 | 적재 전 84개 원본 JSON 해시 재계산 — 전부 일치 |
| 가공 CSV 대조 | 박스스코어 CSV 각 행의 해시·경기·시즌·출처·수집시각을 원본과 대조, 모든 입력 CSV 의 시즌 일치 검사 — 전부 통과 |
| 적재 전 백업 | `pg_dump` 770KB (세션 scratchpad, 커밋 안 함) |

## 적재 결과 (2025)

| 테이블 | 행 | 내용 |
| --- | --- | --- |
| `ref.game` | 720 | 일정 CSV 의 GameId 기준 경기 |
| `ref.player` | 577 | KBO playerId 기준 선수(= 네이버 pcode = 투구 데이터 ID) |
| `ref.player_name` | 1,044 | 출처별 이름 이력(`pitch_relay` · `naver_boxscore`) |
| `ingest.raw_record` | 84 | 박스스코어 응답 원본(JSONB, 451kB) · 수집시각 · sha256 |
| `ingest.fetch_log` | 84 | 수집 시도 이력(`ingest_log.csv`) |
| `official.game_pitcher_line` | 831 | 원본 1개 = 행 묶음, 불변 |
| `official.game_batter_line` | 2,173 | 〃 |
| `derived.build` | 3 | 산출물 빌드(종류별 1개, 계산 규칙 `01f58acf52bb`) |
| `derived.player_game` | 23,484 | 자체 계산, 빌드별 불변 |
| `verify.player_game_check` | 15,851 | 항목별 대조 결과 |
| `verify.outs_uncertain` | 144 | 아웃 미확정 투수-경기 |

## 대조 상태 (DB 기준, P0 와 동일)

| 상태 | 건수 |
| --- | --- |
| `observed_naver_match` | 13,703 |
| `calc_missing` (타석 없는 대수비·대주자 등) | 1,405 |
| `naver_verified` | 552 |
| `naver_conflict` | 135 |
| `observed_naver_conflict` (자동 고의4구) | 49 |
| `naver_unusable` (원본 팀 합계 불일치) | 7 |

아웃 미확정 144건: `naver_verified` 90 · `naver_conflict` 2 · `unverified` 52(박스스코어 미수집 경기 — P1-B 대상).
`kbo_verified` 는 아직 0건이다(KBO 공식 사이트 대조는 P1-C).

## 재실행·보존 규칙

- `ingest`·`official`: 불변. 같은 원본은 다시 넣지 않고(ON CONFLICT DO NOTHING), 다시 받은 원본은 새 행으로 쌓인다.
  `official.*_current` 뷰가 경기·선수별 가장 최근 원본만 보여 준다.
- `derived`·`verify`: 입력 CSV 한 벌 = 빌드(내용 해시, `CheckedAt` 제외). 행은 빌드별 불변이다 — 같은 CSV 는 같은 빌드라
  다시 넣지 않고, 입력·계산 규칙(`calc_rule`)·대조 원본 중 무엇이 바뀌어도 새 빌드가 쌓이며 옛 빌드(사라진 행 포함)가 남는다.
  `*_current` 뷰는 시즌별 가장 최근 적재 빌드만 보여 준다(Codex P1-A 리뷰 반영).
- `ref`: 경기 상태·선수 대표 이름은 최신 값으로 갱신, 이름 이력은 쌓는다.

## 예측용 시점 보존

- 외부 기록은 수집 시각(`fetched_at`)별로 남아 "그 시점에 알 수 있던 값"을 `fetched_at <= 기준시각` 으로 고를 수 있다.
- 계산·대조 결과는 빌드 단위로 처음 적재 시각(`derived.build.loaded_at`)이 남아, 기준시각 이전 마지막 빌드를 고를 수 있다.
- 한계: 시즌 누적 CSV(`kbo_naver_*`, `kbo_pitcher_*`)는 여전히 덮어쓰기라 시점 이력이 없다(P3).

## 운영 메모

- 적재는 일일 파이프라인과 같은 경로(백엔드 이미지·compose 환경변수)로, 현재 backend 폴더를 마운트한 일회성 컨테이너에서 실행했다:
  `docker compose -f kbo-dashboard/docker-compose.yml run --rm --no-deps -T -v "$PWD/kbo-dashboard/backend:/app/kbo-dashboard/backend" backend python migrate_records.py --season 2025`
- 호스트 `kbo-dashboard/backend/.env` 의 DB 비밀번호가 실제 DB 와 맞지 않는다(호스트에서 직접 접속 실패). 비밀값은 열람·수정하지 않았다.
- `kbo_backend` 컨테이너는 내려가 있다(이전 일일 실행 로그: "DB was NOT reloaded"). 이번 작업에서 띄우지 않았다.
- `migrate_records.py` 는 아직 일일 파이프라인에 연결하지 않았다(기존 동작 유지).
