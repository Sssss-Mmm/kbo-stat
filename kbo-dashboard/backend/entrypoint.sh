#!/bin/sh
set -e

# 필수 데이터(data_check.py)가 준비 안 됐으면 API 를 띄우지 않는다 — 빈 데이터로 서비스하지 않는다.
# 실패하면 잠시 쉬고 exit 1 → 재시작 정책이 다시 띄우면 Docker Desktop 이 그 사이 붙인 바인드 마운트를 받는다
# (2026-10-24 장애: 마운트가 컨테이너보다 늦게 준비됨. 수동 docker restart 로 복구 확인).
# 연속 실패 횟수는 컨테이너 쓰기 계층(/tmp — restart 에는 남고 재생성 때 지워짐)에 센다. 한도에 닿으면
# 재시작 고리를 끊고 대기한다(포트 안 엶 → healthcheck unhealthy). 확인 후: docker restart kbo_backend
FAILS=/tmp/kbo_data_check_failures
if ! python data_check.py; then
  n=$(( $(cat "$FAILS" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$FAILS"
  if [ "$n" -ge "${KBO_DATA_MAX_ATTEMPTS:-5}" ]; then
    echo "[error] data: ${n}회 연속 준비 실패 — 재시작을 멈추고 대기한다(API 미기동). 마운트 확인 후 docker restart kbo_backend"
    exec sleep infinity
  fi
  echo "[error] data: 준비 안 됨(${n}/${KBO_DATA_MAX_ATTEMPTS:-5}) — ${KBO_DATA_RETRY_DELAY:-5}초 뒤 종료, 재시작 정책에 맡긴다"
  sleep "${KBO_DATA_RETRY_DELAY:-5}"
  exit 1
fi
rm -f "$FAILS"

# DB가 비어 있으면 최초 1회 시드 후 API 기동.
python seed_if_empty.py

exec uvicorn main:app --host 0.0.0.0 --port 8001
