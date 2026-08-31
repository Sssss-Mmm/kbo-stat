#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
LOG_DIR="${ROOT_DIR}/logs"
LOCK_FILE="${LOG_DIR}/update_kbo_daily.lock"

mkdir -p "${LOG_DIR}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] another update is already running"
  exit 0
fi

cd "${ROOT_DIR}"

TODAY="$(TZ=Asia/Seoul date +%F)"
YEAR="$(TZ=Asia/Seoul date +%Y)"
YESTERDAY="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
TWO_DAYS_AGO="$(TZ=Asia/Seoul date -d '2 days ago' +%F)"

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] start daily KBO update season=${YEAR}"

COMPOSE_FILE="${ROOT_DIR}/kbo-dashboard/docker-compose.yml"

echo "[official] standings/schedule/attendance/game-time/players"
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY_RUN: ${PYTHON_BIN} src/update_daily.py --year ${YEAR} --players"
  echo "DRY_RUN: ${PYTHON_BIN} src/crawl_naver_player_stats.py --year ${YEAR}"
  echo "DRY_RUN: ${PYTHON_BIN} src/crawl_naver_pitch_zones.py --from-date ${TWO_DAYS_AGO} --to-date ${YESTERDAY}"
  echo "DRY_RUN: ${PYTHON_BIN} src/build_zone_metrics.py --year ${YEAR}"
  echo "DRY_RUN: ${PYTHON_BIN} src/build_pitch_arsenal.py --year ${YEAR}"
  echo "DRY_RUN: ${PYTHON_BIN} src/build_count_metrics.py --year ${YEAR}"
  echo "DRY_RUN: docker compose -f ${COMPOSE_FILE} up -d backend   # only if container is down"
  echo "DRY_RUN: docker compose -f ${COMPOSE_FILE} exec -T backend python migrate.py   # exit 3/4 on failure"
  exit 0
fi

"${PYTHON_BIN}" src/update_daily.py --year "${YEAR}" --players

echo "[naver-players] full-roster season stats (hitters/pitchers)"
"${PYTHON_BIN}" src/crawl_naver_player_stats.py --year "${YEAR}"

echo "[naver-pitch] refresh ${TWO_DAYS_AGO}..${YESTERDAY}"
"${PYTHON_BIN}" src/crawl_naver_pitch_zones.py \
  --from-date "${TWO_DAYS_AGO}" \
  --to-date "${YESTERDAY}"

echo "[zones] rebuild hot/cold zone datasets season=${YEAR}"
"${PYTHON_BIN}" src/build_zone_metrics.py --year "${YEAR}"

echo "[arsenal] rebuild pitch-type arsenal datasets season=${YEAR}"
"${PYTHON_BIN}" src/build_pitch_arsenal.py --year "${YEAR}"

echo "[count] rebuild ball/strike count dataset season=${YEAR}"
"${PYTHON_BIN}" src/build_count_metrics.py --year "${YEAR}"

# 갱신된 CSV를 DB로 재적재(컨테이너는 data 를 bind mount 하므로 새 CSV 가 보인다).
# zone 데이터는 CSV 직접 서빙이라 재적재 불필요.
# DB 적재 실패/스킵은 성공이 아니다: CSV 만 최신이고 DB 가 낡은 상태로 조용히
# exit 0 하면 아무도 모른 채 몇 달이 지난다(실제로 2026-06-13 ~ 08-30 발생).
echo "[db] reload database from refreshed CSVs"

backend_running() {
  docker compose -f "${COMPOSE_FILE}" ps -q backend 2>/dev/null | grep -q .
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[db] FAIL: docker not found — CSVs are updated but the DB was NOT reloaded" >&2
  exit 3
fi

if ! backend_running; then
  echo "[db] backend container not running — trying to start it once"
  docker compose -f "${COMPOSE_FILE}" up -d backend || true
  # ponytail: 고정 대기. backend 는 postgres service_healthy 를 기다린 뒤 뜨므로
  # 보통 충분하다. 부족하면 healthcheck 폴링 루프로 올릴 것.
  sleep 5
fi

if ! backend_running; then
  echo "[db] FAIL: backend container is down and could not be started —" >&2
  echo "[db]       CSVs are updated but the DB was NOT reloaded (stale API data)." >&2
  echo "[db]       fix: bash scripts/start_kbo.sh" >&2
  exit 3
fi

if ! docker compose -f "${COMPOSE_FILE}" exec -T backend python migrate.py; then
  echo "[db] FAIL: migrate.py exited non-zero — CSVs are updated but the DB reload failed" >&2
  exit 4
fi

# 성공 마커: 기동 캐치업(start_kbo.sh)이 "오늘 이미 갱신됨"을 판정하는 데 사용.
# set -e + 위 exit 3/4 때문에 크롤 또는 DB 적재가 실패하면 여기까지 못 온다.
# 즉 DB 적재 실패 시 마커가 안 남고, 다음 start_kbo.sh(=컨테이너 기동 후)가
# 캐치업으로 다시 돌려 DB 까지 맞춘다.
echo "${TODAY}" > "${LOG_DIR}/.last_update_date"

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] finished daily KBO update date=${TODAY}"
