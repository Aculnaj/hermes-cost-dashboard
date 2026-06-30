from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from zoneinfo import ZoneInfo

import httpx
import pytest

from hermes_codexbar_cost_api.app import Settings, _aether_model_pricing_from_payload, create_app
from hermes_codexbar_cost_api.stats import ModelPricing, TokenTotals, _calculate_model_cost, _provider_for_model, build_quota_stats


@pytest.mark.asyncio
async def test_healthz_without_api_key() -> None:
    async with _client_for_settings(Settings(api_key=None, state_db="/missing.db")) as client:
        response = await client.get("/healthz")

    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_quota_stats_requires_bearer_token(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    async with _client(db) as client:
        missing = await client.get("/v1/quota-stats")
        wrong = await client.get("/v1/quota-stats", headers={"Authorization": "Bearer wrong"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_api_quota_stats_aliases_match_compatibility_endpoint(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    _insert_session(db, billing_provider="openai-api", api_call_count=2, estimated_cost_usd=1.5)

    async with _client(db) as client:
        compat = await client.get("/v1/quota-stats", headers=_auth())
        versioned = await client.get("/api/v1/quota-stats", headers=_auth())
        unversioned = await client.get("/api/quota-stats", headers=_auth())
        refresh = await client.post("/api/v1/quota-stats", json={"action": "force_refresh"}, headers=_auth())

    assert compat.status_code == 200
    assert versioned.status_code == 200
    assert unversioned.status_code == 200
    assert refresh.status_code == 200
    assert list(compat.json()["providers"]) == ["today", "this_month", "Hermes", "openai-api"]
    assert list(versioned.json()["providers"]) == list(compat.json()["providers"])
    assert list(unversioned.json()["providers"]) == list(compat.json()["providers"])
    assert versioned.json()["providers"]["Hermes"]["total_requests"] == 2
    assert unversioned.json()["providers"]["Hermes"]["approx_cost"] == 1.5
    assert refresh.json()["providers"]["Hermes"]["total_requests"] == compat.json()["providers"]["Hermes"][
        "total_requests"
    ]


@pytest.mark.asyncio
async def test_api_overview_requires_bearer_token(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)

    async with _client(db) as client:
        missing = await client.get("/api/overview")
        wrong = await client.get("/api/overview", headers={"Authorization": "Bearer wrong"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_api_overview_returns_dashboard_analytics_shape(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    now = datetime.now(timezone.utc)

    _insert_session(
        db,
        billing_provider="openai-api",
        model="gpt-5",
        source="codex",
        api_call_count=3,
        input_tokens=100,
        cache_read_tokens=20,
        output_tokens=50,
        estimated_cost_usd=2.25,
        updated_at=now.isoformat(),
    )
    _insert_session(
        db,
        billing_provider="custom:aether",
        model="aether-large",
        source="hermes",
        api_call_count=1,
        input_tokens=40,
        output_tokens=10,
        estimated_cost_usd=0.5,
        updated_at=(now - timedelta(days=1)).isoformat(),
    )
    _insert_message(db, session_id=1, role="assistant", timestamp=now.timestamp(), finish_reason="tool_calls", tool_calls='[{"name":"terminal"}]')
    _insert_message(db, session_id=1, role="assistant", timestamp=(now - timedelta(minutes=1)).timestamp(), finish_reason="stop")

    settings = Settings(api_key="test-key", state_db=str(db), lookback_days=7, timezone_name="UTC")
    async with _client_for_settings(settings) as client:
        response = await client.get("/api/overview", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["timezone"] == "UTC"
    assert data["lookback_days"] == 7
    assert set(data["summary"]) == {"today", "this_week", "this_month", "lookback_total"}
    assert data["summary"]["lookback_total"]["requests"] == 4
    assert data["summary"]["lookback_total"]["approx_cost"] == 2.75
    assert len(data["daily"]) >= 7
    assert len(data["hourly"]) == 24
    assert {"date", "requests", "total_tokens", "approx_cost"} <= set(data["daily"][0])
    assert {"hour", "requests", "total_tokens", "approx_cost"} <= set(data["hourly"][0])
    assert sum(hour["requests"] for hour in data["hourly"]) == 2
    assert round(sum(hour["approx_cost"] for hour in data["hourly"]), 2) == 2.25

    providers = {provider["key"]: provider for provider in data["providers"]}
    assert providers["hermes"]["kind"] == "aggregate"
    assert providers["hermes"]["requests"] == 4
    assert providers["openai-api"]["approx_cost"] == 2.25
    assert providers["aether"]["requests"] == 1

    models = {model["key"]: model for model in data["models"]}
    assert models["gpt-5"]["providers"] == ["openai-api"]
    assert models["aether-large"]["providers"] == ["aether"]

    sources = {source["key"]: source for source in data["sources"]}
    assert sources["codex-cli"]["requests"] == 3
    assert sources["hermes-cli"]["requests"] == 1

    assert data["recent_sessions"][0]["provider"] == "openai-api"
    assert data["recent_sessions"][0]["source"] == "codex-cli"
    assert {"session_id", "session_title", "client", "occurred_at", "provider", "model", "source", "requests", "tokens", "approx_cost"} <= set(
        data["recent_sessions"][0]
    )
    assert data["recent_calls"][0]["provider"] == "openai-api"
    assert data["recent_calls"][0]["finish_reason"] == "tool_calls"
    assert data["recent_calls"][0]["tool_call_count"] == 1


@pytest.mark.asyncio
async def test_quota_stats_aggregates_hermes_sessions(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)

    _insert_session(
        db,
        billing_provider="openai",
        model="gpt-5",
        source="codex",
        api_call_count=3,
        input_tokens=100,
        cache_read_tokens=10,
        cache_write_tokens=5,
        output_tokens=40,
        reasoning_tokens=7,
        estimated_cost_usd=1.25,
        actual_cost_usd=None,
        archived=0,
        updated_at=now.isoformat(),
    )
    _insert_session(
        db,
        billing_provider="anthropic",
        model="claude",
        source="hermes",
        api_call_count=2,
        input_tokens=20,
        cache_read_tokens=3,
        cache_write_tokens=2,
        output_tokens=8,
        reasoning_tokens=1,
        estimated_cost_usd=99.0,
        actual_cost_usd=0.75,
        archived=0,
        updated_at=now.isoformat(),
    )
    _insert_session(
        db,
        billing_provider="openai",
        model="old",
        source="codex",
        api_call_count=100,
        input_tokens=1000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=1000,
        reasoning_tokens=0,
        estimated_cost_usd=100.0,
        actual_cost_usd=None,
        archived=0,
        updated_at=old.isoformat(),
    )
    _insert_session(
        db,
        billing_provider="openai",
        model="archived",
        source="codex",
        api_call_count=100,
        input_tokens=1000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=1000,
        reasoning_tokens=0,
        estimated_cost_usd=100.0,
        actual_cost_usd=None,
        archived=1,
        updated_at=now.isoformat(),
    )

    async with _client(db) as client:
        response = await client.get("/v1/quota-stats", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert list(data["providers"]) == ["today", "this_month", "Hermes"]
    assert "hermes" not in data["providers"]
    assert "hermes_billing" not in data["providers"]
    assert data["providers"]["Hermes"]["total_requests"] == 5
    assert data["providers"]["Hermes"]["approx_cost"] == 2.0
    assert data["providers"]["today"]["quota_groups"] == {}
    assert data["providers"]["this_month"]["quota_groups"] == {}
    assert data["summary"]["total_providers"] == 3
    assert data["summary"]["active_credentials"] == 3
    assert isinstance(data["timestamp"], float)


@pytest.mark.asyncio
async def test_quota_stats_calculates_cost_from_model_pricing_when_costs_are_not_positive(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)

    _insert_session(
        db,
        billing_provider="openai",
        model="gpt-5.5",
        input_tokens=1_000_000,
        cache_read_tokens=500_000,
        cache_write_tokens=500_000,
        output_tokens=1_000_000,
        estimated_cost_usd=0.0,
        actual_cost_usd=0.0,
    )
    _insert_session(
        db,
        billing_provider="openai",
        model="gpt-5.5",
        input_tokens=10_000_000,
        output_tokens=10_000_000,
        estimated_cost_usd=0.25,
        actual_cost_usd=0.0,
    )
    _insert_session(
        db,
        billing_provider="openai",
        model="gpt-5.5",
        input_tokens=10_000_000,
        output_tokens=10_000_000,
        estimated_cost_usd=99.0,
        actual_cost_usd=0.5,
    )

    settings = Settings(
        api_key="test-key",
        state_db=str(db),
        lookback_days=30,
        model_pricing={
            "gpt-5.5": ModelPricing(input_uncached=100.0, input_cached=100.0, output=100.0),
            "openai/gpt-5.5": ModelPricing(input_uncached=1.25, input_cached=0.125, output=10.0),
        },
    )
    async with _client_for_settings(settings) as client:
        response = await client.get("/v1/quota-stats", headers=_auth())

    assert response.status_code == 200
    hermes = response.json()["providers"]["Hermes"]
    assert hermes["approx_cost"] == 12.125
    assert hermes["credentials"][0]["approx_cost"] == 12.125


def test_quota_stats_adds_local_spending_overview_windows(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    berlin = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 6, 17, 12, 0, tzinfo=berlin)

    _insert_session(
        db,
        billing_provider="openai-api",
        api_call_count=1,
        estimated_cost_usd=1.0,
        updated_at=datetime(2026, 6, 17, 8, 0, tzinfo=berlin).isoformat(),
    )
    _insert_session(
        db,
        billing_provider="openai",
        api_call_count=2,
        estimated_cost_usd=2.0,
        updated_at=datetime(2026, 6, 16, 8, 0, tzinfo=berlin).isoformat(),
    )
    _insert_session(
        db,
        billing_provider="openai",
        api_call_count=4,
        estimated_cost_usd=4.0,
        updated_at=datetime(2026, 6, 10, 8, 0, tzinfo=berlin).isoformat(),
    )
    _insert_session(
        db,
        billing_provider="custom:aether",
        model="glm-5.2",
        api_call_count=5,
        estimated_cost_usd=0.5,
        updated_at=datetime(2026, 6, 17, 9, 0, tzinfo=berlin).isoformat(),
    )
    _insert_session(
        db,
        billing_provider="openai",
        api_call_count=8,
        estimated_cost_usd=8.0,
        updated_at=datetime(2026, 5, 31, 8, 0, tzinfo=berlin).isoformat(),
    )

    data = build_quota_stats(
        db_path=db,
        lookback_days=30,
        timezone_name="Europe/Berlin",
        now=now,
    )

    assert list(data["providers"]) == ["today", "this_month", "Hermes", "openai-api"]
    assert "hermes" not in data["providers"]
    assert "hermes_billing" not in data["providers"]
    assert data["providers"]["openai-api"]["total_requests"] == 1
    assert data["providers"]["openai-api"]["approx_cost"] == 1.0
    assert data["providers"]["Hermes"]["total_requests"] == 20
    assert data["providers"]["Hermes"]["approx_cost"] == 15.5

    assert data["providers"]["today"]["total_requests"] == 6
    assert data["providers"]["today"]["approx_cost"] == 1.5
    assert data["providers"]["this_month"]["total_requests"] == 12
    assert data["providers"]["this_month"]["approx_cost"] == 7.5

    for provider in data["providers"].values():
        assert provider["quota_groups"] == {}


def test_quota_stats_keeps_empty_spending_windows_visible(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    berlin = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 6, 17, 12, 0, tzinfo=berlin)

    _insert_session(
        db,
        billing_provider="openai-api",
        api_call_count=3,
        estimated_cost_usd=1.25,
        updated_at=datetime(2026, 5, 31, 8, 0, tzinfo=berlin).isoformat(),
    )

    data = build_quota_stats(
        db_path=db,
        lookback_days=30,
        timezone_name="Europe/Berlin",
        now=now,
    )

    assert list(data["providers"]) == ["today", "this_month", "Hermes", "openai-api"]
    assert data["providers"]["today"]["total_requests"] == 0
    assert data["providers"]["Hermes"]["total_requests"] == 3
    assert data["providers"]["this_month"]["total_requests"] == 0
    assert data["providers"]["openai-api"]["total_requests"] == 3


def test_aether_only_model_corrects_stale_openai_provider() -> None:
    pricing = {
        "aether/glm-5.2": ModelPricing(input_uncached=0.55, input_cached=0.09, output=1.75),
        "openai-api/gpt-5.5": ModelPricing(input_uncached=5, input_cached=0.5, output=30),
        "aether/gpt-5.5": ModelPricing(input_uncached=3.5, input_cached=3.5, output=21),
    }

    assert _provider_for_model("openai-api", "glm-5.2", pricing) == "aether"
    assert _provider_for_model("openai-api", "gpt-5.5", pricing) == "openai-api"
    assert _provider_for_model("custom:aether", "gpt-5.5", pricing) == "openai-api"
    assert _provider_for_model("custom:aether", "gpt-5.5", pricing, is_active_session=True) == "openai-api"


def test_corrected_provider_wins_pricing_lookup() -> None:
    pricing = {
        "openai-api/gpt-5.5": ModelPricing(input_uncached=5, input_cached=0.5, output=30),
        "custom:aether/gpt-5.5": ModelPricing(input_uncached=3.5, input_cached=3.5, output=21),
        "aether/gpt-5.5": ModelPricing(input_uncached=3.5, input_cached=3.5, output=21),
    }
    tokens = TokenTotals(input_uncached=1_000_000, input_cached=1_000_000, output=1_000_000)

    assert _calculate_model_cost("custom:aether", "openai-api", "gpt-5.5", tokens, pricing) == 35.5
    assert _calculate_model_cost("custom:aether", "aether", "gpt-5.5", tokens, pricing) == 28.0


def test_aether_models_payload_adds_provider_scoped_pricing() -> None:
    pricing = _aether_model_pricing_from_payload(
        {
            "object": "list",
            "data": [
                {
                    "id": "kimi-k2.6",
                    "input_cost": 0.105,
                    "cached_input_cost": 0.0275,
                    "output_cost": 0.49,
                },
                {
                    "id": "gpt-5.5",
                    "owned_by": "OpenAI",
                    "input_cost": 3.5,
                    "cached_input_cost": None,
                    "output_cost": 21,
                },
            ],
        }
    )

    assert pricing["aether/kimi-k2.6"] == ModelPricing(
        input_uncached=0.105,
        input_cached=0.0275,
        output=0.49,
    )
    assert pricing["custom/kimi-k2.6"] == pricing["aether/kimi-k2.6"]
    assert pricing["custom:aether/kimi-k2.6"] == pricing["aether/kimi-k2.6"]
    assert pricing["aether/gpt-5.5"].input_cached == pytest.approx(0.35)
    assert "gpt-5.5" not in pricing


@pytest.mark.asyncio
async def test_quota_stats_missing_db_returns_error_payload(tmp_path) -> None:
    async with _client(tmp_path / "missing.db") as client:
        response = await client.get("/v1/quota-stats", headers=_auth())

    assert response.status_code == 200
    hermes = response.json()["providers"]["Hermes"]
    assert hermes["status"] == "error"
    assert hermes["active_count"] == 0
    assert hermes["credentials"][0]["status"] == "disabled"
    assert hermes["total_requests"] == 0


@pytest.mark.asyncio
async def test_quota_stats_post_force_refresh_and_empty_body(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    _insert_session(db, api_call_count=1)
    async with _client(db) as client:
        refresh = await client.post("/v1/quota-stats", json={"action": "force_refresh"}, headers=_auth())
        empty = await client.post("/v1/quota-stats", headers=_auth())

    assert refresh.status_code == 200
    assert empty.status_code == 200
    assert refresh.json()["providers"]["Hermes"]["total_requests"] == 1
    assert empty.json()["providers"]["Hermes"]["total_requests"] == 1


@pytest.mark.asyncio
async def test_quota_stats_post_rejects_unknown_action(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    async with _client(db) as client:
        response = await client.post("/v1/quota-stats", json={"action": "other"}, headers=_auth())

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_quota_stats_excludes_hermes_rows_when_provider_data_exists(tmp_path) -> None:
    db = tmp_path / "state.db"
    _create_db(db)
    _insert_session(db, billing_provider="hermes", api_call_count=4)
    _insert_session(db, billing_provider="openai-api", api_call_count=2)

    async with _client(db) as client:
        response = await client.get("/v1/quota-stats", headers=_auth())

    providers = response.json()["providers"]
    assert list(providers) == ["today", "this_month", "Hermes", "openai-api"]
    assert "hermes" not in providers
    assert "hermes_billing" not in providers
    assert providers["openai-api"]["total_requests"] == 2
    assert providers["Hermes"]["total_requests"] == 6


def test_settings_from_env_parses_model_pricing_json(monkeypatch) -> None:
    monkeypatch.delenv("HERMES_CODEXBAR_TIMEZONE", raising=False)
    monkeypatch.setenv(
        "HERMES_CODEXBAR_MODEL_PRICING_JSON",
        '{"gpt-5.5":{"input_uncached":1.25,"input_cached":0.125,"output":10},'
        '"bad-entry":null}',
    )

    settings = Settings.from_env()

    assert settings.model_pricing == {
        "gpt-5.5": ModelPricing(input_uncached=1.25, input_cached=0.125, output=10.0)
    }
    assert settings.timezone_name == "Europe/Berlin"


def _client(db_path) -> httpx.AsyncClient:
    settings = Settings(
        api_key="test-key",
        state_db=str(db_path),
        lookback_days=30,
    )
    return _client_for_settings(settings)


def _client_for_settings(settings: Settings) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(settings))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-key"}


def _create_db(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY,
                billing_provider TEXT,
                model TEXT,
                source TEXT,
                api_call_count INTEGER,
                input_tokens INTEGER,
                cache_read_tokens INTEGER,
                cache_write_tokens INTEGER,
                output_tokens INTEGER,
                reasoning_tokens INTEGER,
                estimated_cost_usd REAL,
                actual_cost_usd REAL,
                archived INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                role TEXT,
                timestamp REAL,
                finish_reason TEXT,
                tool_calls TEXT,
                active INTEGER DEFAULT 1
            )
            """
        )


def _insert_session(
    path,
    *,
    billing_provider="openai",
    model="gpt-5",
    source="codex",
    api_call_count=0,
    input_tokens=0,
    cache_read_tokens=0,
    cache_write_tokens=0,
    output_tokens=0,
    reasoning_tokens=0,
    estimated_cost_usd=0.0,
    actual_cost_usd=None,
    archived=0,
    updated_at=None,
) -> None:
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                billing_provider,
                model,
                source,
                api_call_count,
                input_tokens,
                cache_read_tokens,
                cache_write_tokens,
                output_tokens,
                reasoning_tokens,
                estimated_cost_usd,
                actual_cost_usd,
                archived,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                billing_provider,
                model,
                source,
                api_call_count,
                input_tokens,
                cache_read_tokens,
                cache_write_tokens,
                output_tokens,
                reasoning_tokens,
                estimated_cost_usd,
                actual_cost_usd,
                archived,
                updated_at,
            ),
        )


def _insert_message(
    path,
    *,
    session_id=1,
    role="assistant",
    timestamp=None,
    finish_reason="stop",
    tool_calls=None,
    active=1,
) -> None:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).timestamp()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO messages (session_id, role, timestamp, finish_reason, tool_calls, active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, role, timestamp, finish_reason, tool_calls, active),
        )
