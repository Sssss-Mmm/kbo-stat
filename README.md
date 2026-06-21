# KBO Stat

KBO 데이터를 수집, 정제, 저장하고 웹 대시보드로 시각화하는 야구 데이터 프로젝트입니다.

현재 프로젝트는 두 가지 화면을 함께 가지고 있습니다.

- `web/`: Docker에서 기본으로 서빙되는 정적 대시보드
- `kbo-dashboard/frontend/`: React + Vite 개발용 대시보드

백엔드는 `kbo-dashboard/backend`의 FastAPI가 담당하고, 데이터는 `data/` 아래 CSV와 PostgreSQL을 함께 사용합니다.

## 주요 기능

- 오늘의 KBO: 오늘 경기, 순위, 최근 흐름, 주요 선수 카드
- 순위표: 팀 순위, 승률, 게임차, 최근 10경기 흐름
- 경기 일정: KBO 일정/결과 데이터 조회
- 팀 분석: 순위 변화, 월별 승률, 득점/실점, 홈/원정 비교
- 선수 분석: 타자/투수 기록, 등록 선수 명단, 검색
- 핫/콜드존: 네이버 경기센터 투구 데이터를 활용한 존 분석 기반 데이터
- AI 스토리: OpenAI API를 이용한 경기 프리뷰/리뷰 생성
- RAG 데모: 수집된 야구 데이터를 근거로 질문에 답하는 분석 API

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| 데이터 수집 | Python, pandas, requests, BeautifulSoup |
| 백엔드 | FastAPI, SQLAlchemy, PostgreSQL |
| 프론트 | Vanilla JS, React, Vite |
| 시각화 | SVG, CSS, 자체 차트 컴포넌트 |
| 인프라 | Docker, nginx, cron |
| AI | OpenAI API |

## 프로젝트 구조

```text
kbo-stat/
├── data/
│   ├── raw/                  # 원천 CSV
│   └── processed/            # 가공 CSV
├── src/
│   ├── crawl_*.py            # KBO/네이버/Statiz 크롤러
│   ├── build_*.py            # 가공 데이터 생성
│   └── update_daily.py       # 일일 업데이트 엔트리포인트
├── scripts/
│   └── update_kbo_daily.sh   # cron 자동 업데이트 스크립트
├── web/                      # Docker 기본 웹 화면
│   ├── index.html
│   ├── *.js
│   ├── styles.css
│   ├── Dockerfile
│   └── nginx.conf
└── kbo-dashboard/
    ├── backend/              # FastAPI API 서버
    ├── frontend/             # React + Vite 개발용 프론트
    └── docker-compose.yml
```

## 빠른 실행

Docker 기준 실행이 가장 쉽습니다.

```bash
cd kbo-dashboard
cp .env.example .env
docker compose up -d --build
```

접속 주소:

- 웹: `http://127.0.0.1:8000/web/`
- 백엔드 API: `http://127.0.0.1:8001`
- API 문서: `http://127.0.0.1:8001/docs`
- pgAdmin: `http://127.0.0.1:5050`
- PostgreSQL: `localhost:5433`

`docker-compose` v1에서 `ContainerConfig` 오류가 나면 v2 명령을 사용하세요.

```bash
docker compose up -d --build
```

기존 컨테이너 이름 충돌이 나면 아래처럼 정리 후 다시 실행합니다.

```bash
docker rm -f kbo_web kbo_backend kbo_dashboard_db kbo_pgadmin
cd kbo-dashboard
docker compose up -d --build
```

## 환경 변수

Docker compose는 `kbo-dashboard/.env`를 사용합니다.

```bash
cd kbo-dashboard
cp .env.example .env
```

예시:

```env
DB_USER=kbo_user
DB_PASSWORD=CHANGE_ME
DB_NAME=kbo_dashboard

PGADMIN_EMAIL=admin@example.com
PGADMIN_PASSWORD=CHANGE_ME

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
```

`OPENAI_API_KEY`가 없으면 AI 스토리 기능은 mock 응답으로 동작합니다.

## 데이터 갱신

기본 갱신은 순위, 일정, 결과, 관중, 경기시간, 타자 파생지표를 업데이트합니다.

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

네이버 투구 존 데이터 갱신:

```bash
python3 src/update_daily.py --pitch-zones --pitch-date 2026-06-21
```

CSV 갱신 후 PostgreSQL까지 적재:

```bash
python3 src/update_daily.py --year 2026 --players --db
```

## 자동 업데이트

`scripts/update_kbo_daily.sh`를 cron에 등록해 매일 자동 갱신할 수 있습니다.

```cron
30 1 * * * cd /home/sssssmmm/kbo-stat && PYTHON_BIN=/usr/bin/python3 scripts/update_kbo_daily.sh >> logs/update_kbo_daily.log 2>&1
```

스크립트는 `flock`으로 중복 실행을 방지합니다.

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
```

RAG 질의:

```bash
curl -X POST http://127.0.0.1:8001/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"왜 한화가 강하지?","season":2026}'
```

## React 프론트 로컬 실행

React 앱은 Docker 기본 화면이 아니라 개발용 프론트입니다.

```bash
cd kbo-dashboard/frontend
npm install
npm run dev
```

접속:

```text
http://127.0.0.1:3000
```

Vite 개발 서버는 `/api` 요청을 `http://localhost:8001`로 프록시합니다.

## 데이터 출처

이 프로젝트는 학습 및 포트폴리오 목적으로 만들어졌습니다.

- KBO 공식 사이트
- 네이버 스포츠
- Statiz

일부 데이터는 공식 문서화된 공개 API가 아니라 웹 페이지와 내부 응답 구조를 기반으로 수집합니다. 출처의 구조가 바뀌면 크롤러가 동작하지 않을 수 있으며, 모든 데이터의 권리는 각 원 출처에 있습니다.

## 현재 주의할 점

- Docker의 기본 `web` 서비스는 `web/` 정적 대시보드를 서빙합니다.
- `kbo-dashboard/frontend` React 앱은 별도 개발 서버로 실행해야 합니다.
- 선수 기록 API는 데이터 파일 종류에 따라 리더보드 선수만 보일 수 있습니다.
- 전체 등록 선수 명단은 `src/update_daily.py --registered-players` 또는 `--players`로 갱신합니다.
- CSV를 갱신해도 DB 기반 API에는 바로 반영되지 않을 수 있으므로 필요하면 `--db`를 함께 실행하세요.

## 앞으로 할 일

- Docker 기본 프론트를 React 앱으로 통일
- 등록 선수 API 정식 추가
- 핫/콜드존 가공 파이프라인 정리
- 선수 비교, 팀 비교, AI 분석 챗봇 고도화
- README와 요구사항 정의서 기준 기능 체크리스트 동기화
