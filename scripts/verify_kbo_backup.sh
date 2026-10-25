#!/usr/bin/env bash
# 백업 복원 테스트 — 최신(또는 지정한) 덤프를 **운영과 완전히 분리된 임시 PostgreSQL** 에 복원해 검증한다.
#
# 임시 컨테이너: 운영과 같은 이미지 · 네트워크 없음(--network none) · 포트 없음 · 볼륨 없음(tmpfs 데이터) · 종료 시 삭제.
# 운영 DB 는 선택적으로 **읽기 전용 조회**(행 수 비교)만 한다 — KBO_VERIFY_COMPARE_LIVE=0 이면 그것도 하지 않는다.
# 소유자·권한은 복원하지 않는다(--no-owner --no-privileges) — 운영 계정 이름에 기대지 않는다.
#
# 사용:  scripts/verify_kbo_backup.sh [덤프 경로]      (기본: ~/kbo-backups/daily/latest.dump)
# 종료 코드: 0 성공 · 2 사전 점검 실패 · 3 해시 불일치 · 4 복원 실패 · 5 내용 검증 실패
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${KBO_BACKUP_ROOT:-${HOME}/kbo-backups/daily}"
DUMP="${1:-${BACKUP_ROOT}/latest.dump}"
LIVE="${KBO_DB_CONTAINER:-kbo_dashboard_db}"
SCHEMAS="${KBO_BACKUP_SCHEMAS:-public derived ingest official ref verify}"
MIN_TABLES="${KBO_BACKUP_MIN_TABLES:-27}"
LOG="${BACKUP_ROOT}/verify.log"
NAME_TMP="kbo_backup_verify_$(date +%s)_$$"

mkdir -p "${BACKUP_ROOT}"
log() { echo "[$(TZ=Asia/Seoul date '+%F %T %Z')] [verify] $*" | tee -a "${LOG}"; }
cleanup() { docker rm -f "${NAME_TMP}" >/dev/null 2>&1 || true; }
trap cleanup EXIT
die() { log "FAIL($1): $2"; exit "$1"; }

[[ -e "${DUMP}" ]] || die 2 "덤프가 없다: ${DUMP}"
real="$(readlink -f "${DUMP}")"
log "start $(basename "${real}")"

# 1) 무결성 — 기록해 둔 SHA-256 과 비교
( cd "$(dirname "${real}")" && sha256sum -c --status "$(basename "${real}").sha256" ) || die 3 "SHA-256 불일치 또는 .sha256 없음"

# 2) 격리 임시 DB — 이미지는 운영과 같게, 비밀번호는 매번 무작위(어디에도 남기지 않음)
. "${ROOT_DIR}/scripts/docker_engine.sh"
require_kbo_engine >/dev/null 2>&1 || die 2 "Docker Desktop(KBO 엔진)에 연결할 수 없다"
image="$(docker inspect -f '{{.Config.Image}}' "${LIVE}" 2>/dev/null || echo postgres:15-alpine)"
docker run -d --rm --name "${NAME_TMP}" --network none --tmpfs /var/lib/postgresql/data:rw,size=3g \
  -e POSTGRES_USER=verify -e POSTGRES_DB=verify -e POSTGRES_PASSWORD="$(head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9)" \
  "${image}" >/dev/null || die 2 "임시 컨테이너 기동 실패"
iso="$(docker inspect -f '{{len .Mounts}}|{{.HostConfig.NetworkMode}}|{{len .HostConfig.PortBindings}}' "${NAME_TMP}")"
[[ "${iso}" == "0|none|0" ]] || die 2 "임시 컨테이너가 격리되지 않았다(${iso}) — 중단"
for _ in $(seq 60); do docker exec "${NAME_TMP}" pg_isready -U verify -q 2>/dev/null && break; sleep 1; done
docker exec "${NAME_TMP}" pg_isready -U verify -q || die 2 "임시 DB 가 준비되지 않았다"

# 3) 복원 — 오류가 나면 즉시 중단
start=$(date +%s)
docker exec -i "${NAME_TMP}" pg_restore -U verify -d verify --exit-on-error --no-owner --no-privileges < "${real}" 2>>"${LOG}" \
  || die 4 "pg_restore 실패(자세한 오류는 verify.log)"
secs=$(( $(date +%s) - start ))

# 4) 내용 — 스키마·테이블·뷰 수, 테이블별 행 수(운영과 비교는 선택)
q() { docker exec "$1" sh -c "psql -U \"\${POSTGRES_USER}\" -d \"\${POSTGRES_DB}\" -At -c \"$2\""; }
COUNTS="SELECT n.nspname||'.'||c.relname||'|'||(xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname), false, true, '')))[1]::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1"
restored="$(q "${NAME_TMP}" "${COUNTS}")"
for s in ${SCHEMAS}; do grep -q "^${s}\." <<<"${restored}" || die 5 "복원 결과에 스키마 ${s} 의 테이블이 없다"; done
ntables="$(grep -c . <<<"${restored}")"
(( ntables >= MIN_TABLES )) || die 5 "복원된 테이블 ${ntables}개 < ${MIN_TABLES}"
nviews="$(q "${NAME_TMP}" "SELECT count(*) FROM pg_views WHERE schemaname NOT IN ('pg_catalog','information_schema')")"
rows="$(awk -F'|' '{s+=$2} END{print s}' <<<"${restored}")"

diff_note="운영 비교 안 함"
if [[ "${KBO_VERIFY_COMPARE_LIVE:-1}" == "1" ]]; then
  # 운영은 읽기 전용 트랜잭션으로 행 수만 센다. 백업 이후 운영이 바뀌었으면 차이가 날 수 있다(경고만).
  live="$(docker exec "${LIVE}" sh -c "PGOPTIONS='-c default_transaction_read_only=on' psql -U \"\${POSTGRES_USER}\" -d \"\${POSTGRES_DB}\" -At -c \"${COUNTS}\"" 2>/dev/null || true)"
  if [[ -z "${live}" ]]; then
    diff_note="운영 조회 실패(비교 생략)"
  elif [[ "${live}" == "${restored}" ]]; then
    diff_note="운영과 테이블별 행 수 일치"
  else
    diff_note="운영과 다른 테이블 $(diff <(echo "${live}") <(echo "${restored}") | grep -c '^>' || true)개(백업 이후 변경 가능 — 확인 필요)"
  fi
fi
log "ok $(basename "${real}") restore=${secs}s tables=${ntables} views=${nviews} rows=${rows} · ${diff_note}"
