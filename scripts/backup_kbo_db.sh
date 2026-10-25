#!/usr/bin/env bash
# 운영 DB(kbo_dashboard) 일일 백업 — pg_dump -Fc 를 저장소 밖(~/kbo-backups/daily)에 남기고 검증한다.
#
# 2026-10-26 05:04 KST compose down -v 로 운영 볼륨이 지워졌을 때 마지막 백업이 이틀 전 수동 덤프뿐이었다.
# 그 재발 방지 1단계. 원칙:
#   - 읽기만 한다: 컨테이너 안에서 pg_dump 만 부른다(운영 DB·컨테이너·볼륨을 바꾸지 않는다).
#   - 접속 정보를 다루지 않는다: 계정·DB 이름은 컨테이너 안의 POSTGRES_USER/POSTGRES_DB 로만 쓴다(.env 를 읽지 않음).
#   - 실패하면 기존 백업을 하나도 지우지 않는다. 보관 정리는 새 백업 검증 성공 뒤에만 한다.
#   - 덮어쓰지 않는다: 같은 이름이 있으면 실패로 끝낸다.
#
# 사용:  scripts/backup_kbo_db.sh
# 환경변수(선택):
#   KBO_BACKUP_ROOT          저장 위치                (기본 ~/kbo-backups/daily)
#   KBO_DB_CONTAINER         DB 컨테이너 이름          (기본 kbo_dashboard_db)
#   KBO_BACKUP_SCHEMAS       반드시 있어야 할 스키마    (기본 "public derived ingest official ref verify")
#   KBO_BACKUP_MIN_TABLES    최소 테이블 데이터 수      (기본 27)
#   KBO_BACKUP_MIN_RATIO     직전 백업 대비 최소 크기비  (기본 0.5 — 이보다 줄면 DB 가 비었을 수 있다)
#   KBO_BACKUP_MIN_FREE_MB   필요한 여유 공간(MB)      (기본: 직전 백업 크기의 3배, 최소 200)
#   KBO_BACKUP_KEEP_DAILY/WEEKLY/MONTHLY  보관 개수   (기본 14 / 8 / 6)
# 종료 코드: 0 성공 · 2 사전 점검 실패(엔진·컨테이너) · 3 덤프 실패 · 4 검증 실패 · 5 공간 부족 · 6 저장 실패
#           7 잠금 충돌(다른 백업이 실행 중 — 그쪽이 status.json 을 쓰므로 기록하지 않는다)
#           그 밖의 값 = 예상치 못한 종료(TERM 143 · INT 130 포함) — EXIT 트랩이 status.json 에 fail 로 남긴다
set -eEuo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${KBO_BACKUP_ROOT:-${HOME}/kbo-backups/daily}"
CONTAINER="${KBO_DB_CONTAINER:-kbo_dashboard_db}"
SCHEMAS="${KBO_BACKUP_SCHEMAS:-public derived ingest official ref verify}"
MIN_TABLES="${KBO_BACKUP_MIN_TABLES:-27}"
MIN_RATIO="${KBO_BACKUP_MIN_RATIO:-0.5}"
LOG="${BACKUP_ROOT}/backup.log"
STATUS="${BACKUP_ROOT}/status.json"
TMP_DIR="${BACKUP_ROOT}/.tmp"
STAMP="$(TZ=Asia/Seoul date +%Y%m%d-%H%M%S)"
NAME="kbo-${STAMP}.dump"
PART="${TMP_DIR}/${NAME}.part"

RECORDED=0   # 이번 실행의 결과(ok·fail)를 status.json 에 이미 썼는가 — 트랩이 두 번 쓰지 않게
LAST_CMD=""

mkdir -p "${BACKUP_ROOT}" "${TMP_DIR}"

log() { echo "[$(TZ=Asia/Seoul date '+%F %T %Z')] [backup] $*" | tee -a "${LOG}"; }

# status.json 은 마지막 시도 결과다. 마지막 성공(last_ok)은 실패해도 지우지 않는다.
write_status() {  # write_status ok|fail code reason [file size]
  python3 - "${STATUS}" "$@" <<'EOF'
import json, sys, os, datetime
path, result, code, reason = sys.argv[1:5]
extra = sys.argv[5:]
try:
    prev = json.load(open(path))
except Exception:
    prev = {}
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
out = {"last_attempt": now, "result": result, "exit_code": int(code), "reason": reason, "last_ok": prev.get("last_ok")}
if result == "ok":
    out["last_ok"] = {"at": now, "file": extra[0], "bytes": int(extra[1])}
tmp = path + ".tmp"
json.dump(out, open(tmp, "w"), ensure_ascii=False, indent=1)
os.replace(tmp, path)
EOF
}

fail() {  # fail code reason — 임시 파일만 지우고 기존 백업은 건드리지 않는다
  rm -f "${PART}"
  RECORDED=1
  log "FAIL($1): $2"
  write_status fail "$1" "$2"
  exit "$1"
}

# 예상치 못한 종료(set -e·신호)도 status.json 에 남긴다. 임시 .part 만 지우고, 저장된 백업은 지우지 않는다.
# LAST_CMD 는 확장 전 명령 원문이라 컨테이너 안 변수($POSTGRES_USER 등)의 값은 들어가지 않는다.
on_exit() {
  local rc=$?
  rm -f "${PART}"
  (( rc == 0 || RECORDED == 1 )) && return 0
  RECORDED=1
  local why="예상치 못한 종료(exit ${rc}${LAST_CMD:+ · line ${LAST_CMD}})"
  log "FAIL(${rc}): ${why}" || true
  write_status fail "${rc}" "${why}" || echo "[backup] status.json 기록 실패" >&2
}
trap 'LAST_CMD="${LINENO}: ${BASH_COMMAND:0:120}"' ERR
trap on_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# 동시에 두 번 돌지 않게(타이머 + 수동 실행 겹침). 상태는 실행 중인 쪽이 쓴다.
exec 9>"${BACKUP_ROOT}/.lock"
flock -n 9 || { RECORDED=1; log "다른 백업이 실행 중 — 건너뜀(exit 7)"; exit 7; }

log "start ${NAME} container=${CONTAINER} root=${BACKUP_ROOT}"

# 1) 사전 점검 — 엔진·컨테이너. 운영 쪽은 조회만 한다.
. "${ROOT_DIR}/scripts/docker_engine.sh"
require_kbo_engine >/dev/null 2>&1 || fail 2 "Docker Desktop(KBO 엔진)에 연결할 수 없다"
health="$(docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${CONTAINER}" 2>/dev/null || true)"
[[ "${health}" == "running/healthy" ]] || fail 2 "DB 컨테이너 상태가 running/healthy 가 아니다(${health:-없음})"

# 2) 공간 — 직전 백업의 3배(최소 200MB) 여유가 없으면 시작하지 않는다
prev="$(ls -1 "${BACKUP_ROOT}"/kbo-*.dump 2>/dev/null | sort | tail -1 || true)"
prev_bytes=$([[ -n "${prev}" ]] && stat -c %s "${prev}" || echo 0)
need_mb="${KBO_BACKUP_MIN_FREE_MB:-$(( (prev_bytes * 3 / 1048576) > 200 ? (prev_bytes * 3 / 1048576) : 200 ))}"
free_mb="$(df -Pm "${BACKUP_ROOT}" | awk 'NR==2{print $4}')"
(( free_mb >= need_mb )) || fail 5 "여유 공간 ${free_mb}MB < 필요 ${need_mb}MB"

# 3) 덤프 — 컨테이너 안의 계정·DB 이름을 쓴다(호스트로 접속 정보가 나오지 않는다)
if ! docker exec "${CONTAINER}" sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "${PART}" 2>>"${LOG}"; then
  fail 3 "pg_dump 실패(자세한 오류는 backup.log)"
fi
bytes="$(stat -c %s "${PART}")"
(( bytes > 0 )) || fail 3 "덤프가 0 바이트"

# 4) 검증 — 목록 읽기·필수 스키마·테이블 수·크기 급감
toc="$(docker exec -i "${CONTAINER}" pg_restore --list < "${PART}" 2>>"${LOG}")" || fail 4 "pg_restore --list 실패(손상된 덤프)"
for s in ${SCHEMAS}; do
  if [[ "${s}" == public ]]; then
    grep -qE " TABLE DATA public " <<<"${toc}" || fail 4 "필수 스키마 누락: public"
  else
    grep -qE " SCHEMA - ${s} " <<<"${toc}" || fail 4 "필수 스키마 누락: ${s}"
  fi
done
tables="$(grep -cE " TABLE DATA " <<<"${toc}" || true)"
(( tables >= MIN_TABLES )) || fail 4 "테이블 데이터 ${tables}개 < 최소 ${MIN_TABLES}개"
if [[ -n "${prev}" ]]; then
  python3 -c "import sys; sys.exit(0 if ${bytes} >= ${prev_bytes} * ${MIN_RATIO} else 1)" \
    || fail 4 "크기 급감: ${bytes}B < 직전($(basename "${prev}")) ${prev_bytes}B × ${MIN_RATIO}"
fi

# 5) 저장 — 덮어쓰지 않는다(같은 이름이 있으면 실패)
final="${BACKUP_ROOT}/${NAME}"
[[ ! -e "${final}" ]] || fail 6 "같은 이름의 백업이 이미 있다: ${NAME}"
mv -n "${PART}" "${final}" && [[ -f "${final}" && ! -e "${PART}" ]] || fail 6 "저장(mv) 실패"
( cd "${BACKUP_ROOT}" && sha256sum "${NAME}" > "${NAME}.sha256" ) || fail 6 "SHA-256 기록 실패"
ln -sfn "${NAME}" "${BACKUP_ROOT}/latest.dump"
log "ok ${NAME} bytes=${bytes} tables=${tables} sha256=$(cut -c1-16 "${final}.sha256")…"
write_status ok 0 "" "${NAME}" "${bytes}"
RECORDED=1

# 6) 보관 정리 — 검증 성공 뒤에만. 정리 실패는 백업 실패가 아니다(경고만)
python3 "${ROOT_DIR}/scripts/kbo_backup_retention.py" "${BACKUP_ROOT}" --protect "${final}" \
  --keep-daily "${KBO_BACKUP_KEEP_DAILY:-14}" --keep-weekly "${KBO_BACKUP_KEEP_WEEKLY:-8}" \
  --keep-monthly "${KBO_BACKUP_KEEP_MONTHLY:-6}" 2>&1 | tee -a "${LOG}" || log "경고: 보관 정리 실패(백업은 정상)"
log "done"
