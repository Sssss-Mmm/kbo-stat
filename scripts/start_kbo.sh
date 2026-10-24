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
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/logs}"  # 테스트는 임시 폴더로 바꾼다(실제 마커를 건드리지 않게)
MARKER="${LOG_DIR}/.last_update_date"
LOG_FILE="${LOG_DIR}/update_kbo_daily.log"

mkdir -p "${LOG_DIR}"

. "${ROOT_DIR}/scripts/docker_engine.sh"
require_kbo_engine || exit 5

# --no-recreate 는 예전 설정으로 만든 컨테이너의 포트 바인딩을 그대로 둔다. 켜기 전에, 이미 있는 컨테이너
# (정지 포함)가 외부 공개 금지(127.0.0.1 전용)를 지키는지 본다. 아니면 아무것도 켜지 않고 멈춘다.
# 새로 만들어지는 컨테이너는 compose 설정(127.0.0.1)을 그대로 따른다.
EXISTING="$(docker compose -f "${COMPOSE_FILE}" ps -aq)"
EXPOSED=""
if [[ -n "${EXISTING}" ]]; then
  EXPOSED="$(docker inspect --format '{{.Name}} {{range $p, $b := .HostConfig.PortBindings}}{{range $b}}{{.HostIp}}:{{.HostPort}} {{end}}{{end}}' \
    ${EXISTING} | grep -E ' (:|0\.0\.0\.0:|\[?::\]?:)[0-9]' || true)"
fi
if [[ -n "${EXPOSED}" ]]; then
  echo "[error] start: 모든 인터페이스에 열리도록 만들어진 컨테이너 — ${EXPOSED}"
  echo "[error] start: 승인 후 재생성으로 127.0.0.1 바인딩을 적용: docker compose -f ${COMPOSE_FILE} up -d --no-deps --force-recreate <서비스>"
  exit 4
fi

echo "[start] bringing up KBO dashboard stack"
# --no-recreate: 이미 있는 컨테이너는 켜기만 한다. 새 이미지·설정으로 교체하려면(승인 후)
#   docker compose -f kbo-dashboard/docker-compose.yml up -d --force-recreate <서비스>
docker compose -f "${COMPOSE_FILE}" up -d --no-recreate

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
