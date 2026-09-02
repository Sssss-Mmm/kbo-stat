# KBO Stat

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-DB-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)

KBO 데이터를 수집, 정제, 저장하고 웹 대시보드로 시각화하는 야구 데이터 프로젝트입니다.

화면은 `kbo-dashboard/frontend/`의 React + Vite 대시보드 하나이며 Docker Compose가 `:3000`으로 서빙합니다.
1세대 정적 대시보드(`web/`)는 전용 화면이 모두 React로 옮겨져 제거됐습니다.
백엔드는 `kbo-dashboard/backend`의 FastAPI가 담당하고, 데이터는 `data/` 아래 CSV와 PostgreSQL을 함께 사용합니다.

## 문서

기획·요구사항·조사 결과는 `docs/`에 있습니다.

| 문서 | 내용 |
| --- | --- |
| [docs/PLAN.md](docs/PLAN.md) | 기획서 — 무엇을 왜 만드는가, 범위, 로드맵, 리스크 |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | 요구사항 정의서 — FR/DR/NFR을 ID 단위로, 각 항목의 수용 기준과 검증 결과 |
| [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md) | 목표 사이트 대비 격차 분석 — 무엇을 우리 데이터로 만들 수 있고 무엇이 원천적으로 불가한가 |
| [docs/IDEAS.md](docs/IDEAS.md) | 아이디어 후보와 채택/기각 근거 |
| [docs/BACKFILL_PITCH_DATA.md](docs/BACKFILL_PITCH_DATA.md) | 네이버 투구 데이터 백필 절차 |

## 주요 기능

React 앱은 네비게이션 **9개 페이지**로 구성됩니다.

| 페이지 | 내용 |
| --- | --- |
| HOME | 오늘 경기 카드(스코어·선발·**AI 프리뷰/리뷰**), 시즌 요약 6카드, 타이틀 레이스(순위 변화), 팀 순위, 홈/원정 성적, 리그 타격·투구 평균, QS%·BB/K·K/BB·팀 득실차, OPS 분포(beeswarm), 산점도 4종(ISO×AVG · OBP×SLG · BB×SO · WHIP×ERA), 홈런 경쟁, 리더 3종(OPS·ERA·도루), 운영 요약(관중·평균 경기시간), 야구 규칙 가이드 |
| 순위표 | 12열(순위·팀·경기·승·패·무·승률·게임차·최근10·연속·홈·원정), 열 헤더 클릭 정렬, **팀명 클릭 시 팀 분석 페이지로 이동** |
| 가을야구 | 잔여 경기·매직넘버/트래직넘버·자력 진출 여부, 5위와의 승차, 피타고리안 기대승률, 순위 곡선, 진출 경쟁팀 맞대결. **확정 산수만 — 진출 확률·시뮬레이션은 비목표** |
| 리그 운영 | 연도별 평균 경기시간 **1982~2026(45시즌)**, 구단별 관중·경기시간, 월별 관중. 수집 안 된 항목은 화면에 그 사실을 밝힘 |
| 질문하기 | 자연어 질문 → 수집 CSV에서 검색한 **근거 표와 함께** 답변. 근거가 없으면 그 사실을 경고로 알림 |
| 팀 분석 | 팀 선택 후 시즌 순위 변화 라인, 월별 승/패/승률, 홈/원정 비교 |
| 경기일정 | 월 단위 달력, 팀 칩 필터(선택 시 그 팀 관점 vs/@ 상대·승패로 전환) |
| 선수 기록 | 타자 20열 · 투수 20열 표, 팀 필터·규정충족 필터, 헤더 클릭 정렬 |
| 핫/콜드존 | 네이버 투구 좌표를 **5×5 격자**로 재집계한 히트맵(타자 타율 / 투수 피안타율), 존별 표본 수 함께 노출 |

백엔드에만 있고 React 화면이 없는 기능:

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| 데이터 수집 | Python, pandas, requests, BeautifulSoup |
| 백엔드 | FastAPI, SQLAlchemy, PostgreSQL |
| 프론트 | React, Vite |
| 시각화 | SVG, CSS, 자체 차트 컴포넌트 |
| 인프라 | Docker, nginx, cron |
| AI | OpenAI API |

## 프로젝트 구조

```text
kbo-stat/
├── docs/                     # 기획서·요구사항·격차 분석
├── data/
│   ├── raw/                  # 원천 CSV
│   └── processed/            # 가공 CSV (1차 진실)
├── src/
│   ├── crawl_*.py            # KBO/네이버/Statiz 크롤러
│   ├── build_*.py            # 가공 데이터 생성
│   ├── csv_guard.py          # 0행 저장 거부 + 정합성 검사(V-01~08)
│   └── update_daily.py       # 일일 업데이트 엔트리포인트
├── scripts/
│   ├── start_kbo.sh          # 스택 기동 + 놓친 갱신 캐치업
│   └── update_kbo_daily.sh   # cron 자동 업데이트 스크립트
└── kbo-dashboard/
    ├── backend/              # FastAPI API 서버
    ├── frontend/             # React + Vite (Docker로도 서빙, :3000)
    └── docker-compose.yml
```

## 사전 준비물

- Python 3.12+
- Node.js 18+ (React 프론트 로컬 개발 시. Docker로만 쓸 거면 불필요)
- Docker / Docker Compose v2 (권장 실행 방식)
- PostgreSQL (Docker 사용 시 컨테이너로 자동 제공)

데이터 파이프라인용 의존성은 루트의 `requirements.txt`, 백엔드 의존성은 `kbo-dashboard/backend/requirements.txt`에 정의되어 있습니다.

## 빠른 실행

`kbo-dashboard/.env`를 먼저 만듭니다(아래 [환경 변수](#환경-변수) 참고). 그다음:

```bash
bash scripts/start_kbo.sh
```

`start_kbo.sh`는 스택을 띄우고, 오늘자 갱신이 아직 안 됐으면(PC가 02:00에 꺼져 있었던 경우 등)
백그라운드로 캐치업 갱신을 1회 실행합니다. 캐치업이 필요 없으면 compose를 직접 써도 됩니다.

```bash
cd kbo-dashboard
docker compose up -d --build
```

접속 주소:

- **React 대시보드: `http://127.0.0.1:3000`** (주 화면)
- 백엔드 API: `http://127.0.0.1:8001`
- API 문서: `http://127.0.0.1:8001/docs`
- pgAdmin: `http://127.0.0.1:5050`
- PostgreSQL: `localhost:5433`

`docker-compose` v1에서 `ContainerConfig` 오류가 나면 v2 명령(`docker compose`)을 사용하세요.

기존 컨테이너 이름 충돌이 나면 아래처럼 정리 후 다시 실행합니다.

```bash
docker rm -f kbo_frontend kbo_backend kbo_dashboard_db kbo_pgadmin
cd kbo-dashboard
docker compose up -d --build
```

## 환경 변수

Docker compose는 `kbo-dashboard/.env`를 사용합니다. 이 파일은 커밋되지 않으므로 직접 만듭니다.

```env
# PostgreSQL (필수)
DB_USER=kbo_user
DB_PASSWORD=CHANGE_ME
DB_NAME=kbo_dashboard

# pgAdmin (필수 — 컨테이너 기동에 사용)
PGADMIN_EMAIL=admin@example.com
PGADMIN_PASSWORD=CHANGE_ME

# AI 스토리 (선택)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
```

`OPENAI_API_KEY`가 없으면 AI 스토리 기능은 mock 응답으로 동작합니다(에러가 아닙니다).

## 데이터 갱신

기본 갱신은 순위, 일정, 결과, 관중, 경기시간, 타자 파생지표를 업데이트합니다.
`--year`를 생략하면 KST 기준 현재 연도를 씁니다.

```bash
python3 src/update_daily.py --year 2026
```

선수 리더보드와 현재 등록 선수 명단까지 갱신:

```bash
python3 src/update_daily.py --year 2026 --players
```

등록 선수 명단만 갱신:

```bash
python3 src/update_daily.py --registered-players
```

네이버 투구 존 데이터 갱신(`--pitch-date` 생략 시 KST 오늘):

```bash
python3 src/update_daily.py --pitch-zones --pitch-date 2026-06-21
```

CSV 갱신 후 PostgreSQL까지 적재:

```bash
python3 src/update_daily.py --year 2026 --players --db
```

> 투구 존 **가공** 데이터(`kbo_*_zones_*.csv`)는 `src/build_zone_metrics.py --year 2026`이 따로 만듭니다.
> 격자 크기는 같은 파일의 `GRID_N` 상수(현재 5)이며, 안쪽 3×3이 스트라이크존, 바깥 테두리 한 겹이 존 밖을 전부 흡수합니다.
> 과거 날짜 대량 수집은 [docs/BACKFILL_PITCH_DATA.md](docs/BACKFILL_PITCH_DATA.md)를 따르세요.

모든 CSV 저장은 `src/csv_guard.py`를 경유합니다. 출처 구조가 바뀌어 파서가 빈 결과를 뱉으면
0행 저장을 거부해 기존 CSV를 지키고, 행 수가 맞아도 값이 깨진 경우는 정합성 규칙 V-01~08로 거부합니다.

```bash
python3 src/csv_guard.py        # 자체 점검 (0행 거부 · V-01~08 위반 샘플 거부 · 운영 CSV 통과)
```

## 자동 업데이트

`scripts/update_kbo_daily.sh`를 cron에 등록해 매일 **02:00 KST**에 자동 갱신합니다.

```cron
0 2 * * * cd /home/sssssmmm/kbo-stat && PYTHON_BIN=/usr/bin/python3 scripts/update_kbo_daily.sh >> logs/update_kbo_daily.log 2>&1
```

스크립트가 하는 일: 공식 순위·일정·관중·경기시간·선수 → 네이버 시즌 기록 → 네이버 투구 데이터(직전 2일) →
존 지표 재생성 → **DB 재적재**(`migrate.py`). `flock`으로 중복 실행을 막고, DB 적재가 실패하면
exit 3/4로 종료합니다(CSV만 최신이고 DB가 낡은 채로 조용히 성공하지 않게).

동작 확인만 하려면:

```bash
DRY_RUN=1 bash scripts/update_kbo_daily.sh
```

## 백업과 복구

**DB는 백업 대상이 아닙니다.** `data/processed/*.csv`가 1차 진실이고, DB는 언제든 재생성 가능한 서빙용 사본입니다.

- `data/`는 호스트 디렉터리이고 compose가 `../data:/app/data`로 bind mount 하므로 컨테이너를 지워도 남습니다.
- DB 볼륨이 완전히 소실돼도 `migrate.py` 한 번이면 CSV에서 전량 복구됩니다.
- `migrate.py`는 시즌별 delete-after-insert 방식이라 몇 번을 돌려도 결과가 같습니다(멱등).
- 컨테이너 최초 기동 시 DB가 비어 있으면 `seed_if_empty.py`가 자동 시드합니다.

```bash
# DB 전량 복구 (컨테이너 기동 상태에서)
cd kbo-dashboard
docker compose exec -T backend python migrate.py
```

CSV만 갱신하고 재적재를 안 하면 화면은 옛 데이터를 보여줍니다. 수동 갱신 시에는 `--db`나 위 명령을 함께 실행하세요.
실제 재적재로 `team-rank-history` 40 → 250행, `team-games` 630 → 1152행이 되어 CSV와 일치함을 확인했습니다.

## 백엔드 로컬 실행

```bash
cd kbo-dashboard/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python migrate.py
python main.py
```

서버:

```text
http://127.0.0.1:8001
```

대표 API:

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/standings
curl http://127.0.0.1:8001/api/schedule-games
curl "http://127.0.0.1:8001/api/player-stats?role=hitter&season=2026"
curl "http://127.0.0.1:8001/api/zones?role=batter&season=2026"
```

RAG 질의:

```bash
curl -X POST http://127.0.0.1:8001/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"왜 한화가 강하지?","season":2026}'
```

오류 응답은 `{"detail": "..."}` 형식입니다 — 400(파라미터 값 오류) · 404(없는 시즌·팀·선수) ·
502(외부 출처 조회 실패) · 503(DB 연결 불가). 비시즌처럼 "아직 데이터가 없음"은 오류가 아니라 200 + 빈 배열입니다.

## React 프론트 로컬 실행

Docker로 이미 `:3000`에 서빙되므로, 아래는 HMR이 필요한 개발 시에만 필요합니다.

```bash
cd kbo-dashboard/frontend
npm install
npm run dev
```

접속:

```text
http://127.0.0.1:3000
```

Vite 개발 서버는 `/api` 요청을 `http://localhost:8001`로 프록시합니다
(Docker 빌드본은 nginx가 `backend:8001`로 프록시).

## 데이터 출처

이 프로젝트는 학습 및 포트폴리오 목적으로 만들어졌습니다.

- KBO 공식 사이트
- 네이버 스포츠
- Statiz

일부 데이터는 공식 문서화된 공개 API가 아니라 웹 페이지와 내부 응답 구조를 기반으로 수집합니다. 출처의 구조가 바뀌면 크롤러가 동작하지 않을 수 있으며, 모든 데이터의 권리는 각 원 출처에 있습니다.

## 라이선스

현재 별도 라이선스 파일이 없습니다. 학습 및 포트폴리오 용도로 사용하세요. <!-- TODO: LICENSE 파일 추가 -->
수집 데이터의 권리는 각 원 출처(KBO, 네이버 스포츠, Statiz)에 있습니다.

## 현재 주의할 점

- **백엔드 코드는 이미지에 COPY됩니다.** 소스 볼륨 마운트가 아니라서 `docker compose restart backend`로는
  코드 변경이 반영되지 않습니다. `docker compose up -d --build backend`를 쓰세요.
- CSV를 갱신해도 DB 기반 API에는 바로 반영되지 않습니다. 필요하면 `--db` 또는 `migrate.py`를 함께 실행하세요.
- 시즌 셀렉터는 최근 10년을 나열하지만 **팀 순위 CSV는 2026 시즌만** 있습니다.
  과거 45시즌(1982~2026)에 있는 것은 팀 순위가 아니라 **선수 리더보드**(`data/raw/kbo_official/kbo_{연도}.csv`)입니다.
  `migrate.py`도 2020~2026 7시즌만 적재합니다.
- 선수 기록 API는 데이터 파일 종류에 따라 리더보드 선수만 보일 수 있습니다.
  전체 등록 선수 명단은 `python3 src/update_daily.py --registered-players`(또는 `--players`)로 갱신합니다.
- 백엔드 엔드포인트 25개 중 12개는 아직 React 화면에서 쓰이지 않습니다(대부분 클라이언트 필터 방식을 택해 중복이 된 서버측 검색·필터입니다. 사유는 `docs/REQUIREMENTS.md` 5절).

## 앞으로 할 일

`docs/PLAN.md` 6절 로드맵과 `docs/REQUIREMENTS.md` 8절 미달 항목이 정본입니다. 요약하면:

v1 `필수` 항목은 전부 충족됐습니다. 남은 것은 `권장`·`선택` 등급입니다.

- **RAG 의도 분기 확장**(PLAN T11) — 지금은 키워드 3갈래뿐이라 "왜 한화가 강하지?" 같은 인과형 질문과
  홈/원정·투수·월별 질문에 답하지 못합니다. 근거 없는 단정은 막았지만 답변 범위 자체가 좁습니다
- **선수/팀 비교**(FR-10), **미사용 엔드포인트 정리**(PLAN T9), **갱신 실패 알림**(PLAN T7 잔여)
- **과거 시즌 확장** — `migrate.py`가 2020~2026만 적재합니다
- 미측정 항목: 화면 로딩 시간(NFR-02), DB 복구 소요 시간(NFR-17), 파서 자체 점검(NFR-18)
