# 재발 방지 A·B·C — 엔진 확인 · 기동 전 데이터 확인 · 헬스체크

작성: 2026-10-24 · 운영 컨테이너 교체·재시작·cron 재활성화·커밋/푸시 하지 않음. 배경은 `P2C_stabilization.md` 7·8장(빈 data 마운트 장애).

## 1. 구현

| 항목 | 파일 | 동작 |
| --- | --- | --- |
| A 엔진 확인 | `scripts/docker_engine.sh`(신규, source 용) → `start_kbo.sh`·`update_kbo_daily.sh`·`backup_db.sh` | `docker info` 의 OperatingSystem 이 `Docker Desktop` 이 아니면 `[error] engine:` 후 exit 5(아무 조작 전). 맞으면 `[engine] Docker Desktop|docker-desktop|<엔진 ID> · kbo_backend: <ID> <이미지> <상태>` 로 실제 daemon·운영 컨테이너를 로그에 남긴다. WSL 기본 엔진은 OperatingSystem 이 `Ubuntu 24.04.3 LTS` |
| B 기동 전 데이터 | `backend/data_check.py`(신규), `backend/entrypoint.sh` | 마운트(tmpfs 자리표시 / mounted / image) · 필수 4개(활성 시즌의 순위·일정·팀경기·타자지표: missing / empty(0바이트·헤더만) / unreadable / ok) · 선택 6개(네이버 타자·투수, 존 2, 구종, 볼카운트 — 없으면 경고만)를 구분. 준비 안 되면 API 를 띄우지 않고 5초 뒤 exit 1 → 재시작 정책이 다시 띄움. 연속 실패 5회(`KBO_DATA_MAX_ATTEMPTS`)면 재시작 고리를 끊고 대기(`sleep infinity`, 포트 안 엶 → unhealthy). 카운터는 컨테이너 쓰기 계층 `/tmp` — restart 에 남고 재생성 때 지워짐, 성공하면 지움. 데이터 확인이 시드보다 먼저라 빈 마운트로 시드하지 않는다. DB 삭제·재적재 없음 |
| C 헬스체크 | `backend/main.py`, `docker-compose.yml` | `/health` 그대로(프로세스 생존). `/ready` = DB + `data_check` — 둘 중 하나라도 아니면 503, 본문에 `database`, `data.{ready, mount, season, problems, optional_missing}`. compose 헬스체크 `/health` → `/ready`, `KBO_DATA_MOUNT_REQUIRED: "1"`(마운트 없이 이미지 스냅샷으로 뜨면 준비 안 됨) |
| 테스트 편의 | `scripts/start_kbo.sh` | `LOG_DIR` 재지정 가능(일일 스크립트와 같은 방식) — 테스트가 실제 `logs/` 마커를 건드리거나 캐치업을 띄우지 않게 |

## 2. 테스트

| 종류 | 결과 |
| --- | --- |
| 단위 — `tests/test_data_check.py`(신규 7) | 마운트 4종(tmpfs·ext4·없음·겹침), 파일 5종, 필수 있음+선택 없음 = 준비, 필수 하나 없음 = 사유 1줄, tmpfs 면 파일 있어도 아님, 마운트 필요 여부, `/ready` DB 정상·데이터 아님 = 503 |
| 스크립트 — `src/test_update_daily.py`(+4) | 일일: 엉뚱한 엔진이면 exit 5·적재 안 함·성공 마커 없음. `start_kbo.sh`: Desktop+로컬 바인딩이면 `up`, 엉뚱한 엔진이면 아무것도 안 하고 exit 5, 빈·`0.0.0.0`·`::` 바인딩이면 `up` 전에 exit 4 |
| 전체 | src 110개 · 백엔드 111개(PG 전용 11 건너뜀) 통과 |
| 실제 엔진 | Desktop 엔진에서 `require_kbo_engine` 통과(엔진 ID 5340d6af…, kbo_backend 18842f04). 기대 OS 를 바꾸면 rc=1 |

## 3. 격리 재현 (`kbo-backend:p2c-guard`, 운영과 같은 `--restart unless-stopped` + `/ready` 헬스체크, 복원 DB)

헬스체크 주기만 3초로 줄였다(운영 10초).

| # | 상황 | 결과 |
| --- | --- | --- |
| 1 | 정상 바인드 마운트 | healthy, `/health` 200 · `/ready` 200, `mount=mounted season=2026 problems=[]` |
| 2 | **마운트 미준비**(`--tmpfs /app/data` = 이번 장애와 같은 자리표시) | 재시작 4회(시도 5회) 뒤 대기. 30초 더 지나도 재시작 수 4 → **무한 재시작 없음**. 상태 running·unhealthy, 포트 닫힘. 로그: `mount: … tmpfs 자리표시`, 필수 4개 `missing`, `5회 연속 준비 실패 — 재시작을 멈추고 대기` |
| 3 | **늦게 준비된 마운트**(빈 폴더로 시작 → 실패 중 파일 채움) | 재시작 2회 만에 스스로 healthy, `/ready` 200 — 재시작 정책과 결합한 자가 복구 |
| 4 | 필수만 있고 선택 자료 없음 | healthy, `/ready` 200. 선택 자료는 `[warn]` 만, 존 API 만 404, 순위 등 200 — 전체 장애로 번지지 않음 |
| 5 | 필수 파일이 헤더만(0행) | `required …: empty` ×4, 한도(2로 설정) 뒤 대기, unhealthy |
| 5b | 5 의 대기 중 파일을 고치고 `docker restart` | healthy, 카운터 초기화 |
| 5c | 2 의 대기 중 원인 그대로 `docker restart` | 곧바로 다시 대기(한도 유지) — 재시작 폭주 없음 |
| 6 | 데이터 정상 + DB 중단 | `/health` 200, `/ready` 503 `database: unavailable`(DB 호스트가 사라지면 응답에 3초 넘게 걸려 헬스체크 시간 초과로 실패 처리 — 결과는 같다) |
| 7 | 재기동(`docker restart`) | healthy 복귀, 시드 건너뜀 |
| 회귀 | `p2c-stab3` 대비 v1 31 · v2 19 경로 | `/ready` 1개만 다름(의도: 데이터 상태 추가). 나머지 49 동일 |

한계: Docker Desktop 자체의 '재시작 정책 vs WSL 바인드' 경합은 Desktop 을 재시작해야 재현되는데, 운영 컨테이너가 같은 엔진에 있어 하지 않았다. 대신 같은 결과(tmpfs 자리표시, 늦게 생기는 파일)를 격리 컨테이너로 만들어 확인했다. 운영 적용 뒤 첫 재부팅 때 `docker logs kbo_backend` 의 `[data]`/`[error] data:` 로 확인한다.

## 4. 운영 적용 (별도 승인 필요)

- B·C 는 새 백엔드 이미지 + compose 변경(헬스체크·환경변수)이라 **백엔드 컨테이너 재생성**이 필요하다. P2-C/P2-D 배포 때 함께 넣는다(재생성 1회).
- A 는 스크립트만 — 다음 실행부터 적용. 단 cron 은 멈춘 상태 그대로다.
- 이미지: `kbo-backend:p2c-guard`(검증용). 최종 후보 `kbo-backend:p2d-cand2`(7d11a1c0)에 포함 — 그 이미지로 마운트 미준비 재현을 다시 해 같은 결과(재시작 4회 후 대기)를 확인했다(`P2D_team_player.md`).
