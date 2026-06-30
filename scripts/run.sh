#!/usr/bin/env sh
set -eu

# Load project-local configuration when present. This keeps manual restarts from
# accidentally dropping HERMES_CODEXBAR_API_KEY and breaking the dashboard API.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8787}"

python -m uvicorn hermes_codexbar_cost_api.app:app --host "$HOST" --port "$PORT"
