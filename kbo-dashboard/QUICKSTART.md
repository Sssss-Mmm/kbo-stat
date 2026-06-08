# 빠른 시작 가이드

## 1단계: PostgreSQL 시작

```bash
cd kbo-dashboard
docker-compose up -d
```

✅ PostgreSQL이 `localhost:5432`에서 실행됩니다.

## 2단계: Backend 설정

```bash
cd backend

# 환경변수 설정
cp .env.example .env

# 패키지 설치
pip install -r requirements.txt

# CSV 데이터 마이그레이션 (1-2분 소요)
python migrate.py

# 서버 시작
python main.py
```

✅ API 서버: `http://localhost:8000`
✅ API 문서: `http://localhost:8000/docs`

## 3단계: Frontend 설정 (다른 터미널)

```bash
cd frontend

# 환경변수 설정
cp .env.example .env

npm install
npm run dev
```

✅ 프론트엔드: `http://localhost:3000`

## API 테스트

### 순위표 조회
```bash
curl http://localhost:8000/api/standings?season=2026
```

### 팀 순위 조회
```bash
curl "http://localhost:8000/api/standings/KT?season=2026"
```

### 타자 통계 조회
```bash
curl "http://localhost:8000/api/players/hitters?season=2026&limit=10"
```

### 선수 검색
```bash
curl "http://localhost:8000/api/players/search/최원준?season=2026"
```

## 데이터 상태 확인

### PgAdmin으로 DB 확인
- 주소: `http://localhost:5050`
- 이메일: `admin@example.com`
- 비밀번호: `admin`

### 마이그레이션 후 행 수 확인

```bash
# Backend 디렉토리에서
python -c "
from database import SessionLocal
from models import Standing, Hitter, Pitcher

db = SessionLocal()
print(f'순위: {db.query(Standing).count()} 행')
print(f'타자: {db.query(Hitter).count()} 행')
print(f'투수: {db.query(Pitcher).count()} 행')
db.close()
"
```

## 문제 해결

### PostgreSQL 연결 오류
```bash
# Docker 재시작
docker-compose down
docker-compose up -d
```

### 마이그레이션 오류
```bash
# 데이터 경로 확인
ls ../../../data/raw/kbo_official/

# 마이그레이션 재실행
python migrate.py
```

## 다음 단계

1. **프론트엔드 완성**: 선수 페이지, 팀별 상세 페이지 추가
2. **실시간 업데이트**: 크롤러로 신규 데이터 수집
3. **고급 통계**: 선수 비교, 팀 분석 기능
4. **배포**: Docker로 프로덕션 환경 구성
