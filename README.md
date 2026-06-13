# KBO Dashboard ⚾

> KBO(한국 프로야구) 데이터를 직접 수집·정제·시각화하는 풀스택 데이터 대시보드.
> 매일 자동으로 갱신되는 데이터 파이프라인 위에 React 대시보드와 FastAPI 백엔드를 올린 개인 프로젝트입니다.

**Stack** · Python (크롤러 / ETL) · FastAPI · PostgreSQL · React + Vite · Docker · cron

---

## 한눈에 보기

여러 공개 소스(KBO 공식, 네이버 스포츠, Statiz)에서 데이터를 수집해 하나의 DB로 정규화하고,
매일 새벽 자동 갱신되는 파이프라인을 거쳐 대시보드로 보여줍니다.

```
 데이터 소스                  수집/정제(Python)            저장          서비스
┌──────────────┐         ┌─────────────────────┐    ┌──────────┐   ┌──────────────┐
│ KBO 공식 사이트 │         │  crawl_*.py (크롤러)   │    │          │   │ FastAPI       │
│ 네이버 스포츠   │  ──►    │  build_*.py (ETL)     │──► │ Postgres │──►│ REST API      │──► React Dashboard
│ Statiz        │         │  update_daily.py      │    │  / CSV   │   │ (8001)        │     (Vite)
└──────────────┘         └─────────────────────┘    └──────────┘   └──────────────┘
                                  ▲
                          매일 02:00 KST cron 자동 실행
```

## 주요 기능

| 기능 | 설명 |
| --- | --- |
| 🏠 **오늘의 경기** | 네이버 일정 API를 온디맨드로 프록시해 예고 선발·스코어·경기 상태를 실시간 표시. **log5 + 홈 어드밴티지**로 홈팀 승리 확률 추정 |
| 📊 **팀 순위** | 승·패·승률·게임차·최근 10경기, 시즌 순위 변동을 보여주는 **순위 레이스 차트** |
| 📅 **경기 일정** | 시즌 전체 일정/결과 |
| 🧑 **선수 기록** | 타자·투수 리더보드를 **산점도(Scatter) / 비스웜(Beeswarm)** 차트로 탐색 |
| 🔥 **핫/콜드존** | 네이버 경기센터의 투구 추적 데이터를 모아 만든 타자·투수별 **3×3 스트라이크존 히트맵** |
| 🤖 **AI 분석 데모** | CSV 기반 경량 RAG — 질문에 대해 관련 통계 근거(evidence)를 검색·합성해 답변 |

> 다크/라이트 테마 토글, 팀별 컬러·엠블럼 등 디테일도 직접 구현했습니다.

## 기술적으로 신경 쓴 점

- **다중 소스 크롤링 정규화** — KBO 공식, 네이버, Statiz의 서로 다른 응답 구조와 팀 코드(예: 잠실 = LG/두산 공용)를 하나의 스키마로 통합.
- **라이브 vs 배치 데이터 분리** — 하루에도 바뀌는 예고 선발·스코어는 요청 시점에 직접 호출(60초 캐시)하고, 안정적인 통계는 일일 CSV 배치로 처리.
- **자동화된 일일 파이프라인** — `flock` 락으로 중복 실행을 막는 cron 스크립트가 매일 데이터를 갱신하고, 경기 지연/연장을 고려해 투구 데이터는 직전 2일치를 다시 수집.
- **DB 단일화 리팩터링** — 초기 정적 CSV 직접 읽기 방식에서 PostgreSQL + FastAPI 백엔드 API 호출로 전환해 데이터 소스를 일원화.
- **경량 RAG** — 외부 LLM 의존 없이 키워드 오버랩 기반 검색 + 템플릿 합성으로 근거 기반 답변을 생성하는 데모.

## 기술 스택

| 영역 | 사용 기술 |
| --- | --- |
| 데이터 수집/정제 | Python, pandas, requests, BeautifulSoup |
| 백엔드 | FastAPI, SQLAlchemy, PostgreSQL |
| 프런트엔드 | React 18, Vite, axios, 직접 구현한 SVG 차트 |
| 인프라 | Docker, docker-compose, nginx, cron |

## 프로젝트 구조

```
kbo-stat/
├── src/                     # 데이터 수집·정제 파이프라인 (Python)
│   ├── crawl_*.py           #   소스별 크롤러 (KBO/네이버/Statiz)
│   ├── build_*.py           #   ETL — 지표·존·경기결과 데이터셋 생성
│   └── update_daily.py      #   일일 업데이트 엔트리포인트
├── kbo-dashboard/           # 메인 풀스택 앱
│   ├── backend/             #   FastAPI (routers / services / models / migrations)
│   └── frontend/            #   React + Vite 대시보드
├── scripts/                 # 배포·일일 cron 스크립트
├── web/                     # 초기 vanilla JS 프로토타입 (레거시, nginx 클린 URL)
└── data/                    # raw / processed CSV
```

## 빠른 실행

### 1) 데이터 갱신

```bash
python3 src/update_daily.py --year 2026                 # 순위·일정 (빠른 갱신)
python3 src/update_daily.py --year 2026 --players        # 타자·투수 리더보드 포함
python3 src/update_daily.py --year 2026 --pitch-zones    # 핫/콜드존 투구 데이터 포함
```

### 2) 백엔드

```bash
cd kbo-dashboard/backend
venv/bin/python main.py          # http://127.0.0.1:8001
```

```bash
# 예시: RAG 질의
curl -X POST http://127.0.0.1:8001/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"왜 한화가 강하지?","season":2026}'
```

### 3) 프런트엔드

```bash
cd kbo-dashboard/frontend
npm install
npm run dev                       # Vite 개발 서버 (백엔드 8001로 프록시)
```

### Docker

```bash
cd kbo-dashboard
docker-compose up -d              # postgres + backend + frontend
```

## 자동 업데이트 (cron)

매일 새벽 2시(KST) KBO 공식 데이터와 네이버 투구 데이터를 함께 갱신합니다.

```cron
0 2 * * * cd /home/sssssmmm/kbo-stat && scripts/update_kbo_daily.sh >> logs/update_kbo_daily.log 2>&1
```

`logs/update_kbo_daily.lock` 기반 `flock`으로 중복 실행을 방지합니다.

## 데이터 출처 안내

네이버 경기센터의 투구 위치·일정 데이터는 공식 문서화된 API가 아니라 네이버 스포츠가 사용하는
공개 응답을 기반으로 합니다. 응답 구조가 바뀔 수 있으며, 모든 데이터의 저작권은 각 출처에 있습니다.
본 프로젝트는 학습·포트폴리오 목적의 비상업적 프로젝트입니다.

## 향후 개선 아이디어

- 순위표 컬럼 정렬 / 선수 검색·팀 필터 / CSV 다운로드
- 홈 미니 캘린더
- 구종(pitch type) 분석 데이터 수집 및 시각화
