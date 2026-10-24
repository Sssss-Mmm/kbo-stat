# 배포 준비 보고 — 백엔드 v2 · 프론트엔드 (운영 교체 전, 승인 대기)

작성: 2026-10-24 · 운영 컨테이너 교체·외부 공개·커밋/푸시는 하지 않았다.

## 1. 조건 점검

| 조건 | 결과 |
| --- | --- |
| DB 백업 | `pg_dump` 9.7MB(25개 테이블 = public 13 + 신규 12), gzip 무결성 OK. **이 파일로 임시 DB 를 복원**해 행 수가 운영과 같음을 확인(teams 23 · hitters 1,926 · schedule_games 17,257 · raw 720 · build 15) — 백업 복원 가능 |
| v1/v2 API 회귀 | 운영(현 이미지·운영 DB) vs 후보(새 이미지·복원 DB) v1 31개 경로 대조: 26개 본문 동일, 5개 차이는 회귀 아님 — `today-story`(시각 의존), `schedule-games`(같은 행, 정렬 없는 쿼리라 순서만 다름), `player-stats`·`zones`(같은 행, 부동소수 16자리째 차이 = pandas 3.0.6→3.1.0). 후보 이미지 안 백엔드 테스트 86개(PostgreSQL 통합 포함) 통과 |
| 프론트 주요 경로 | 후보 nginx 로 v1·v2 14개 경로 200(SPA 폴백), 없는 asset 404, `/api` 프록시 동작. 리더보드(규정타석·참고 순위)·순위표·일정 화면 캡처 확인 |
| 롤백 준비 | 현재 이미지를 `kbo-dashboard-backend:rollback-20260922`(03a2ba9d), `kbo-dashboard-frontend:rollback-20260922`(4d86e139) 로 태그 고정 |
| 재생성·DB 중단 영향 | 아래 명령의 dry-run: 백엔드 교체는 `kbo_backend` 만, 프론트 교체는 `kbo_frontend` 만 재생성 — **DB 컨테이너는 건드리지 않는다**. API 는 재생성 동안(수 초) 중단 |

## 2. 교체 절차(승인 후)

```bash
cd ~/kbo-stat
# 0) 직전 백업
docker exec kbo_dashboard_db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > backup-$(date +%F-%H%M).sql.gz
# 1) 후보 이미지를 compose 서비스 이미지 이름으로
docker tag kbo-backend:p2a-candidate kbo-dashboard-backend:latest
docker tag kbo-frontend:p2b-candidate kbo-dashboard-frontend:latest
# 2) 서비스별 교체(DB 는 건드리지 않음)
docker compose -f kbo-dashboard/docker-compose.yml up -d --no-deps --no-build --force-recreate backend
curl -fsS http://127.0.0.1:8001/ready && curl -fsS "http://127.0.0.1:8001/api/v2/data-quality?season=2025" >/dev/null
docker compose -f kbo-dashboard/docker-compose.yml up -d --no-deps --no-build --force-recreate frontend
curl -fsS http://127.0.0.1:3000/ >/dev/null
```

## 3. 롤백

```bash
docker tag kbo-dashboard-backend:rollback-20260922 kbo-dashboard-backend:latest
docker tag kbo-dashboard-frontend:rollback-20260922 kbo-dashboard-frontend:latest
docker compose -f kbo-dashboard/docker-compose.yml up -d --no-deps --no-build --force-recreate backend frontend
```

DB 는 교체로 바뀌지 않는다(v2 스키마는 이미 적재돼 있고, 옛 이미지는 그 스키마를 읽지 않는다). DB 롤백이 필요한 경우에만 백업 복원.

## 4. 교체 전 권장

- **의존성 고정**: `kbo-dashboard/backend/requirements.txt` 가 pandas·numpy·fastapi 를 버전 없이 받아 빌드마다 바뀐다
  (이번 후보: pandas 3.1.0 · fastapi 0.161.1 · numpy 2.5.4 — 운영 이미지는 3.0.6 · 0.141.1 · 2.5.3). 테스트한 버전으로 고정(lock)한 뒤 다시 빌드하는 것이 안전하다.
- `schedule-games` 등 정렬 없는 v1 쿼리는 DB 물리 순서에 따라 결과 순서가 바뀐다(기존 동작). 화면이 정렬해서 쓰는지 확인 필요.
- 이 준비 중 독립 환경 포트 중계용으로 공개 이미지 `alpine/socat` 를 한 번 받았다가 바로 지웠다(쓰지 않음).

## 5. 운영 상태(변경 없음)

`kbo_backend`(v1 이미지)·`kbo_dashboard_db` 그대로 실행 중, 일일 cron 중단 유지, KBO·네이버 자동 수집 차단 유지.
