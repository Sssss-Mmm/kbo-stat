# P1-D 보고서 — KBO 자동 수집 중단 · 수집 조건 · 운영 점검

작성: 2026-10-24

## 1. KBO 자동 요청 경로와 비활성화

| 경로 | KBO 요청 | 조치 |
| --- | --- | --- |
| cron 02:00 → `scripts/update_kbo_daily.sh` → `src/update_daily.py --players` | 순위·일정·관중·경기시간(`update_fast`), 타자·투수 기록·등록선수(`update_players`) | 승인 전 건너뜀, 가공 단계는 실행 |
| `scripts/start_kbo.sh` 캐치업 | 위와 같은 스크립트 | 같은 경로라 함께 막힘 |
| `.github/workflows/kbo-probe.yml` → `scripts/probe_kbo_reachable.py` | push 시 자동 실행, 프로브가 일반 `requests` 로 순위 페이지를 직접 요청(크롤러 우회) | push 자동 실행 제거(수동 실행만) + 프로브의 KBO 요청을 스위치 경유로 변경(Codex 지적) — 미승인 시 판정 '중단'(exit 2) |
| `src/crawl_kbo_*.py` 7개 직접 실행 | 각 모듈의 get/post/Session | 아래 스위치 |
| 백엔드·프론트엔드 | 없음 | — |

**스위치**: `src/kbo_access.py`. 7개 크롤러가 `requests` 대신 이 모듈의 `requests` 를 쓴다(import 한 줄씩).
요청은 `KBO_AUTOMATED_FETCH_APPROVED=1` 일 때만 나가고, 아니면 `KboFetchDisabled` 로 멈춘다 — 어느 경로로 불러도 같은 자리.
크롤러 코드·기존 CSV·원본은 그대로다. `update_daily.py` 는 스위치가 꺼져 있으면 KBO 단계를 로그 한 줄 남기고 건너뛴다.

**영향**: 순위·일정·관중·경기시간·선수 시즌 기록·등록선수 CSV 가 2026-10-22 기준에서 더 갱신되지 않는다(정규시즌 종료 이후).
네이버 투구 `--missing` 수집은 KBO 일정 CSV 의 종료 경기를 기준으로 하므로 새 경기를 찾지 못한다.
작업 중 검증 실행으로 `data/processed/kbo_hitter_metrics_2026.csv`(기존 CSV 로 다시 만드는 파생 파일, 49행)가 한 번 다시 저장됐다.

## 2. 네이버 수집 이용 조건·운영 위험

| 항목 | 확인 결과 |
| --- | --- |
| `api-gw.sports.naver.com/robots.txt` | 404(없음) — 허용 근거로 쓰지 않는다 |
| `m.sports.naver.com/robots.txt` | `User-agent: *` 루트 외 `Disallow: /` |
| 이용약관 | 검색으로 원문 조항 확인 못 함 — policy.naver.com 원문을 사람이 확인해야 함 |
| 공개 API 여부 | 크롤러가 쓰는 `api-gw` 는 문서화된 공개 API 가 아니다(내부 응답 구조) |
| 데이터 원천 | KBO 공식 기록 업체(스포츠투아이)의 고객사에 포털이 포함 — 네이버 야구 데이터의 권리 관계는 확인 못 함 |
| 법적 쟁점(일반) | 국내에서 크롤링 관련 손해배상 판결 사례가 있다는 보도. 데이터베이스 제작자 권리·부정경쟁 쟁점은 법률 검토 대상 |
| 운영 위험 | 응답 구조 변경·차단 시 무경고 실패(현재 csv_guard·빈 응답 거부로 방어), 요청량 증가 시 차단 가능 |

권장: 약관 검토 전까지 **새 백필·수집 범위 확대를 하지 않는다.** 일일 네이버 수집(선수 시즌 기록·투구)은 현재 그대로 돈다 — 계속할지 결정 필요.

## 3. Docker Compose WSL 경로 문제

원인: `docker compose` 플러그인이 `/usr/local/lib/docker/cli-plugins/docker-compose ->
/mnt/wsl/docker-desktop/cli-tools/...` 심볼릭 링크다. Docker Desktop 이 떠 있지 않으면 링크 대상이 없어
`docker compose` 가 `unknown shorthand flag: 'f' in -f` 로 실패하고, 스크립트는 이를 "백엔드가 내려감"으로 잘못 보고한다
(2026-09-10, 10-22 실패). 데몬 자체도 Docker Desktop 이 띄우므로 플러그인만 설치해서는 해결되지 않는다.

수정안(미적용, 승인 필요):

1. **Docker Desktop 자동 시작**: 설정 > General > "Start Docker Desktop when you sign in" 켜기(Windows 로그인 시 데몬·WSL 통합 준비).
2. **스크립트 사전 점검**: `update_kbo_daily.sh` 의 DB 단계 앞에

   ```bash
   if ! docker compose version >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
     echo "[db] FAIL: docker compose 플러그인 또는 Docker 데몬 없음(Docker Desktop 미실행?) — DB 재적재 안 함" >&2
     exit 5
   fi
   ```

   로 "백엔드 다운"과 "Docker 환경 없음"을 구분한다.
3. **재시작 정책**: `docker-compose.yml` 의 `postgres`·`backend`·`frontend` 에 `restart: unless-stopped` —
   Docker Desktop 재시작(2026-10-23 17:49 KST, 전 컨테이너 exit 255) 후 자동 복귀.
4. (선택) `version: '3.8'` 줄 삭제 — compose v2 경고 제거.

## 4. DB 연결 설정 불일치

- 비밀값을 출력하지 않고 항목별 일치만 비교했다: 호스트 `kbo-dashboard/backend/.env` 의 `DATABASE_URL` 은
  호스트·포트(localhost:5433)·사용자·DB 이름은 compose `.env` 와 같고 **비밀번호만 다르다.**
- 실제 DB 는 compose 쪽 비밀번호로 접속된다(일회성 컨테이너 적재 성공). 호스트에서 직접 `migrate.py`·`update_daily.py --db`
  를 돌릴 때만 실패하고, 일일 cron 은 컨테이너 안에서 적재하므로 영향이 없다.
- 수정안(미적용): 사용자가 `backend/.env` 의 비밀번호를 compose `.env` 의 `DB_PASSWORD` 와 맞추거나, 호스트 실행도
  `docker compose run` 경로만 쓰도록 문서화.

## 5. 백엔드 컨테이너 종료

- `kbo_backend` 는 2026-09-24 부터 정상 동작(헬스체크 200)하다 2026-10-23 08:49:40Z(17:49 KST)에 exit 255,
  OOM 아님. 같은 순간 다른 프로젝트 컨테이너까지 모두 종료 → Docker Desktop 재시작이 원인. 재시작 정책 `no` 라 복귀 안 함.
- 승인 없이 재시작하지 않았다. 수정안: 3절의 재시작 정책 + Docker Desktop 자동 시작.

## 6. 기존 데이터·API

`public` 13개 테이블·v1 API·원본 파일·기존 CSV 를 지우거나 바꾸지 않았다(위 1절의 파생 파일 1개 재저장 제외).

## 7. 검증

- 테스트: src 92개(KBO 스위치 6개 신규) · backend 53개 · 크롤러 자체 점검 통과.
- Codex 2라운드: 프로브가 크롤러를 거치지 않고 일반 `requests` 로 KBO 를 요청 → 스위치 경유로 수정, `src/`·`scripts/` 전체 정적 검사 테스트 추가.
- Codex 3라운드:
  - `official.*_current` 뷰가 새 원본에서 빠진 선수를 옛 원본에서 계속 보여 줌 → "경기별 최신 원본의 줄만" 으로 수정.
    PostgreSQL 에서 가짜 경기 2개 원본을 트랜잭션 안에 넣어 확인 후 롤백, 실제 뷰 교체(현재 행 수 7,026·18,506 그대로).
    **마지막 라운드 이후 수정이라 Codex 재검증은 받지 않았다.**
  - 승인 후에도 수동 프로브에 `KBO_AUTOMATED_FETCH_APPROVED` 가 전달되지 않음(낮음) → 의도대로 둠.
    승인을 받으면 워크플로 step 에 `env: KBO_AUTOMATED_FETCH_APPROVED: ${{ vars.KBO_AUTOMATED_FETCH_APPROVED }}` 한 줄을 추가한다.
