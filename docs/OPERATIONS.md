# 운영 가이드

설치, 실행, 데이터 갱신, 백업과 복구 방법을 정리한 문서입니다. 프로젝트 소개는 [README](../README.md)에 있습니다.

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

외부 호출은 아래 스위치를 켜야만 나갑니다. 셋 다 기본값은 꺼짐이고, 운영 compose도 넘기지 않습니다.

| 변수 | 켜면 |
| --- | --- |
| `LLM_EXTERNAL_CALLS_APPROVED=1` | `OPENAI_API_KEY`와 함께 있을 때 OpenAI를 호출합니다. 꺼져 있으면 질의응답은 기록 계산만으로 답합니다. |
| `KBO_AUTOMATED_FETCH_APPROVED=1` | KBO 공식 사이트 자동 수집을 허용합니다. |
| `NAVER_AUTOMATED_FETCH_APPROVED=1` | 네이버 스포츠 자동 수집을 허용합니다. |

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
> 과거 날짜 대량 수집은 [docs/BACKFILL_PITCH_DATA.md](BACKFILL_PITCH_DATA.md)를 따르세요.

모든 CSV 저장은 `src/csv_guard.py`를 경유합니다. 출처 구조가 바뀌어 파서가 빈 결과를 뱉으면
0행 저장을 거부해 기존 CSV를 지키고, 행 수가 맞아도 값이 깨진 경우는 정합성 규칙 V-01~08로 거부합니다.

```bash
python3 src/csv_guard.py        # 자체 점검 (0행 거부 · V-01~08 위반 샘플 거부 · 운영 CSV 통과)
```

## 자동 업데이트

`scripts/update_kbo_daily.sh`를 cron에 등록해 매일 **02:00 KST**에 자동 갱신합니다.

```cron
0 2 * * * cd $HOME/kbo-stat && PYTHON_BIN=/usr/bin/python3 scripts/update_kbo_daily.sh >> logs/update_kbo_daily.log 2>&1
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

## 주의할 점

- **백엔드 코드는 이미지에 COPY됩니다.** 소스 볼륨 마운트가 아니라서 `docker compose restart backend`로는
  코드 변경이 반영되지 않습니다. `docker compose up -d --build backend`를 쓰세요.
- CSV를 갱신해도 DB 기반 API에는 바로 반영되지 않습니다. 필요하면 `--db` 또는 `migrate.py`를 함께 실행하세요.
- **시즌 셀렉터는 실제로 데이터가 있는 시즌만 보여줍니다.** 고를 게 하나뿐인 화면
  (순위·일정·관중·선수 기록 = 2026)은 셀렉터를 아예 그리지 않고 활성 시즌을 텍스트로 표기합니다.
  셀렉터가 남아 있는 곳은 투구 존·구종·볼카운트(2025~2026) 뿐입니다.
  단일 시즌 화면이 쓰는 값은 상수가 아니라 백엔드가 파일을 보고 판정한 활성 시즌입니다(`utils.current_season()`).
- 과거 45시즌(1982~2026)에 있는 것은 팀 순위가 아니라 **선수 리더보드**(`data/raw/kbo_official/kbo_{연도}.csv`)입니다.
  다만 이 파일은 규정 충족자만(시즌당 50명 안팎) 담겨 있고 OBP·SLG·OPS·wRC+·WAR이 없어,
  선수 기록 화면(네이버 기준 342명 + WAR)을 그대로 채우지 못합니다. `migrate.py`도 2020~2026 7시즌만 적재합니다.
- 선수 기록 API는 데이터 파일 종류에 따라 리더보드 선수만 보일 수 있습니다.
  전체 등록 선수 명단은 `python3 src/update_daily.py --registered-players`(또는 `--players`)로 갱신합니다.
- 백엔드 엔드포인트 25개 중 12개는 아직 React 화면에서 쓰이지 않습니다(대부분 클라이언트 필터 방식을 택해 중복이 된 서버측 검색·필터입니다. 사유는 `docs/REQUIREMENTS.md` 5절).
