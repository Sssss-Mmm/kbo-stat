#!/usr/bin/env bash
# kbo_dashboard_db 백업(읽기 전용). 소유자·권한 문을 빼서(--no-owner --no-privileges) 역할이 없는 빈 PostgreSQL 에도 복원된다.
#
#   bash scripts/backup_db.sh [출력.sql.gz] [--verify]
#
# --verify: 임시 postgres 컨테이너(빈 DB, kbo_user 역할 없음)에 복원해 모든 테이블 행 수를 운영 DB 와 비교하고 지운다.
# 비밀번호는 컨테이너 안의 환경변수만 쓰고 출력하지 않는다.
# 복원(빈 DB):  zcat 백업.sql.gz | psql -v ON_ERROR_STOP=1 -U <사용자> -d <DB>
set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/docker_engine.sh"
require_kbo_engine || exit 5

DB_CONTAINER="${DB_CONTAINER:-kbo_dashboard_db}"
OUT="${1:-backup-$(date +%F-%H%M).sql.gz}"
VERIFY="${2:-}"
[[ "$OUT" == "--verify" ]] && { OUT="backup-$(date +%F-%H%M).sql.gz"; VERIFY="--verify"; }

docker exec "$DB_CONTAINER" sh -c 'pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > "$OUT"
gzip -t "$OUT"
echo "[backup] $OUT $(du -h "$OUT" | cut -f1) · 테이블 $(zcat "$OUT" | grep -c '^COPY ')개"

[[ "$VERIFY" == "--verify" ]] || exit 0

COUNTS="SELECT string_agg(format('%s.%s=%s', schemaname, relname, n), ' ' ORDER BY schemaname, relname) FROM (
  SELECT schemaname, relname, (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', schemaname, relname), false, true, '')))[1]::text::bigint AS n
  FROM pg_stat_user_tables) t"
name="kbo_backup_verify_$$"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$name" --network none -e POSTGRES_PASSWORD="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')" \
  -e POSTGRES_USER=restore_check -e POSTGRES_DB=restore_check postgres:15-alpine >/dev/null
for _ in $(seq 1 60); do docker exec "$name" pg_isready -U restore_check -d restore_check >/dev/null 2>&1 && break; sleep 1; done
sleep 2
zcat "$OUT" | docker exec -i "$name" psql -q -v ON_ERROR_STOP=1 -U restore_check -d restore_check >/dev/null
roles=$(docker exec "$name" psql -At -U restore_check -d restore_check -c "SELECT count(*) FROM pg_roles WHERE rolname = 'kbo_user'")
live=$(docker exec "$DB_CONTAINER" sh -c 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$COUNTS")
restored=$(docker exec "$name" psql -At -U restore_check -d restore_check -c "$COUNTS")
if [[ "$live" != "$restored" ]]; then
  echo "[backup] FAIL: 복원한 행 수가 운영과 다르다" >&2
  diff <(tr ' ' '\n' <<<"$live") <(tr ' ' '\n' <<<"$restored") >&2 || true
  exit 1
fi
echo "[backup] verify OK: 빈 PostgreSQL(kbo_user 역할 ${roles}개)에 복원 · 테이블 $(wc -w <<<"$restored")개 행 수 운영과 동일"
