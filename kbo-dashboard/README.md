# KBO Dashboard

KBO(한국 야구위원회) 리그 데이터를 시각화하는 대시보드입니다.

## 프로젝트 구조

```
kbo-dashboard/
├── backend/                    # FastAPI
│   ├── main.py
│   ├── requirements.txt
│   ├── migrate.py              # CSV → DB 마이그레이션
│   ├── database/               # DB 연결 설정
│   │   └── __init__.py
│   ├── models/                 # SQLAlchemy ORM 모델
│   │   └── __init__.py
│   ├── routers/
│   │   ├── standings.py        # GET /api/standings
│   │   ├── schedule.py         # GET /api/schedule
│   │   └── players.py          # GET /api/players
│   └── services/
│       ├── standings_service.py
│       ├── schedule_service.py
│       └── player_service.py
│
└── frontend/                   # React + Vite
    └── src/
        ├── pages/
        │   ├── Standings.jsx
        │   └── Schedule.jsx
        └── components/
            └── StandingsTable.jsx
```

## 데이터 흐름

```
PostgreSQL 데이터베이스
        ↓
  service (ORM 쿼리)
        ↓
  router (REST API)
        ↓
  React 프론트엔드
```

## 설치 및 실행

### 1. PostgreSQL 시작 (Docker)

```bash
docker-compose up -d
```

PostgreSQL: `localhost:5432`
PgAdmin: `http://localhost:5050` (admin@example.com / admin)

### 2. Backend 설정

```bash
cd backend

# 환경변수 설정
cp .env.example .env

# 패키지 설치
pip install -r requirements.txt

# CSV 데이터를 DB로 마이그레이션
python migrate.py

# 서버 실행
python main.py
```

서버는 `http://localhost:8000`에서 실행됩니다.
API 문서: `http://localhost:8000/docs`

### 3. Frontend 설정

```bash
cd frontend

# 환경변수 설정
cp .env.example .env

npm install
npm run dev
```

프론트엔드는 `http://localhost:3000`에서 실행됩니다.

## 데이터베이스 스키마

### 테이블

- **teams**: 팀 정보
- **standings**: 팀 순위
- **schedules**: 경기 일정
- **hitters**: 타자 통계
- **pitchers**: 투수 통계

## API 엔드포인트

### 순위표
- `GET /api/standings` - 현재 시즌 순위표
- `GET /api/standings?season=2024` - 특정 시즌 순위표
- `GET /api/standings/KT?season=2024` - 팀별 순위 정보

### 경기 일정
- `GET /api/schedule?season=2024` - 시즌 경기 일정
- `GET /api/schedule?season=2024&team=KT` - 팀별 경기 일정
- `GET /api/schedule/2024-06-01` - 날짜별 경기 일정

### 선수 정보
- `GET /api/players/hitters?season=2024&limit=50` - 타자 순위
- `GET /api/players/pitchers?season=2024&limit=50` - 투수 순위
- `GET /api/players/search/선수명?season=2024` - 선수 검색
- `GET /api/players/team/KT?season=2024&player_type=hitter` - 팀별 선수

## 기술 스택

### Backend
- FastAPI
- SQLAlchemy ORM
- PostgreSQL
- Uvicorn

### Frontend
- React 18
- Vite
- Axios

## 마이그레이션

CSV 데이터를 데이터베이스로 변환:

```bash
cd backend
python migrate.py
```

이 명령은:
1. PostgreSQL 테이블 생성
2. `data/raw/kbo_official/` 폴더의 CSV 파일 읽기
3. 데이터 파싱 및 DB 저장

## 개발 가이드

### 새로운 API 엔드포인트 추가

1. **모델 생성** (`models/__init__.py`)
2. **서비스 작성** (`services/`)
3. **라우터 구현** (`routers/`)
4. **main.py에 라우터 등록**

### CSV 데이터 포함 경로

- 타자 데이터: `/data/raw/kbo_official/kbo_YYYY.csv`
- 투수 데이터: `/data/raw/kbo_official/kbo_pitcher_YYYY.csv`
- 팀 순위: `/data/raw/kbo_official/kbo_team_rank_YYYY.csv`
- 경기 일정: `/data/raw/kbo_official/kbo_schedule_YYYY.csv`

## 라이선스

MIT
