# Hermes CodexBar Cost API

A small local FastAPI service that reads Hermes usage from `~/.hermes/state.db`, serves a web spend dashboard, and exposes CodexBar's LLM Proxy-compatible quota stats format.

This service is a stats adapter only. It does not proxy LLM requests.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

## Configure

Create a local environment from `.env.example` or export the values directly:

```bash
export HERMES_CODEXBAR_API_KEY='replace-with-a-long-random-token'
export HERMES_STATE_DB="$HOME/.hermes/state.db"
export HERMES_CODEXBAR_TIMEZONE=Europe/Berlin
export HERMES_CODEXBAR_LOOKBACK_DAYS=30
export HERMES_CODEXBAR_MODEL_PRICING_JSON='{"gpt-5.5":{"input_uncached":1.25,"input_cached":0.125,"output":10}}'
```

`HERMES_CODEXBAR_API_KEY` is required for `/v1/quota-stats`, `/api/v1/quota-stats`, `/api/quota-stats`, and `/api/overview`. The web dashboard at `/` asks for this key in the browser and stores it in `localStorage`.

`HERMES_CODEXBAR_TIMEZONE` controls the local day, week, and month used by the synthetic spending overview rows. It defaults to `Europe/Berlin`. Weeks start on Monday.

`HERMES_CODEXBAR_LOOKBACK_DAYS` controls the full aggregate window for `providers.hermes` and real provider rows. It defaults to `30`.

`HERMES_CODEXBAR_MODEL_PRICING_JSON` is optional. It fills in `approx_cost` when Hermes has no positive `actual_cost_usd` or `estimated_cost_usd` for a session row. The value must be a JSON object keyed by `model` or `provider/model`; `provider/model` takes precedence when both are present. Prices are USD per 1M tokens:

```json
{
  "gpt-5.5": {
    "input_uncached": 1.25,
    "input_cached": 0.125,
    "output": 10
  },
  "openai/gpt-5.5": {
    "input_uncached": 1.25,
    "input_cached": 0.125,
    "output": 10
  }
}
```

## Run

```bash
HERMES_CODEXBAR_API_KEY=replace-with-a-long-random-token \
python -m uvicorn hermes_codexbar_cost_api.app:app --host 127.0.0.1 --port 8787
```

Or:

```bash
HERMES_CODEXBAR_API_KEY=replace-with-a-long-random-token scripts/run.sh
```

## CodexBar Setup

In CodexBar settings:

- Provider: `LLM Proxy`
- Base URL: `https://your-host.example/api`
- API key: the same value as `HERMES_CODEXBAR_API_KEY`

CodexBar appends `/v1/quota-stats`, so the recommended hosted base URL is:

```text
https://your-host.example/api
```

For local-only use, set the base URL to:

```text
http://127.0.0.1:8787/api
```

CLI API key setup:

```bash
printf '%s' "$HERMES_CODEXBAR_API_KEY" | codexbar config set-api-key --provider llmproxy --stdin
```

Set the LLM Proxy enterprise host to:

```text
https://your-host.example/api
```

## Endpoints

Open the web dashboard:

```text
http://127.0.0.1:8787/
```

```bash
curl -s http://127.0.0.1:8787/healthz
curl -s -H "Authorization: Bearer $HERMES_CODEXBAR_API_KEY" \
  http://127.0.0.1:8787/api/v1/quota-stats | python -m json.tool
curl -s -H "Authorization: Bearer $HERMES_CODEXBAR_API_KEY" \
  http://127.0.0.1:8787/api/quota-stats | python -m json.tool
curl -s -H "Authorization: Bearer $HERMES_CODEXBAR_API_KEY" \
  http://127.0.0.1:8787/api/overview | python -m json.tool
curl -s -X POST -H "Authorization: Bearer $HERMES_CODEXBAR_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"action":"force_refresh"}' \
  http://127.0.0.1:8787/api/v1/quota-stats | python -m json.tool
```

`GET /v1/quota-stats` and `POST /v1/quota-stats` remain available for compatibility. The preferred CodexBar paths are `/api/v1/quota-stats` and `/api/quota-stats`.

`POST /v1/quota-stats` and `POST /api/v1/quota-stats` accept an empty body or `{"action":"force_refresh"}`. Aggregation is live from SQLite, so refresh just re-runs the query.

`GET /api/overview` returns dashboard analytics: summary cards for today, this week, this month, and the full lookback window; provider and model breakdowns; daily cost/token/request time series; and recent sessions.

## Response Shape

The response contains a synthetic `providers.hermes` aggregate, real provider breakdowns such as `providers.openai`, `providers.openai-api`, `providers.anthropic`, or `providers.aether` when those appear in Hermes sessions, and spending overview rows named `providers.today`, `providers.this_week`, and `providers.this_month`.

`quota_groups` is always an empty object. The adapter reports spending only; it does not expose daily, weekly, or monthly budgets.

```json
{
  "providers": {
    "hermes": {
      "credential_count": 1,
      "active_count": 1,
      "exhausted_count": 0,
      "total_requests": 123,
      "tokens": {
        "input_cached": 1,
        "input_uncached": 2,
        "output": 3
      },
      "approx_cost": 3.5,
      "quota_groups": {},
      "credentials": []
    },
    "today": {
      "credential_count": 1,
      "active_count": 1,
      "exhausted_count": 0,
      "total_requests": 12,
      "tokens": {
        "input_cached": 1,
        "input_uncached": 2,
        "output": 3
      },
      "approx_cost": 1.0,
      "quota_groups": {},
      "credentials": []
    }
  },
  "summary": {
    "total_providers": 1,
    "total_credentials": 1,
    "active_credentials": 1
  },
  "timestamp": 1782137533.0
}
```

## Aggregation

The SQLite database is opened read-only using `file:/path/state.db?mode=ro`. The adapter reads non-archived `sessions` rows within the configured lookback window and aggregates:

- Requests: `api_call_count`
- Uncached input tokens: `input_tokens`
- Cached input tokens: `cache_read_tokens + cache_write_tokens`
- Output tokens: `output_tokens + reasoning_tokens`
- Cost: positive `actual_cost_usd`, otherwise positive `estimated_cost_usd`, otherwise optional configured model pricing, otherwise `0`

`approx_cost`, `tokens`, and `total_requests` on `providers.hermes` and real provider rows are the full configured lookback aggregate. `providers.today`, `providers.this_week`, and `providers.this_month` are synthetic spending overview rows scoped to the current local day, week, and month. Spending overview windows use `updated_at` when present, otherwise `started_at`.

If the database or `sessions` table is missing, `/v1/quota-stats` and the `/api` stats aliases still return HTTP 200 with `providers.hermes.status = "error"` and zero usage so CodexBar can keep polling. `/api/overview` reports `status = "error"` with empty analytics arrays.

## Test

```bash
python -m pytest -q
```
