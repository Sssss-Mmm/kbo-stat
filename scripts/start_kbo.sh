#!/usr/bin/env bash
# KBO 대시보드 스택을 띄우고, 오늘 아직 갱신 전이면 전체 데이터 파이프라인을
# 백그라운드로 1회 실행(캐치업)한다. WSL 처럼 PC 가 02:00 cron 시점에 꺼져 있어
# 일일 갱신을 놓친 경우를 따라잡기 위한 용도.
#
# 사용: docker compose up 대신 이 스크립트를 실행.
#   scripts/start_kbo.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/kbo-dashboard/docker-compose.yml"
LOG_DIR="${ROOT_DIR}/logs"
MARKER="${LOG_DIR}/.last_update_date"
LOG_FILE="${LOG_DIR}/update_kbo_daily.log"

mkdir -p "${LOG_DIR}"

echo "[start] bringing up KBO dashboard stack"
docker compose -f "${COMPOSE_FILE}" up -d

TODAY="$(TZ=Asia/Seoul date +%F)"
LAST="$(cat "${MARKER}" 2>/dev/null || true)"

if [[ "${LAST}" == "${TODAY}" ]]; then
  echo "[start] data already updated today (${TODAY}) — skipping catch-up"
  exit 0
fi

echo "[start] last update '${LAST:-none}' != today ${TODAY} — launching catch-up in background"
echo "[start] follow progress with: tail -f ${LOG_FILE}"
# update_kbo_daily.sh 내부 flock 이 02:00 cron 과의 동시 실행을 막는다.
nohup bash "${ROOT_DIR}/scripts/update_kbo_daily.sh" >> "${LOG_FILE}" 2>&1 &

echo "[start] done. stack is up; catch-up update running in background."
