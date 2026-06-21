# KBO Dashboard

`kbo-dashboard`는 KBO Stat 프로젝트의 백엔드, React 개발용 프론트, Docker 실행 구성을 담고 있습니다.

상위 루트 README가 전체 프로젝트 기준 문서이고, 이 문서는 대시보드 실행에 필요한 내용만 정리합니다.

## 구성

```text
kbo-dashboard/
├── backend/
│   ├── main.py               # FastAPI 앱
│   ├── migrate.py            # CSV -> PostgreSQL 적재
│   ├── migrate_analytics.py  # 분석용 CSV -> PostgreSQL 적재
│   ├── routers/              # API 라우터
│   ├── services/             # 비즈니스 로직
│   ├── models/               # SQLAlchemy 모델
│   └── requirements.txt
├── frontend/                 # React + Vite 개발용 프론트
└── docker-compose.yml
```

## Docker 실행

```bash
cd kbo-dashboard
cp .env.example .env
docker compose up -d --build
```

서비스:

| 서비스 | 주소 |
| --- | --- |
| 웹 | `http://127.0.0.1:8000/web/` |
| FastAPI | `http://127.0.0.1:8001` |
| API 문서 | `http://127.0.0.1:8001/docs` |
| pgAdmin | `http://127.0.0.1:5050` |
| PostgreSQL | `localhost:5433` |

현재 Docker의 `web` 서비스는 `frontend/` React 앱이 아니라 상위 루트의 `web/` 정적 대시보드를 서빙합니다.

## 환경 변수

`kbo-dashboard/.env`:

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

## Backend 로컬 실행

```bash
cd kbo-dashboard/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python migrate.py
python main.py
```

기본 포트는 `8001`입니다.

```bash
curl http://127.0.0.1:8001/health
```

## Frontend 로컬 실행

React/Vite 프론트는 개발 서버로 따로 실행합니다.

```bash
cd kbo-dashboard/frontend
npm install
npm run dev
```

접속:

```text
http://127.0.0.1:3000
```

`frontend/vite.config.js`에서 `/api` 요청을 `http://localhost:8001`로 프록시합니다.

## 주요 API

| API | 설명 |
| --- | --- |
| `GET /api/standings` | DB 기반 팀 순위 |
| `GET /api/schedule` | DB 기반 경기 일정 |
| `GET /api/players/hitters` | DB 기반 타자 리더보드 |
| `GET /api/players/pitchers` | DB 기반 투수 리더보드 |
| `GET /api/team-rank` | CSV/분석 화면용 순위 |
| `GET /api/schedule-games` | CSV/분석 화면용 일정 |
| `GET /api/hitter-metrics` | 타자 파생 지표 |
| `GET /api/player-stats` | 네이버 선수 기록 CSV 기반 API |
| `GET /api/zones` | 핫/콜드존 데이터 |
| `POST /api/rag/ask` | 데이터 기반 RAG 질의 |
| `GET /api/today-story` | OpenAI 기반 오늘 경기 스토리 |

## 데이터 적재

CSV를 PostgreSQL에 적재:

```bash
cd kbo-dashboard/backend
source venv/bin/activate
python migrate.py
```

상위 루트에서 데이터 갱신 후 DB까지 반영:

```bash
cd ../..
python3 src/update_daily.py --year 2026 --players --db
```

## 문제 해결

컨테이너 이름 충돌:

```bash
docker rm -f kbo_web kbo_backend kbo_dashboard_db kbo_pgadmin
docker compose up -d --build
```

`docker-compose` v1의 `ContainerConfig` 오류:

```bash
docker compose up -d --build
```

DB 접속 오류가 나면 `.env`의 `DB_USER`, `DB_PASSWORD`, `DB_NAME`과 `docker-compose.yml`의 healthcheck 값이 같은지 확인하세요.
