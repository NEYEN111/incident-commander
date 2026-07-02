#!/usr/bin/env bash
# End-to-end smoke test: boots the REAL docker-compose stack (no testcontainers,
# no mocks) and exercises login -> declare-incident over HTTP, so it catches
# deploy-path bugs (missing DB commit, migration/startup ordering, hook wiring)
# that unit tests never touch.
set -euo pipefail

# Always operate from the repo root, regardless of the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PROJECT="ic-smoke"
PORT="${SMOKE_PORT:-18000}"
BASE="http://localhost:${PORT}"

# secrets — pure-stdlib, generated fresh every run, never hardcoded/committed.
export APP_PORT="$PORT"
export BASE_URL="$BASE"           # required so the CSRF Origin/Referer check accepts our requests
export SESSION_HTTPS_ONLY="false" # curl over plain http must receive the session cookie
SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export SESSION_SECRET
FERNET_KEYS="$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
export FERNET_KEYS

JAR="$(mktemp)"

compose() { docker compose -p "$PROJECT" "$@"; }
cleanup() {
  rm -f "$JAR"
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Issue a request, return only the HTTP status code (never fails on non-2xx
# so callers can assert the expected code themselves — logins/declares 303).
req() {
  curl -s -o /dev/null -w '%{http_code}' -c "$JAR" -b "$JAR" \
    -H "Origin: $BASE" -H "Referer: $BASE/" "$@"
}

fail() {
  echo "SMOKE-FAIL: $1"
  echo "---- app logs (tail) ----"
  compose logs app 2>&1 | tail -80
  exit 1
}

echo "== bring up the stack (project=$PROJECT port=$PORT) =="
compose up -d --build

echo "== wait for /healthz =="
up=""
for i in $(seq 1 90); do
  if curl -fsS "$BASE/healthz" >/dev/null 2>&1; then
    up=1
    break
  fi
  sleep 2
done
[ -n "$up" ] || fail "healthz never came up"

echo "== scrape bootstrap admin password from logs =="
PW="$(compose logs app 2>&1 | grep -oE 'Generated password \(shown once\): [^[:space:]]+' | tail -1 | awk '{print $NF}')"
[ -n "$PW" ] || fail "no bootstrap admin password found in app logs"

echo "== login =="
code="$(req -X POST --data-urlencode "email=admin@localhost" --data-urlencode "password=$PW" "$BASE/login")"
[ "$code" = "303" ] || fail "login expected 303, got $code"

echo "== clear forced password change (bootstrap admin has must_change_password) =="
code="$(req -X POST --data-urlencode "new_password=Smoke-123456" --data-urlencode "confirm=Smoke-123456" "$BASE/account/password")"
[ "$code" = "303" ] || fail "password change expected 303, got $code"

echo "== declare an incident (title only; severity is optional) =="
code="$(req -X POST --data-urlencode "title=Smoke test incident" "$BASE/incidents")"
[ "$code" = "303" ] || fail "declare incident expected 303, got $code"

echo "== assert it shows on the incidents list =="
if curl -fsS -c "$JAR" -b "$JAR" "$BASE/" | grep -q "Smoke test incident"; then
  echo "SMOKE-OK"
else
  fail "incident not visible on incidents list"
fi
