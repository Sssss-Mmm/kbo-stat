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

echo "[official] standings/schedule/attendance/game-time"
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY_RUN: ${PYTHON_BIN} src/update_daily.py --year ${YEAR}"
  echo "DRY_RUN: ${PYTHON_BIN} src/crawl_naver_pitch_zones.py --from-date ${TWO_DAYS_AGO} --to-date ${YESTERDAY}"
  exit 0
fi

"${PYTHON_BIN}" src/update_daily.py --year "${YEAR}"

echo "[naver-pitch] refresh ${TWO_DAYS_AGO}..${YESTERDAY}"
"${PYTHON_BIN}" src/crawl_naver_pitch_zones.py \
  --from-date "${TWO_DAYS_AGO}" \
  --to-date "${YESTERDAY}"

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] finished daily KBO update date=${TODAY}"
