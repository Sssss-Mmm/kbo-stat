# KBO Stat 요구사항 정의서

작성일: 2026-08-31 · 상태: v1.3 · 상위 문서: [PLAN.md](PLAN.md)

기획서(PLAN.md)가 "왜/무엇을"이라면 이 문서는 **"무엇을 만족해야 완료인가"**를 ID 단위로 적는다.
각 요구사항은 검증 가능한 수용 기준(AC)을 가진다. AC를 못 쓰는 항목은 요구사항이 아니라 아이디어다.

**우선순위**: `필수` 없으면 서비스가 성립 안 됨 / `권장` 있어야 제값 / `선택` 있으면 좋음
**상태**: ✅ 완료 · 🟡 부분(백엔드만 등) · ⬜ 미구현

---

## 0. 용어

| 용어 | 정의 |
| --- | --- |
| 시즌 | KBO 정규시즌 연도. 이 문서에서 `season=2026`은 2026년 정규시즌을 뜻한다. |
| 시즌 상태 | `개막전`(1~3월) / `정규시즌`(3월말~10월초) / `포스트시즌`(10월) / `오프시즌`(11~2월) 4가지. FR-12 참조. |
| 활성 시즌 | 화면이 기본으로 보여주는 시즌. DR-06의 판정 규칙을 따른다. |
| 1차 진실 | `data/processed/*.csv`. DB는 이걸로 재생성 가능한 서빙용 사본이다(DR-08). |
| 갱신 | cron이 하루 1회 수행하는 수집→가공→CSV 저장→DB 재적재 전 과정(DR-01). |
| AC | 수용 기준(Acceptance Criteria). 참/거짓으로 판정 가능해야 한다. |

---

## 1. 범위와 전제

- 대상 시즌: 2026 정규시즌 (과거 데이터는 팀 순위에 한해 1982~ 보유)
- 사용자: 비로그인 익명 사용자 단일 역할. 권한 구분 없음.
- 데이터는 외부 사이트 크롤링으로 확보하며 공식 API 계약이 없다. → 출처 변경은 장애가 아니라 **예상된 상황**으로 다룬다(NFR-05).
- 실시간성 요구 없음. 데이터 신선도 기준은 "전일 경기까지 반영"(DR-01).

---

## 2. 기능 요구사항 (FR)

### FR-01 오늘의 KBO · `필수` · ✅
사용자는 첫 화면에서 오늘 경기 일정과 현재 순위를 본다.
- AC1 오늘 날짜의 경기 카드가 팀명·경기시간·구장과 함께 표시된다.
- AC2 경기가 없는 날(월요일·비시즌)에는 빈 화면이 아니라 "경기 없음" 문구가 나온다.
- AC3 종료된 경기는 점수와 승패가 표시된다.
- 구현: `GET /api/today-games?date=`, `Home.jsx`

### FR-02 순위표 · `필수` · ✅
- AC1 ✅ 10개 구단의 순위·경기수·승·패·무·승률·게임차가 표시된다.
- AC2 ✅ 최근 10경기 흐름을 확인할 수 있다.
- AC3 ⬜ 팀명 클릭 시 해당 팀 상세를 조회할 수 있다.
  → API는 있으나 `StandingsTable.jsx`에 클릭 핸들러가 없고 `/api/standings/{team_name}`을 호출하는 코드가 없다
  (5절 갭 요약 대조 중 발견). FR-07 팀 분석 페이지가 팀 단위 뷰를 제공하므로, 이 AC는 "팀 분석으로 연결"로
  바꿀지 별도 상세를 만들지 결정이 필요하다.
- 구현: `GET /api/standings`, `Standings.jsx` / (미사용) `GET /api/standings/{team_name}`

### FR-03 경기 일정·결과 · `필수` · ✅
- AC1 시즌 전체 일정을 날짜순으로 조회한다.
- AC2 특정 날짜(`/schedule/{date}`)로 필터링된다.
- AC3 종료 경기는 스코어를, 미래 경기는 예정 시간을 보여준다.
- 구현: `GET /api/schedule-games`, `GET /api/schedule/{date}`, `Schedule.jsx`

### FR-04 선수 기록 · `필수` · ✅
- AC1 타자/투수를 전환해 시즌 기록을 표로 본다.
- AC2 선수명으로 검색하면 해당 선수 기록이 나온다.
- AC3 팀별로 선수 목록을 필터링한다.
- AC4 리더보드에 없는 등록 선수도 조회된다. *(현재 데이터 소스에 따라 미충족 가능 — 리스크 R-03)*
- 구현: `GET /api/player-stats?role=&season=`, `/api/players/{hitters,pitchers}`, `/api/players/search/{name}`, `/api/players/team/{team}`, `Players.jsx`

### FR-05 핫/콜드존 · `권장` · ✅
- AC1 타자/투수를 선택해 스트라이크존 격자별 지표를 히트맵으로 본다.
- AC2 표본이 적은 존은 색으로 단정하지 않고 표본 수를 함께 노출한다.
- 구현: `GET /api/zones?role=batter|pitcher&season=`, `Zones.jsx` / `ZoneHeatmap.jsx`

### FR-06 AI 데일리 스토리 · `권장` · ✅
- AC1 오늘 경기 카드에 프리뷰(경기 전)/리뷰(종료 후) 요약이 붙는다.
- AC2 `OPENAI_API_KEY`가 없으면 에러가 아니라 mock 응답으로 화면이 정상 동작한다.
- AC3 생성 실패 시 스토리 영역만 비고 나머지 화면은 살아 있다.
- 구현: `GET /api/today-story?date=&season=`, `story_service.py`

### FR-07 팀 분석 화면 · `필수` · ✅
사용자는 한 팀의 시즌 흐름을 순위·월별·홈원정 세 각도로 본다.
- AC1 팀 선택 시 시즌 순위 변화가 라인 차트로 표시된다. — `RankRace` 재사용, `team-rank-history`의 실제 스냅샷 순위(`순위` 컬럼) 사용.
- AC2 월별 승/패/승률이 표시된다.
- AC3 홈/원정 성적이 나란히 비교된다.
- AC4 데이터가 없는 월은 0이 아니라 빈 값으로 구분된다. — 해당 월의 행 자체를 만들지 않는다.
- 구현: `GET /api/team-rank-history`, `/api/team-monthly?team=`, `/api/team-games?team=`,
  `kbo-dashboard/frontend/src/pages/Teams.jsx`, `App.jsx` 네비게이션 "팀 분석"(총 6개 페이지)
- 공용화: `src/lib/format.js`(`fmt*`·`parseRecord`·`recordWinRate`), `src/components/MiniTable.jsx`(`MiniTable`/`BarList`/`TeamCell`)로 추출해 `Home.jsx` 중복 제거.
- 검증: `npm run build` 통과. 홈/원정 집계를 실데이터로 교차검증 — 삼성 홈 33-1-21 / 원정 35-2-23이
  `data/processed/kbo_team_rank_2026.csv`의 홈·방문 기록과 정확히 일치.

### FR-08 관중·경기시간 · `선택` · ✅
- AC1 시즌·월별 관중 수를 조회한다.
- AC2 팀별/연도별 평균 경기 시간을 조회한다.
- 구현: `GET /api/attendance?season=&month=`, `/api/game-time/team`, `/api/game-time/yearly`
- 현황: `attendance`·`game-time/team`은 `Home.jsx` 운영 지표 박스(총 관중·최다 관중 팀·평균 경기시간)에서 소비 중.
  **전용 화면과 월별/연도별 뷰는 없다**(`game-time/yearly` 미사용). legacy `web/`에만 전체 화면이 있다.
- → PLAN T4

### FR-09 RAG 질의응답 화면 · `권장` · ✅
- AC1 자연어 질문을 입력하면 수집 데이터에 근거한 답변이 나온다.
- AC2 답변에 사용된 근거 데이터가 함께 표시된다(출처 없는 단정 금지).
- AC3 응답 실패 시 사용자에게 실패가 명시된다.
- 구현: `pages/Ask.jsx` + `POST /api/rag/ask`. 근거를 team/hitter로 갈라 `MiniTable` 두 개로 표시하고,
  각 표에 원본 CSV명과 검색 대상 행 수를 명시한다. `dangerouslySetInnerHTML` 미사용.
- AC2 보강: 백엔드가 **근거 0건이어도 단정형 답변을 반환**하므로, 화면이 이를 감지해 경고한다.
  답변 주체가 근거 목록에 있는 행에만 "답변 근거" 배지를 붙인다(타자는 소속팀이 아니라 선수명으로 판정).
- AC3: 연결 차단 → "서버에 연결하지 못했습니다", HTTP 500 → "요청 실패 (HTTP 500)". 실패 시 이전 답변을 지운다.

**정정**: 이 RAG는 LLM이 아니다. `rag_service.py`(348줄)는 pandas로 CSV를 읽어 토큰 겹침 점수로
검색하고 키워드 3갈래(`mvp|war|ops` / `뜨거|최근` / 나머지=팀)로 문장을 조립한다. OpenAI 참조가 없어
`OPENAI_API_KEY` 유무와 무관하게 동작한다(NFR-08은 F6 AI 스토리에만 해당).

**남은 문제 — 백엔드 답변 품질** (화면이 아니라 `services/rag_service.py` 이슈):
| 질문 | 실제 답변 | 문제 |
| --- | --- | --- |
| 왜 한화가 강하지? | 한화는 현재 8위, 승률 .441 | "왜"에 답하지 않음. 한화는 강하지 않음(최근 1승9패) |
| 삼성 홈 성적은? | 시즌 전체 68승44패3무 | `HomeAway`를 쓰지 않아 홈/원정 스플릿을 문서화하지 않음 |
| ~~김치찌개 맛집 알려줘~~ | ~~삼성는 현재 1위 (근거 0건)~~ | **해결** — `rag_service.ask()` 1줄: 근거 0건이면 단정형 대신 `NO_EVIDENCE_ANSWER`. 답할 수 있는 범위를 힌트로 제시한다. 회귀 확인: "삼성 어때?" 근거 7건, "WAR 1위는?" 근거 8건 정상 |
→ 남은 두 건은 신규 T11 (의도 분기 확장)

**배포 주의**: 백엔드는 소스 볼륨 마운트가 아니라 이미지에 COPY된다.
`docker compose restart backend`로는 코드 변경이 반영되지 않는다 — `up -d --build backend`를 써야 한다.

### FR-10 선수/팀 비교 · `선택` · ⬜ 미구현
- AC1 선수 2명을 선택하면 주요 지표가 나란히 비교된다.
- AC2 비교 대상은 같은 포지션군(타자↔타자)으로 제한된다.
- → PLAN T6

### FR-11 다크/라이트 테마 · `선택` · ✅
- AC1 토글로 전환되고 선택이 다음 방문에도 유지된다.
- AC2 저장된 선택이 없으면 OS 설정(`prefers-color-scheme`)을 따른다.
- 구현: `App.jsx`

### FR-13 가을야구 레이스 · `권장` · ✅
포스트시즌 진출 경쟁을 확정 계산만으로 보여준다.

- AC1 잔여 경기는 `144 − 경기수`로 계산한다. 미래 일정 개수로 세지 않는다(과거 날짜의 취소 경기 69건이 `status='scheduled'`로 남아 있어 틀린다).
- AC2 매직/트래직 넘버, 자력 진출·탈락 확정 여부를 표시한다.
- AC3 5위와의 승차, 피타고리안 기대승률과 실제 승률의 차이를 표시한다.
- AC4 **진출 확률·시뮬레이션을 제공하지 않는다**(PLAN 3절 비목표). 산식을 화면에 밝힌다.
- AC5 포스트시즌·오프시즌에는 잔여·매직·맞대결 섹션을 감추고 최종 순위와 곡선만 보여준다(FR-12 연동).
- 구현: `lib/race.js`(계산 전부, React 미의존) + `pages/Race.jsx`. 자체 점검 `node src/lib/race.test.js`.
- 검증: `team-games` 누적이 `/api/standings`와 **10팀 전부 일치**(삼성 115경기 68-44-3). 복원한 순위 곡선 122일치의 마지막 날 순위가 공식 순위와 10팀 전부 일치. 취소 69건(우천32/폭염30/그라운드7) 제외 확인.
- 매직넘버 상대는 6위 고정이 아니라 **진출선 밖 `승수+잔여` 최대 팀**이다 — 잔여가 많은 하위 팀이 더 위협적일 수 있다.

### FR-14 구종 아스널 · `선택` · ✅
투수가 무엇을 던지고 타자가 무엇을 못 치는지를 구종 단위로 본다.

- AC1 구사율 합이 선수별로 100%가 된다 (실측: 전 선수 0.9998~1.0002).
- AC2 안타 판정에 `PitchResult=='H'`를 쓰지 않는다 — `H`는 인플레이이고 안타는 `IsHit`이다.
- AC3 볼카운트는 투구 *전* 카운트로 환산한다 (`Ball`/`Strike`는 투구 후 값).
- AC4 표본이 부족한 항목은 수치를 단정하지 않는다 (구종 30구·스윙 10회·타구 10개 미만은 생략).
- AC5 수집 커버리지를 화면에 명시한다 (2026 111경기일 / 2025 180경기일 — 전 경기가 아니다).
- 구현: `src/build_pitch_arsenal.py` → `routers/arsenal.py`(CSV 직결) → `components/PitchArsenal.jsx`.
  핫/콜드존 페이지를 "투구 분석"으로 개명하고 탭으로 합쳤다 — 네비는 9개 유지.
- 검증: 곽빈 2,271구가 원본과 일치, 구종별 헛스윙률·구속 소수점까지 일치. 리그 직구 평균 146.5km/h.
- 원천 불가(GAP G-06): 무브먼트·릴리스 포인트·3D 궤적, 투수 좌우완.

### FR-15 볼카운트 야구 · `선택` · ✅
카운트가 타석을 어떻게 바꾸는지 본다. 목표 사이트에 대응물이 없는 차별화 항목.

- AC1 볼카운트는 투구 *전* 카운트다. 복원 로직은 `build_pitch_arsenal`의 것을 재사용하며 중복 구현하지 않는다.
- AC2 타자 유리 카운트(3-0)의 출루율이 투수 유리(0-2)보다 높다 — 실측 .755 vs .211.
- AC3 표본 미달은 단정하지 않는다(목록 50타석, 셀 하한 투구 30구/타석 20). `0/0`을 `.000`으로 찍지 않는다.
- AC4 버킷이 배타적이지 않음을 명시한다(투수유리는 2S의 부분집합).
- 구현: `src/build_count_metrics.py` → `GET /api/count-baseball` → `components/PitchCount.jsx`("투구 분석" 3번째 탭).
- 검증: `Ball`/`Strike`를 쓰지 않고 `PitchResult`로 카운트를 쌓는 전방 시뮬레이션으로 독립 재계산 —
  복원 일치율 99.91%. 리그 초구 스윙률 26.6%(KBO 상식 25~30% 범위).
- 버린 지표: 인플레이 타율(12칸 범위가 .310~.381뿐이라 카운트 효과가 안 보인다), 선수별 12칸(표본 부족),
  투수 관점(구종 아스널이 이미 낸다), 카운트별 wOBA(장타 구분이 `AtBatText` 문자열에만 있다).

### FR-12 시즌 상태별 화면 동작 · `필수` · ✅
KBO는 1년 중 절반 이상이 정규시즌이 아니다. 각 화면이 비시즌·포스트시즌에 무엇을 보여줄지 정의한다.

| 화면 | 정규시즌 | 포스트시즌(10월) | 오프시즌(11~2월) | 개막전(1~3월) |
| --- | --- | --- | --- | --- |
| 오늘의 KBO | 오늘 경기 | 오늘 PO 경기 | "시즌 종료" + 최종 순위 | "개막 D-n" + 직전 시즌 최종 순위 |
| 순위표 | 실시간 순위 | 정규시즌 **최종** 순위 고정 + PO 대진 표기 | 최종 순위 | 직전 시즌 최종 순위 |
| 경기 일정 | 당월 | PO 일정 | 최종 결과 조회만 | 개막 일정 공개 시 표시 |
| 선수 기록 | 시즌 누적 | 정규시즌 최종 기록 고정 | 최종 기록 | 직전 시즌 기록 |
| 핫/콜드존 | 누적 | 최종 고정 | 최종 고정 | 직전 시즌 |
| AI 스토리 | 프리뷰/리뷰 | 프리뷰/리뷰 | **비활성**(생성 호출 안 함) | 비활성 |

- AC1 어느 시즌 상태에서도 화면이 빈 표나 흰 화면으로 끝나지 않고, 위 표의 내용을 보여준다.
- AC2 화면 상단에 현재 무슨 시즌의 데이터를 보고 있는지 명시된다(예: "2026 정규시즌 최종").
- AC3 오프시즌에는 AI 스토리 API를 호출하지 않는다(불필요한 비용 방지).
- AC4 포스트시즌 순위표는 정규시즌 순위를 덮어쓰지 않는다.
- 비고: 포스트시즌 **경기 데이터 수집**은 이번 범위 밖(정규시즌 데이터만 수집). 화면은 "PO 진행 중" 안내로 처리한다.

**구현**: `frontend/src/lib/season.js`의 `seasonState(today, games)` 한 곳에서만 판정한다(새 API 없음 —
`/api/schedule-games` 응답과 KST 오늘 날짜로 계산). `App.jsx`가 앱 진입 시 1회 판정해 6개 페이지에
`seasonInfo`로 내려주고, **AC2 배너는 페이지마다 두지 않고 셸에서 한 번만** 그린다.

`preseason`은 "다음 시즌 일정이 공개됐고 개막일이 미래"일 때만이다. 1~2월에 활성 시즌 폴백(DR-06)으로
직전 시즌 일정만 오는 동안은 개막일을 알 수 없어 D-n을 말할 수 없으므로 `offseason`으로 두고
폴백 사실만 notice로 알린다(**DR-06 AC2 해결**).

**데이터 함정 대응**: 잔여 경기 판정에 날짜 조건(`Date >= today`)을 함께 건다. `status='scheduled'` 206행 중
69행이 과거 날짜의 취소 경기(우천 32·폭염 30·그라운드 7)라, 이 조건이 없으면 오프시즌이 정규시즌으로 보인다.

**검증** — 실제 일정 데이터로 4개 상태 재현 (`node src/lib/season.test.js` 통과):

| 기준일 | state | storyEnabled | 배너 |
| --- | --- | --- | --- |
| 2026-08-31 | regular | true | `2026 정규시즌` |
| 2026-10-15 | postseason | true | `2026 정규시즌 최종 · 포스트시즌 진행 중` |
| 2026-12-20 | offseason | **false** | `2026 정규시즌 최종 · 시즌 종료` |
| 2027-01-10 | offseason | **false** | `… · 2027시즌 데이터가 없어 직전 시즌으로 표시합니다` |
| 2027-02-20 (다음 시즌 일정 공개 시) | preseason | **false** | `2027 시즌 개막 D-35` |

AC3은 `TodayGames.jsx`가 `if (!storyEnabled) return`으로 **요청 자체를 보내지 않는다**(결과를 숨기는 게 아니다).

---

## 3. 데이터 요구사항 (DR)

### DR-01 일일 갱신 · `필수` · ✅
- AC1 매일 **02:00 KST**(`0 2 * * *`)에 순위·일정·결과·관중·경기시간·타자 파생지표가 자동 갱신된다.
- AC2 갱신은 사람 개입 없이 완료된다.
- AC3 동시 실행이 발생하지 않는다(`flock`).
- 구현: cron → `scripts/update_kbo_daily.sh` → `src/update_daily.py`

### DR-02 빈 데이터 방어 · `필수` · ✅
출처 구조가 바뀌면 파서는 예외 없이 빈 결과를 반환한다. 이걸 그대로 저장하면 멀쩡한 CSV가 헤더만 남는다.
- AC1 0행 데이터는 기존 CSV를 덮어쓰지 않는다.
- AC2 0행이 정상인 경우(비시즌, 우천취소)는 `allow_empty=True`로 **명시적으로만** 허용된다.
- AC3 거부 시 어떤 파일이 왜 막혔는지 로그에 남는다.
- AC4 CSV를 저장하는 모든 모듈이 `csv_guard.save_csv`를 경유한다.
- 구현: `src/csv_guard.py`
- **AC4 충족**: 13개 파일 19곳에 남아 있던 `to_csv` 직접 호출을 전부 `csv_guard.save_csv` 경유로 전환했다 —
  `crawl_kbo_{hitter,pitcher,schedule,players,team_rank,attendance,game_time}.py`, `crawl_naver_pitch_zones.py`,
  `crawl_statiz.py`, `crawl.py`, `build_{dataset,zone_metrics,team_game_results}.py`.
- 검증: `grep -rn "to_csv" src/ | grep -v csv_guard.py` → **0건**.
  `python3 src/csv_guard.py` 자체 점검(0행 거부 + 기존 CSV 보존 + `allow_empty=True` 통과) 통과.

### DR-03 CSV ↔ DB 일관성 · `필수` · ✅
CSV가 1차 진실이고 DB는 서빙용 사본이다. 수동으로 `update_daily.py`만 돌리면 화면은 옛 데이터를 보여준다.
- AC1 일일 자동 갱신 경로는 CSV 갱신 후 DB 재적재를 항상 함께 수행한다.
  → `scripts/update_kbo_daily.sh`가 `docker compose exec -T backend python migrate.py`로 처리한다.
- AC2 적재 실패 시 스크립트가 non-zero로 종료하고 로그에 남는다(exit 3/4).
- AC3 수동 갱신 시에는 `--db` 또는 `migrate.py`를 별도로 실행해야 함이 문서화되어 있다.
- 검증: `docker compose exec -T backend python migrate.py`로 CSV → DB 전량 재적재 성공.
  재적재 후 `team-rank-history` 40 → 250행, `team-games` 630 → 1152행으로 CSV와 일치.
  (재적재 전 DB가 CSV보다 뒤처져 있었다는 뜻이므로, 수동 갱신 시 `migrate.py` 필요가 실증됐다.)

### DR-04 스키마 안정성 · `권장`
- AC1 `data/processed/*.csv`의 컬럼명 변경은 API 응답 키 변경과 함께 검토된다.
- AC2 DB 스키마 변경은 `migrate.py` / `migrate_analytics.py`를 통해 적용된다.

### DR-05 과거 데이터 · `선택`
- 1982~2025 팀 순위 CSV를 보유하나 현재 화면에서 사용하지 않는다.
- 활용 여부는 PLAN 9절 열린 질문으로 남긴다. **결정 전까지 시즌 선택 UI를 만들지 않는다.**

### DR-06 활성 시즌 판정 · `필수` · ✅ (AC2는 FR-12에 남음)
`kbo-dashboard/backend/utils.py`의 `current_season()`이 "현재 연도 데이터가 없으면 직전 시즌으로 폴백"하도록 수정됐다.

- AC1 ✅ 활성 시즌은 다음 규칙으로 정한다: **현재 연도 데이터가 존재하면 현재 연도, 없으면 직전 시즌.**
  → `season_has_data(season)` 헬퍼 추가(= `data/processed/*_{season}.csv` glob) 후 `current_season()`이 이를 사용.
- AC2 활성 시즌이 직전 시즌으로 폴백되면 화면에 그 사실이 표시된다(FR-12 AC2와 동일) — **FR-12(⬜)에 종속, 미구현**.
- AC3 ✅ `season` 쿼리 파라미터를 명시하면 판정 규칙보다 우선한다.
- AC4 ✅ 존재하지 않는 시즌을 요청하면 빈 배열이 아니라 404로 응답한다(NFR-16 참조).
- 영향 범위: `utils.current_season()` 호출부 24곳이 수정 없이 그대로 적용받는다.
- 검증: `utils.py` `__main__`의 assert 자체 점검 — `python3 utils.py` → `ok: 2026`
  (불변식: 활성 시즌은 항상 데이터가 있는 시즌 / `season_has_data(2099)`는 False).

### DR-07 데이터 정합성 · `필수` · ✅
DR-02는 "0행"만 막는다. 행 수가 맞아도 값이 깨진 데이터는 그대로 통과한다.
갱신 직후, DB 적재 **전에** 아래를 검사하고 실패 시 적재를 중단한다.

| ID | 규칙 | 대상 |
| --- | --- | --- |
| V-01 | 팀 수가 정확히 10 | 순위 |
| V-02 | 순위 값이 1~10 중복 없이 유일 | 순위 |
| V-03 | 승 + 패 + 무 = 경기수 (팀별) | 순위 |
| V-04 | 승률이 0.000~1.000 범위 | 순위 |
| V-05 | 팀명이 알려진 10구단 명칭 집합에 속함 | 전체 |
| V-06 | 날짜가 `YYYY-MM-DD`로 파싱되고 시즌 범위 안 | 일정·결과 |
| V-07 | 타율/출루율/장타율이 0~5 범위(결측은 허용, 음수·이상치는 거부) | 선수 기록 |
| V-08 | 전일 대비 행 수가 50% 이상 감소하지 않음 | 전체 |

- AC1 ✅ 위반 시 `IntegrityError`(규칙 ID + 깨진 값 포함)로 저장을 거부한다. 예: `V-03: 승+패+무 != 경기: [...]`
- AC2 ✅ 예외가 `to_csv` **앞에서** 발생하므로 기존 CSV는 그대로 남고, CSV가 안 바뀌니 DB 재적재분도 변하지 않는다.
- AC3 ✅ 검사는 `src/csv_guard.py` 한 곳에서 수행된다. 파일명 접두사 → 검사 함수 매핑(`CHECKS`, 최장 접두사 우선)으로
  분기하므로 크롤러별로 흩어지지 않는다. `save_csv(check=False)`는 백필처럼 행 수 급감이 정상인 경우에만 쓴다.
- 구현: `src/csv_guard.py`의 `_check_team_rank`·`_check_team_rank_history`·`_check_schedule`·`_check_hitters`·`_check_row_drop`
- 검증(오탐 없음): 실제 운영 CSV 5종 — `kbo_team_rank_2026`, `kbo_team_rank_history_2026`, `kbo_schedule_2026`,
  `kbo_naver_hitters_2026`, `kbo_hitter_metrics_2026` — 전부 통과.
  깨진 데이터 거부는 `python3 src/csv_guard.py` 자체 점검(V-01~V-05 각각 위반 샘플 + V-08 행 급감)으로 확인.

### DR-08 백업·복구 · `필수` · ✅
DB는 백업 대상이 아니다. **CSV가 1차 진실이고 DB는 언제든 재생성 가능한 사본**이다.

- AC1 ✅ DB 볼륨이 완전히 소실돼도 `migrate.py` 실행만으로 CSV에서 전량 복구된다.
- AC2 ✅ `migrate.py`는 시즌별 delete-after 방식이라 몇 번을 돌려도 결과가 같다(멱등).
- AC3 ✅ 컨테이너 최초 기동 시 DB가 비어 있으면 자동 시드된다(`seed_if_empty.py`).
- AC4 ✅ `data/` 디렉터리는 호스트에 보존되며 컨테이너 재생성으로 사라지지 않는다.
- 검증(AC1·AC2): `docker compose exec -T backend python migrate.py` 실행으로 CSV 전량 재적재 성공,
  `team-rank-history` 250행 / `team-games` 1152행으로 CSV와 일치(DR-03 검증과 동일 실행).
- **미충족**: 위 복구 절차가 README/운영 문서에 적혀 있지 않다. → 문서화 필요(PLAN T2).

---

## 4. 비기능 요구사항 (NFR)

| ID | 항목 | 요구사항 | 우선순위 | 상태 |
| --- | --- | --- | --- | --- |
| NFR-01 | 응답 성능 | 기준 측정 대상 4개(`/api/standings`, `/api/schedule-games`, `/api/player-stats?role=hitter`, `/api/zones?role=batter`)를 2026 시즌 데이터 기준·캐시 없이 20회 호출해 **p95 < 1000ms** | 필수 | ✅ 최악 p95 **59.4ms** (4.1절) |
| NFR-02 | 화면 로딩 | 로컬 Docker·데스크톱 Chrome에서 각 페이지 최초 콘텐츠 표시까지 **3초 이내** | 권장 | 미측정 |
| NFR-03 | 기동 | `docker compose up -d --build` 한 번으로 전체 스택 기동 | 필수 | ✅ |
| NFR-04 | 헬스체크 | `GET /health`로 백엔드 상태 확인 | 필수 | ✅ |
| NFR-05 | 장애 격리 | 한 구성요소 실패가 다른 데이터 갱신·서빙을 막지 않는다 | 필수 | ✅ (4.2절, 버그 수정 후 검증) |
| NFR-06 | 부분 실패 UI | 한 API 실패가 페이지 전체를 흰 화면으로 만들지 않는다 | 필수 | ✅ (4.3절) |
| NFR-07 | 비밀 관리 | DB 비밀번호·API 키는 `.env`로만 주입, 저장소에 커밋 금지 | 필수 | ✅ |
| NFR-08 | 외부 의존 degrade | OpenAI 키 부재 시 mock으로 동작 | 필수 | ✅ |
| NFR-09 | 수집 예의 | 갱신은 하루 1회, 불필요한 재시도·병렬 요청 금지 | 필수 | ✅ |
| NFR-10 | 브라우저 | 최신 Chrome/Edge/Safari 데스크톱 지원 | 권장 | — |
| NFR-11 | 반응형 | 모바일 폭에서 표가 가로 스크롤되고 레이아웃이 깨지지 않는다 | 권장 | 확인 필요 |
| NFR-12 | 로그 | 갱신 결과가 `logs/`에 날짜와 함께 남는다 | 필수 | ✅ |
| NFR-13 | 문서 일치 | README 기능 목록이 실제 화면과 일치한다 | 권장 | ✅ (네비 6개·12열 순위표·5×5 존 반영, 복구 절차 추가) |
| NFR-14 | 라이선스·출처 | 데이터 출처와 권리 귀속을 명시한다 | 필수 | ✅ |
| NFR-15 | 타임존 | 모든 날짜·시즌 판정은 `Asia/Seoul` 기준으로 한다 | 필수 | ✅ (`src/*` 전역 `ZoneInfo("Asia/Seoul")`) |
| NFR-16 | 오류 응답 규약 | 5.1절 규약을 모든 엔드포인트가 따른다 | 필수 | ✅ 400·404·502·503 실측 확인 (5.1절) |
| NFR-17 | 복구 시간 | DB 전량 소실 시 `migrate.py` 한 번으로 30분 이내 복구 | 권장 | 미측정 (재적재 성공만 확인 — DR-03) |
| NFR-18 | 자동 검증 | 비자명 로직(파서·정합성 검사·시즌 판정)은 실행 가능한 자체 점검을 가진다 | 권장 | 🟡 정합성 검사(`csv_guard._selfcheck`)·시즌 판정(`utils.__main__`)만, 파서 없음 |

### 4.1 NFR-01 응답 성능 측정 결과 · ✅ 충족

조건: 2026 시즌, 캐시 없음, 순차 20회 호출, p95는 nearest-rank. 2라운드 반복해 재현 확인, 80/80 HTTP 200.

| 엔드포인트 | p50 | p95 | max | 응답 건수 |
| --- | --- | --- | --- | --- |
| `GET /api/standings` | 3.7ms | 4.2ms | 4.8ms | 10 |
| `GET /api/schedule-games` | 20.6ms | 59.4ms | 62.3ms | 782 |
| `GET /api/player-stats?role=hitter` | 22.6ms | 25.8ms | 28.2ms | 342 |
| `GET /api/zones?role=batter` | 57.4ms | 59.4ms | 60.8ms | 2267 |

기준 1000ms 대비 최악 p95가 59.4ms로 **16배 이상 여유**. 콜드/웜 유의차 없음 —
캐시가 없어 첫 호출과 20번째 호출이 같은 일을 한다.

> 향후 참고: `/api/zones`의 병목은 CSV 재파싱(~15ms)이 아니라 **515KB 응답의 JSON 직렬화·전송(~42ms)**이다.
> 느려지면 손댈 곳은 캐시가 아니라 응답 페이로드 축소다.

### 4.2 NFR-05 장애 격리 · ✅ (버그 수정 후 충족)

**발견한 버그**: `entrypoint.sh`의 `set -e` 아래에서 `seed_if_empty.py`가 DB 연결 실패로 exit 1 →
**컨테이너 전체가 죽어 DB와 무관한 CSV 라우터까지 전멸**했다(`kbo_backend Exited (1)` 재현됨).

**수정**: `kbo-dashboard/backend/seed_if_empty.py`의 `main()`을 try/except로 감싸 시드 실패가 치명적이지 않게 함(실질 6줄).
`entrypoint.sh`는 수정하지 않았다.

**검증** (`docker compose stop postgres` 후 실측):

| 요청 | DB 다운 시 결과 |
| --- | --- |
| `GET /health` | 200 |
| `GET /api/zones?role=batter` (CSV 기반) | 200 |
| `GET /api/standings` (DB 기반) | 503 `{"detail":"database unavailable"}` |

실패 사유는 컨테이너 로그에 남는다.

### 4.3 부분 실패 UI (NFR-06)

다중 API를 호출하는 페이지는 **Home(6개)과 Teams(3개) 둘뿐**이다. 나머지 4개 페이지
(Standings·Schedule·Players·Zones)는 단일 API라 그 요청의 실패가 곧 그 화면의 유일한 데이터 부재이며,
이미 `error` 상태로 처리된다 — NFR-06 대상이 아니다.

- **Teams**: 요청 실패를 `null`, 빈 응답을 `[]`로 구분한다. 한 API가 실패해도 나머지 패널은 정상
  렌더되고 실패한 패널에만 "불러오지 못했습니다"가 뜬다. 셋 다 실패할 때만 페이지 전체 에러.
  headless Chrome DOM으로 확인: `team-monthly`만 실패 → 순위 변화·홈/원정 정상,
  `team-rank-history`만 실패 → 셀렉터·나머지 패널 유지.
- **Home**: `.catch(() => [])`가 실패와 빈 데이터를 뭉개던 것을 고쳤다. 실패한 요청의 이름을 모아
  상단에 "일부 데이터를 불러오지 못했습니다: …"로 알린다.
  실측(관중=빈 응답, 경기시간=요청 실패): 살아남은 데이터 10 / 1152 / 342 / 285건이 그대로 렌더되고,
  배너에는 **경기시간만** 표시됐다. 200 + 빈 배열은 5.1절 AC1대로 오류가 아니므로 배너에 넣지 않는다.

## 5. 인터페이스 요구사항

- 백엔드 베이스: `http://127.0.0.1:8001`, 모든 데이터 API는 `/api` 프리픽스
- 프론트 개발 서버(`:3000`)는 `/api`를 백엔드로 프록시한다
- 응답은 JSON. 조회 API는 `season` 쿼리 파라미터를 공통으로 받으며 미지정 시 현재 시즌으로 처리한다
- 오류는 5.1절 규약을 따른다

| 엔드포인트 | 파라미터 | 화면 연결 |
| --- | --- | --- |
| `GET /health` | — | — |
| `GET /api/today-games` | `date` | FR-01 |
| `GET /api/today-story` | `date`, `season` | FR-06 |
| `GET /api/standings` | `season` | FR-02 |
| `GET /api/standings/{team_name}` | `season` | FR-02 |
| `GET /api/schedule-games` | `season` | FR-03 |
| `GET /api/schedule` | `season`, `team` | FR-03 |
| `GET /api/schedule/{date}` | — | FR-03 |
| `GET /api/player-stats` | `role`, `season` | FR-04 |
| `GET /api/players/hitters` `/pitchers` | `season`, `limit` | FR-04 |
| `GET /api/players/search/{name}` | `season` | FR-04 |
| `GET /api/players/team/{team}` | `season`, `player_type` | FR-04 |
| `GET /api/hitters-raw` `/pitchers-raw` | `season` | FR-04 |
| `GET /api/hitter-metrics` | `season` | FR-04 |
| `GET /api/zones` | `role`, `season` | FR-05 |
| `GET /api/team-rank-history` | `season` | FR-07 (`Teams.jsx`) |
| `GET /api/team-monthly` | `season`, `team` | FR-07 (`Teams.jsx`) |
| `GET /api/team-games` | `season`, `team` | FR-07 (`Teams.jsx`), FR-01 타이틀 레이스(`Home.jsx`) |
| `GET /api/team-rank` | `season` | **FR-07 (화면 없음)** |
| `GET /api/attendance` | `season`, `month` | FR-08 부분 — `Home.jsx` 운영 지표 박스만, 전용 화면 없음 |
| `GET /api/game-time/team` | `season` | FR-08 부분 — `Home.jsx` 운영 지표 박스만, 전용 화면 없음 |
| `GET /api/game-time/yearly` | `season` | **FR-08 (화면 없음)** |
| `POST /api/rag/ask` | body: `question`, `season` | FR-09 · Ask |
| `GET /api/rag/search` | `query`, `season`, `limit` | **FR-09 (화면 없음)** |

> 라우터 소속 주의: `/api/schedule-games`는 `routers/analytics.py:231`에 있다(CSV `kbo_schedule_{season}.csv` 기반).
> `routers/schedule.py`는 별개의 `/api/schedule`·`/api/schedule/{date}`(DB `schedules` 테이블)를 제공한다.
> 이름이 비슷하지만 데이터 소스가 다르므로 함께 묶어 다루지 않는다.

**갭 요약** (`grep -rE "/api/" kbo-dashboard/frontend/src/` 기준, 2026-08-31):
데이터 엔드포인트 25개(+`/health`) 중 **11개 사용 / 14개 미사용**.

- 사용(11): `today-games`, `today-story`, `standings`, `schedule-games`, `player-stats`, `zones`,
  `team-rank-history`, `team-monthly`, `team-games`, `attendance`, `game-time/team`
- 미사용(14): `standings/{team_name}`, `schedule`, `schedule/{date}`, `players/hitters`, `players/pitchers`,
  `players/search/{name}`, `players/team/{team}`, `hitters-raw`, `pitchers-raw`, `hitter-metrics`,
  `team-rank`, `game-time/yearly`, `rag/ask`, `rag/search`

FR-07은 화면이 붙어 해소됐다. 남은 미사용의 성격은 세 갈래다 —
(1) FR-09(RAG) 화면 미착수 2개, (2) FR-08 전용 화면 미착수 1개(`game-time/yearly`),
(3) 나머지 11개는 프론트가 `player-stats`·`standings` 같은 **전량 조회 후 클라이언트 필터** 방식을 택해
서버 측 검색·필터 엔드포인트를 안 쓰게 된 것(중복 기능). 8절 완료 판정 5번은 이 사유 기재로 충족한다.

### 5.1 오류 응답 규약

응답 본문은 FastAPI 기본 형식 `{"detail": "<사람이 읽을 수 있는 사유>"}`를 따른다.

| 상태 | 의미 | 예 |
| --- | --- | --- |
| 400 | 파라미터 값이 허용 집합 밖 | `role must be 'hitter' or 'pitcher'` |
| 404 | 존재하지 않는 리소스(없는 팀·선수·시즌) | `season 2027 데이터 없음` |
| 502 | 외부 출처(네이버 등) 조회 실패 | `Naver 일정 조회 실패: ...` |
| 503 | DB 연결 불가 | `database unavailable` |

- AC1 데이터가 "아직 없음"(비시즌 등)은 **오류가 아니다** — 200 + 빈 배열로 응답하고, 화면이 FR-12 표대로 처리한다.
- AC2 존재할 수 없는 요청(없는 시즌·팀)은 404로 구분한다. 빈 배열로 뭉개지 않는다.
- AC3 프론트는 4xx/5xx를 받으면 해당 영역만 오류 상태로 표시하고 페이지 전체를 죽이지 않는다(NFR-06).
  → **Teams 페이지만 충족**(4.3절). 나머지 페이지 미적용.

**현황 (실측)**: 400·404·502·503 모두 구현됨.

| 요청 | 응답 | 구현 위치 |
| --- | --- | --- |
| `GET /api/player-stats?role=hitter&season=2099` | 404 | `routers/player_stats.py:28` (CSV 부재) |
| `GET /api/zones?role=batter&season=2099` | 404 | `routers/zones.py:27` (CSV 부재) |
| `GET /api/standings?season=2099` | 404 | `services/standings_service.py:40` |
| `GET /api/player-stats?role=bogus` | 400 | `routers/player_stats.py:40` |
| `GET /api/standings` (DB 다운) | 503 `{"detail":"database unavailable"}` | `main.py:51` `@app.exception_handler(OperationalError)` |

---

## 6. 제약 조건

- C-01 크롤링 대상은 공개 문서화된 API가 아니다. 구조 변경 시 파서 수정이 필요하다.
- C-02 데이터 권리는 원 출처(KBO·네이버·Statiz)에 있으며 상업적 재배포는 하지 않는다.
- C-03 실행 환경은 로컬 Docker 기준. 외부 호스팅은 미결(PLAN 9절).
- C-04 프론트는 React 앱 하나다. 1세대 정적 프론트(`web/`)는 전용 화면이 모두 이관돼 제거됐다.
- C-05 로그인·개인화 없음. 사용자 상태는 브라우저 localStorage(테마)뿐이다.

---

## 7. 검증 방법

각 요구사항을 어떻게 확인하는지 정한다. 방법이 없는 AC는 완료 판정에 쓸 수 없다.

| 구분 | 방법 | 주기 |
| --- | --- | --- |
| FR AC (화면) | 수동 확인 — 브라우저에서 해당 페이지를 열어 AC를 하나씩 대조 | 기능 착수·완료 시 |
| FR AC (API) | `curl`로 엔드포인트 호출 후 응답 확인 (README 대표 API 참조) | 기능 완료 시 |
| DR-01 | `logs/update_kbo_daily.log`에서 최근 7일 갱신 성공 여부 확인 | 주 1회 |
| DR-02 | `python3 src/csv_guard.py` 자체 점검 + `grep -rn "to_csv" src/ \| grep -v csv_guard.py`가 0건인지 | 코드 변경 시 |
| DR-06 | `python3 kbo-dashboard/backend/utils.py` 자체 점검 | 코드 변경 시 |
| DR-07 | `python3 src/csv_guard.py` — 깨진 샘플 입력(V-01~08)이 거부되고 운영 CSV는 통과하는지 | 코드 변경 시 |
| NFR-01 | `curl -w "%{time_total}"` 20회 반복, p95 산출 | 릴리스 전 |
| NFR-05 | `docker compose stop postgres` 후 `/health`·CSV 라우터가 200, DB 라우터가 503인지 | 릴리스 전 |
| NFR-06 | 한 API를 실패시키고 나머지 패널이 살아 있는지 (headless Chrome DOM 확인) | 릴리스 전 |
| NFR-17 | DB 볼륨 삭제 후 `migrate.py`로 복구, 소요 시간 측정 | 반기 1회 |

**최근 실행 기록 (2026-08-31)**: DR-02·DR-03·DR-06·DR-07·NFR-01·NFR-05·NFR-06·NFR-16 실행 완료.
결과는 각 항목 본문과 4.1~4.3절에 기록. 미실행: NFR-02, NFR-11, NFR-17.

- 자체 점검은 프레임워크 없이 `assert` 기반 `__main__` 블록 또는 단일 `test_*.py`로 둔다(NFR-18).
- 전면적인 테스트 스위트는 이번 범위 밖이다. 깨지면 조용히 틀린 데이터가 나가는 지점(파서·정합성·시즌 판정)에만 검증을 건다.

---

## 8. 완료 판정

이 문서 기준 다음이 모두 참이면 v1 완료로 본다.

1. `필수` FR 전부 ✅ — 현재 **FR-02 🟡, FR-12 ⬜ → 미달** (FR-07 ✅ 해소)
2. `필수` NFR 전부 ✅ 또는 측정치 기록됨 — 현재 **NFR-06 🟡, NFR-13 ❌ → 미달** (NFR-01/05/16 ✅ 해소)
3. `필수` DR 전부 ✅ — **DR-02/DR-06/DR-07 ✅ 해소.** DR-08은 기능은 ✅, 문서화만 미비
4. NFR-13 충족 (README ↔ 실제 일치) — **미달**
5. 5절 표에 화면 미연결 엔드포인트가 없거나, 남긴 사유가 적혀 있다 — **충족**(5절 갭 요약에 14개 전부 사유 기재)
6. 7절 검증 방법이 각 항목에 대해 최소 1회 실행되고 결과가 기록되었다 — **부분**(NFR-02/11/17 미실행)

### 현재 미달 항목 (v1까지 남은 일)

| 항목 | 내용 | PLAN 매핑 |
| --- | --- | --- |
| NFR-02 | 화면 로딩 시간 미측정 | 신규 |
| NFR-11 | 모바일 반응형 미확인 | 신규 |
| NFR-17 | DB 전량 복구 소요 시간 미측정 | 신규 |
| NFR-18 | 파서 자체 점검 없음 (정합성·시즌 판정은 있음) | 신규 |
| — | FR-08 전용 화면(`game-time/yearly`), FR-09 RAG 화면 — `선택`/`권장`이라 v1 완료 판정에는 미포함 | T4·T5 |

---

## 9. 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1 초안 | 2026-08-31 | 최초 작성 (FR-01~11, DR-01~05, NFR-01~14) |
| v1.1 | 2026-08-31 | 실제 코드 대조로 DR-02 ✅→🟡, DR-03 🟡→✅ 정정. DR-01 갱신 시각 02:00 KST 명시, NFR-15(타임존) 추가 |
| v1.2 | 2026-08-31 | 0절 용어, FR-12(시즌 상태), DR-06~08(시즌 판정·정합성·복구), NFR-16~18, 5.1 오류 규약, 7절 검증 방법 추가 |
| v1.3 | 2026-08-31 | 구현·검증 결과 반영. FR-07 🟡→✅(Teams.jsx), DR-02 🟡→✅(`to_csv` 잔여 0건), DR-06 🟡→✅(데이터 기반 폴백), DR-07 ⬜→✅(V-01~08), NFR-01 미측정→✅(최악 p95 59.4ms), NFR-05 확인필요→✅(seed 실패로 컨테이너 전멸하던 버그 수정), NFR-16 🟡→✅(400·404·502·503 실측). 4.1~4.3절(성능·장애격리·부분실패 측정 결과) 신설. NFR-06은 Teams 한정 🟡로 명시, NFR-18 ⬜→🟡. 5절 갭 요약을 grep 실측으로 재산정(11 사용 / 14 미사용)하고 `/api/schedule-games`의 라우터 소속(`analytics.py`) 명시. 대조 중 FR-02 AC3 미충족 발견해 ✅→🟡 |
| v1.4 | 2026-08-31 | **`필수` 항목 전부 충족.** FR-02 🟡→✅(팀명 클릭 → 팀 분석 연결), FR-12 ⬜→✅(`lib/season.js` 단일 판정 + 셸 공통 배너, 4개 상태 실측), NFR-13 ❌→✅(README 동기화·복구 절차 추가), DR-08 문서화 충족. 핫/콜드존 3×3→5×5(존 안 38.5%만 보던 것을 100%로), 히트맵 상하 반전 버그 수정. 투구 데이터 백필: 2026 결손 복구(91→111일), 2025 전 시즌 신규(180일/222,444구). |
| v1.5 | 2026-08-31 | FR-13(가을야구 레이스) 추가 — 잔여·매직/트래직·자력 확정·5위차·피타고리안. 계산은 `lib/race.js` 단일 지점, 확률·시뮬레이션 없음. 네비 6개 → 7개. |
| v1.6 | 2026-08-31 | FR-09 ✅ — `pages/Ask.jsx`(근거 표 + 원본 CSV명 명시) 신설, 백엔드가 근거 0건에도 단정하던 문제 해결(`rag_service.ask()` 1줄). RAG가 LLM이 아니라 규칙 기반 CSV 검색임을 명시. 네비 7개 → 8개. |
| v1.7 | 2026-08-31 | FR-08 ✅ — `pages/Ops.jsx`(리그 운영) 신설. 연도별 경기시간 45시즌(1982~2026)을 전면에. 수집 안 된 항목(관중 요일별·수용률, 경기시간 월/요일/구장별)은 만들지 않고 화면에 부재 사유를 명시. 교차검증 4건 원본 CSV 일치. 네비 8개 → 9개, 미사용 엔드포인트 14 → 12. `game-time/yearly`의 `season` 무시 사실 기재. |
| v1.8 | 2026-08-31 | 이동거리 추가(Haversine 직선거리, 좌표 13쌍 ±10% 자체 점검, 미매칭 0%). **레거시 `web/` 제거** — 전용 화면 4종(관중·경기시간·이동거리·RAG)이 모두 React로 이관돼 남은 이유가 없어졌다. compose에서 `web` 서비스 삭제, C-04 갱신. |
| v1.9 | 2026-09-01 | FR-14(구종 아스널) 추가. `PitchType`·`SpeedKmh` 첫 활용. 명세 오류 3건을 실데이터로 정정 — `Ball`/`Strike`가 투구 후 카운트, 구종 11종, `W`/`V` 코드. 375px 페이지 오버플로 버그(grid item `min-width:auto`)도 수정. |
| v2.0 | 2026-09-01 | FR-15(볼카운트 야구) 추가. 복원 로직을 `build_pitch_arsenal`에서 import 해 중복 구현을 피했다. 전방 시뮬레이션 교차검증 99.91%. 375px 3개 탭 실측 완료. |
