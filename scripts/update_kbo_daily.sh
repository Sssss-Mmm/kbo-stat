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
  echo "DRY_RUN: docker compose -f ${COMPOSE_FILE} exec -T backend python migrate.py"
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

# 갱신된 CSV를 DB로 재적재(컨테이너는 data 를 bind mount 하므로 새 CSV 가 보인다).
# 백엔드 컨테이너가 떠 있을 때만 수행. zone 데이터는 CSV 직접 서빙이라 재적재 불필요.
echo "[db] reload database from refreshed CSVs"
if command -v docker >/dev/null 2>&1 && \
   docker compose -f "${COMPOSE_FILE}" ps -q backend 2>/dev/null | grep -q .; then
  docker compose -f "${COMPOSE_FILE}" exec -T backend python migrate.py \
    || echo "[db] migrate.py returned non-zero (continuing)"
else
  echo "[db] backend container not running — skipping DB reload"
fi

# 성공 마커: 기동 캐치업(start_kbo.sh)이 "오늘 이미 갱신됨"을 판정하는 데 사용.
# set -e 라 위 단계가 실패하면 여기까지 못 오므로, 마커는 전체 성공 시에만 갱신된다.
echo "${TODAY}" > "${LOG_DIR}/.last_update_date"

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] finished daily KBO update date=${TODAY}"
