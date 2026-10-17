#!/usr/bin/env bash
# Migration round trip plus DB smoke tests, as CI runs them:
#   up -> tests/db_smoke.sql -> down -all -> up
# Needs an EMPTY database (the smoke test relies on fresh identity values) and
# refuses to run against one that has tables, because `down -all` drops everything.
#
#   MIGRATE_DATABASE_URL=postgres://app:app@localhost:5432/app_check?sslmode=disable scripts/db-check.sh
set -euo pipefail

: "${MIGRATE_DATABASE_URL:?set MIGRATE_DATABASE_URL to an empty throwaway database}"
MIGRATE="${MIGRATE:-migrate}"
cd "$(dirname "$0")/.."

tables=$(psql "$MIGRATE_DATABASE_URL" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
if [ "$tables" != "0" ]; then
  echo "refusing to run: database is not empty ($tables tables in public)" >&2
  exit 2
fi

run_migrate() { "$MIGRATE" -path migrations -database "$MIGRATE_DATABASE_URL" "$@"; }

echo "== up"
run_migrate up

echo "== smoke tests"
out=$(mktemp)
psql "$MIGRATE_DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/db_smoke.sql 2>&1 | tee "$out"
if grep -E 'FAIL|ERROR' "$out"; then
  echo "smoke tests failed" >&2
  exit 1
fi
echo "smoke tests ok ($(grep -c 'ok   rejected' "$out") constraint rejections checked)"

echo "== down -all"
run_migrate down -all

echo "== up again"
run_migrate up
echo "migration round trip ok"
