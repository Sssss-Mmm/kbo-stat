# P2-D 로컬 통합 배포 기록

배포: 2026-10-24 22:43 KST · 범위: `kbo_backend`·`kbo_frontend` 후보 이미지 적용 + 두 컨테이너 재생성. 외부 공개·DB 변경·cron 재활성화·수집 재개·커밋/푸시 없음.

## 1. 배포 전 확인 (전부 충족)

| 항목 | 결과 |
| --- | --- |
| 엔진 | Docker Desktop (`docker-desktop`, 엔진 ID 5340d6af…) |
| 배포 전 컨테이너 | `kbo_backend` 18842f04d673 (이미지 03a2ba9db8f6, v1) · `kbo_frontend` 8324918e5415 (4d86e139c4f5, 정지 — 바인딩 `:3000` 모든 인터페이스) · `kbo_dashboard_db` 2108721417f5 · `kbo_pgadmin` a4d910971201(정지) |
| DB 백업 | 저장소 밖 백업 폴더의 `pre-p2d-2026-10-24-2242.sql.gz` 9.6MB · 27개 테이블 — 역할 없는 빈 PostgreSQL 에 복원, 전 테이블 행 수 운영과 동일 |
| 롤백 이미지 | `kbo-dashboard-backend:rollback-20260922`(03a2ba9d) · `kbo-dashboard-frontend:rollback-20260922`(4d86e139) 보존 |
| 후보 이미지 | `kbo-backend:p2d-cand2` 7d11a1c066de · `kbo-frontend:p2d-cand2` fddcb6501ebd |
| 데이터 | 후보 이미지 + 실제 마운트로 `data_check.py`: `ready — season=2026 mount=mounted` |
| 포트 | 3000 비어 있음(WSL·Windows). 같은 포트를 쓰도록 설정된 다른 컨테이너는 정지 상태이고 자동 시작하지 않음 |
| compose dry-run | `up -d --no-deps --no-build --force-recreate backend frontend` → 두 컨테이너만 재생성, DB·pgAdmin 없음 |

## 2. 배포

```bash
docker tag kbo-backend:p2d-cand2 kbo-dashboard-backend:latest
docker tag kbo-frontend:p2d-cand2 kbo-dashboard-frontend:latest
docker compose -f kbo-dashboard/docker-compose.yml up -d --no-deps --no-build --force-recreate backend   # healthy 확인 후
docker compose -f kbo-dashboard/docker-compose.yml up -d --no-deps --no-build --force-recreate frontend
```

| 컨테이너 | ID | 이미지 | 상태 | 바인딩 |
| --- | --- | --- | --- | --- |
| kbo_backend | 7f6643c24a7d | 7d11a1c066de (p2d-cand2) | healthy(`/ready`) | 127.0.0.1:8001 |
| kbo_frontend | 806c007cbda1 | fddcb6501ebd (p2d-cand2) | running | 127.0.0.1:3000 |
| kbo_dashboard_db | 2108721417f5 (그대로) | 그대로 | healthy, 시작 시각 변화 없음 | 127.0.0.1:5433 |

중단 시간(0.25초 간격 감시): **API 약 3초**(22:43:11–11.5, 22:43:12.8–14.5). 프론트는 배포 전부터 정지 상태였고 22:43:24 부터 서비스.

## 3. 배포 후 검증

| 항목 | 결과 |
| --- | --- |
| `/health` · `/ready` | 200 · 200 (`database: available`, `mount: mounted`, `season: 2026`, problems 없음) — 기동 로그 `[data] ready — season=2026 mount=mounted` |
| v1 API 31개 | 전부 200. 배포 전 운영과 27 동일 — 차이 4: `/ready`(데이터 상태 추가, 의도), `zones`·`player-stats` 2개(부동소수 16자리째, pandas 버전 — 알려진 비회귀) |
| v2 API 19개 | 격리 검증(같은 이미지·같은 데이터의 복원 DB)과 19/19 동일 |
| 화면 30개(1280·390) | 홈 2025/2026 · 순위표 2025/2026 · 일정(2025-09-18 DH, 2026-08) · 박스스코어 · 팀 상세 LG 2025/KT 2026 · 선수 찾기 · 타자/투수 비교 · 존 분석 · 선수 기록 · 선수 상세 — 수치 확인 12건 모두 일치(LG 85-56-3, KT 90-49-5, 홈 41승 1무 29패, 동명이인 4명 등). 가로 넘침: 모바일 존 분석 1건 — 아래 4장 |
| CSV 기반 | 존 분석(2026 타자 표), 선수 기록(364명) 정상 |
| 외부 접근 | WSL 외부 주소·Windows LAN 주소에서 3000·8001·5433 닫힘. Windows 수신은 127.0.0.1 만 |
| 로그 | 백엔드 오류 없음(200 793건, 404 2건 = 회귀 검사의 의도된 '없는 경기'). nginx: 존 분석 큰 응답의 임시 파일 버퍼링 경고만(무해) |
| 운영 제한 | cron PAUSED 유지 · 컨테이너에 수집 승인 환경변수 없음 · DB 미변경 · 다른 프로젝트 컨테이너 미변경 |

## 4. 재발 방지 (운영과 같은 이미지 7d11a1c0, 격리 컨테이너)

| 상황 | 결과 |
| --- | --- |
| 마운트가 늦게 준비됨 | 재시작 2회 뒤 healthy, `/ready` 200 |
| 마운트가 계속 준비 안 됨(tmpfs) | 재시작 4회 뒤 대기, 20초 뒤에도 4회 — 무한 재시작 없음, unhealthy |
| 실행 중 필수 파일 제거/헤더만/복구 | `/ready` 503 `missing` → 503 `empty` → 200 — 실제 데이터 상태를 그대로 반영 |

운영 컨테이너로는 재현하지 않았다(재시작 필요). 실제 Docker Desktop 재시작 때 `docker logs kbo_backend` 의 `[data]` 줄로 확인한다.

## 5. 롤백 (필요 시)

```bash
docker tag kbo-dashboard-backend:rollback-20260922 kbo-dashboard-backend:latest
docker tag kbo-dashboard-frontend:rollback-20260922 kbo-dashboard-frontend:latest
docker compose -f kbo-dashboard/docker-compose.yml up -d --no-deps --no-build --force-recreate backend frontend
```
DB 는 이번 배포로 바뀌지 않았다(롤백에 DB 복원 불필요). 롤백 프론트는 compose 설정상 127.0.0.1:3000 으로 다시 만들어진다.

## 6. 남은 위험

- **모바일 존 분석 가로 넘침(기존)**: 390px 에서 히트맵 칸이 36px 넘친다. 이전 프론트 이미지(rollback)에서도 똑같이 426px — 이번 배포의 회귀가 아니다. 미수정.
- **재부팅 시 마운트 경합**: 이제 자가 복구·대기로 막지만, Desktop 재시작으로는 아직 실측하지 않았다.
- **3000 포트 충돌 가능성**: 같은 포트를 쓰는 다른 로컬 컨테이너를 켜면 KBO 프론트와 충돌한다(먼저 뜬 쪽이 이김).
- **이용 권한**: 모든 자료가 자동 수집분 — 외부 공개 금지(로컬 바인딩으로만 막음, API 인증 없음).
- `start_kbo.sh` 의 외부 바인딩 검사는 이제 통과한다(프론트가 127.0.0.1 로 재생성됨). cron 은 계속 멈춰 있다.
