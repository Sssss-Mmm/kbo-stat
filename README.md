# AI Baseball Lab

KBO 데이터를 Visual Baseball 스타일로 탐색하는 시각화 서비스 프로토타입입니다.
일정, 순위, 타자/투수 기록, 관중, 평균 경기시간, AI 분석 데모를 제공합니다.

## Pages

Docker/nginx 실행 시 클린 URL을 사용할 수 있습니다.

| URL | 설명 |
| --- | --- |
| `/schedule#2026` | KBO 일정/결과 |
| `/standings` | 팀 순위, 득실차, 최근 10경기 흐름 |
| `/batting` | 타자 순위표 |
| `/pitching` | 투수 순위표 |
| `/distance` | 원정 경기/방문 구장 기반 이동 부담 |
| `/attendance` | KBO 공식 구단별 관중 현황 |
| `/gametime` | KBO 공식 평균 경기시간 |
| `/lab` | CSV 기반 AI 야구 분석 데모 |

정적 서버로 실행할 때는 `.html` 경로로 접속합니다.

```text
http://127.0.0.1:8000/web/schedule.html#2026
http://127.0.0.1:8000/web/standings.html
```

## Docker 실행

현재 WSL 환경의 `docker-compose 1.29.2`는 Docker 최신 버전과 충돌해
`ContainerConfig` 에러가 날 수 있습니다. 이 경우 컨테이너를 새로 만들기보다
기존 컨테이너를 시작하거나, 필요한 컨테이너만 제거 후 재생성하세요.

### 처음 빌드

```bash
cd /home/sssssmmm/kbo-stat

docker build -t kbo-dashboard-web:latest -f web/Dockerfile .
docker build -t kbo-dashboard-backend:latest -f kbo-dashboard/backend/Dockerfile .
```

### 컨테이너 시작

```bash
docker start kbo_dashboard_db kbo_backend kbo_web
```

컨테이너가 없거나 이름 충돌이 날 때:

```bash
docker rm -f kbo_web kbo_backend 2>/dev/null || true

docker run -d --name kbo_web \
  --network kbo-dashboard_kbo_network \
  -p 8000:80 \
  kbo-dashboard-web:latest

docker run -d --name kbo_backend \
  --network kbo-dashboard_kbo_network \
  -p 8001:8001 \
  -e DATABASE_URL=postgresql://kbo_user:kbo_password@kbo_dashboard_db:5432/kbo_dashboard \
  kbo-dashboard-backend:latest
```

PostgreSQL이 없으면:

```bash
cd kbo-dashboard
docker-compose up -d postgres pgadmin
```

### 접속

```text
http://127.0.0.1:8000/schedule#2026
http://127.0.0.1:8000/standings
http://127.0.0.1:8000/batting
http://127.0.0.1:8000/pitching
http://127.0.0.1:8000/attendance
http://127.0.0.1:8000/gametime
```

WSL에서 Windows 브라우저의 `127.0.0.1` 접속이 불안정하면 WSL IP를 사용하세요.

```bash
hostname -I
```

예:

```text
http://<WSL_IP>:8000/schedule#2026
```

### nginx 설정만 변경했을 때

```bash
docker cp web/nginx.conf kbo_web:/etc/nginx/conf.d/default.conf
docker exec kbo_web nginx -t
docker exec kbo_web nginx -s reload
```

## Docker 없이 로컬 테스트

nginx 클린 URL은 사용할 수 없고, `.html` 파일로 접속합니다.

```bash
cd /home/sssssmmm/kbo-stat
python3 -m http.server 8000
```

```text
http://127.0.0.1:8000/web/schedule.html#2026
http://127.0.0.1:8000/web/standings.html
http://127.0.0.1:8000/web/attendance.html
```

## 데이터 업데이트

빠른 일일 업데이트:

```bash
python3 src/update_daily.py --year 2026
```

타자/투수 리더보드까지 포함:

```bash
python3 src/update_daily.py --year 2026 --players
```

현재 KBO 등록 선수 전체만 갱신:

```bash
python3 src/update_daily.py --registered-players
```

네이버 경기센터 투구 위치 데이터까지 포함:

```bash
python3 src/update_daily.py --year 2026 --pitch-zones
python3 src/update_daily.py --year 2026 --pitch-zones --pitch-date 2026-06-10
```

개별 크롤러:

```bash
python3 src/crawl_kbo_schedule.py --year 2026
python3 src/crawl_kbo_team_rank.py --year 2026
python3 src/crawl_kbo_attendance.py --year 2026
python3 src/crawl_kbo_game_time.py --year 2026
python3 src/crawl_kbo_hitter.py --start 2026 --end 2026 --overwrite
python3 src/crawl_kbo_pitcher.py --start 2026 --end 2026 --overwrite
python3 src/crawl_kbo_players.py
python3 src/crawl_naver_pitch_zones.py --date 2026-06-10
```

생성/갱신되는 주요 파일:

```text
data/raw/kbo_official/kbo_schedule_2026.csv
data/raw/kbo_official/kbo_team_rank_2026.csv
data/raw/kbo_official/kbo_team_rank_history_2026.csv
data/raw/kbo_official/kbo_attendance_2026.csv
data/raw/kbo_official/kbo_attendance_monthly_2026.csv
data/raw/kbo_official/kbo_game_time_team_2026.csv
data/raw/kbo_official/kbo_game_time_yearly.csv
data/raw/kbo_official/kbo_registered_players_latest.csv
data/raw/naver/naver_kbo_pitches_2026-06-10.csv
data/raw/naver/naver_kbo_zone_summary_2026-06-10.csv
data/processed/kbo_team_games_2026.csv
data/processed/kbo_team_monthly_2026.csv
data/processed/kbo_hitter_metrics_2026.csv
```

네이버 pitch-zone CSV는 공식 문서화된 API가 아니라 네이버 스포츠 경기센터가
사용하는 공개 응답을 기반으로 합니다. 구조가 바뀔 수 있으니 포트폴리오에서는
데이터 출처와 수집 기준을 명시하세요.

Docker 웹 컨테이너에 최신 CSV를 반영하려면 웹 이미지를 다시 빌드하거나 파일을 복사합니다.

```bash
docker build -t kbo-dashboard-web:latest -f web/Dockerfile .
docker rm -f kbo_web
docker run -d --name kbo_web --network kbo-dashboard_kbo_network -p 8000:80 kbo-dashboard-web:latest
```

## RAG Backend

FastAPI 백엔드는 CSV 기반 RAG API를 제공합니다.

```bash
cd kbo-dashboard/backend
venv/bin/python main.py
```

API:

```text
http://127.0.0.1:8001
```

질문:

```bash
curl -X POST http://127.0.0.1:8001/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"왜 한화가 강하지?","season":2026}'
```

검색:

```bash
curl "http://127.0.0.1:8001/api/rag/search?query=MVP&season=2026"
```

## 자동 업데이트

일일 업데이트 스크립트는 KBO 공식 데이터와 네이버 pitch-zone 데이터를 함께 갱신합니다.
네이버 투구 위치 데이터는 경기 지연/연장 반영을 위해 기본적으로 어제와 그제 데이터를 다시 수집합니다.

수동 실행:

```bash
cd /home/sssssmmm/kbo-stat
scripts/update_kbo_daily.sh >> logs/update_kbo_daily.log 2>&1
```

cron 등록:

```bash
mkdir -p logs
crontab -e
```

매일 새벽 1시 30분 KST 실행:

```cron
30 1 * * * cd /home/sssssmmm/kbo-stat && PYTHON_BIN=/usr/bin/python3 scripts/update_kbo_daily.sh >> logs/update_kbo_daily.log 2>&1
```

로그 확인:

```bash
tail -100 logs/update_kbo_daily.log
```

중복 실행은 `logs/update_kbo_daily.lock` 파일 기반 `flock`으로 방지합니다.

공식 데이터와 pitch-zone 수집 시간을 분리하고 싶으면:

```cron
0 9 * * * cd /home/sssssmmm/kbo-stat && /usr/bin/python3 src/update_daily.py --year $(date +\%Y) >> logs/daily_update.log 2>&1
30 1 * * * cd /home/sssssmmm/kbo-stat && /usr/bin/python3 src/crawl_naver_pitch_zones.py --from-date $(date -d '2 days ago' +\%F) --to-date $(date -d yesterday +\%F) >> logs/pitch_zones.log 2>&1
```

## Troubleshooting

### `ContainerConfig` 에러

`docker-compose 1.29.2`와 최신 Docker 조합에서 자주 발생합니다.

```bash
docker rm -f kbo_web
docker run -d --name kbo_web --network kbo-dashboard_kbo_network -p 8000:80 kbo-dashboard-web:latest
```

### `container name "/kbo_web" is already in use`

이미 컨테이너가 존재한다는 뜻입니다.

```bash
docker start kbo_web
```

또는 새로 만들려면:

```bash
docker rm -f kbo_web
```

### `/web/distance` 404

nginx 설정을 reload하세요.

```bash
docker cp web/nginx.conf kbo_web:/etc/nginx/conf.d/default.conf
docker exec kbo_web nginx -t
docker exec kbo_web nginx -s reload
```

지원 경로:

```text
/distance
/web/distance
/web/distance.html
```

## 다음 개발 TODO

- 순위표 컬럼 정렬
- 타자/투수 검색 및 팀 필터
- CSV 다운로드
- 홈 미니 캘린더
- 다크모드
- Beeswarm 차트
- HOT/COLD ZONE
- 구종 분석 데이터 수집
