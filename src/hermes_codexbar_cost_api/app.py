from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Annotated, Any
from urllib.error import URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from .dashboard import DASHBOARD_HTML
from .stats import ModelPricing, build_overview, build_quota_stats


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    state_db: str
    lookback_days: int = 30
    timezone_name: str = "Europe/Berlin"
    model_pricing: dict[str, ModelPricing] | None = None
    aether_models_url: str | None = None
    aether_pricing_ttl_seconds: int = 3600

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("HERMES_CODEXBAR_API_KEY")
        if not api_key and _truthy(os.getenv("HERMES_CODEXBAR_ALLOW_DEV_DEFAULT")):
            api_key = "dev-key"

        return cls(
            api_key=api_key,
            state_db=os.getenv("HERMES_STATE_DB", str(Path("~/.hermes/state.db").expanduser())),
            lookback_days=_int_env("HERMES_CODEXBAR_LOOKBACK_DAYS", 30),
            timezone_name=os.getenv("HERMES_CODEXBAR_TIMEZONE", "Europe/Berlin"),
            model_pricing=_model_pricing_env("HERMES_CODEXBAR_MODEL_PRICING_JSON"),
            aether_models_url=_optional_env(
                "HERMES_CODEXBAR_AETHER_MODELS_URL",
                "https://api.aetherapi.dev/v1/models",
            ),
            aether_pricing_ttl_seconds=_int_env("HERMES_CODEXBAR_AETHER_PRICING_TTL_SECONDS", 3600),
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    app = FastAPI(
        title="Hermes CodexBar Cost API",
        version="0.1.0",
        description="Local quota-stats adapter for CodexBar LLM Proxy using Hermes SQLite usage data.",
    )

    async def require_bearer_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if not app_settings.api_key:
            raise HTTPException(status_code=500, detail="HERMES_CODEXBAR_API_KEY is not configured")
        expected = f"Bearer {app_settings.api_key}"
        if authorization != expected:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/api/quota-stats", dependencies=[Depends(require_bearer_token)])
    @app.get("/api/v1/quota-stats", dependencies=[Depends(require_bearer_token)])
    @app.get("/v1/quota-stats", dependencies=[Depends(require_bearer_token)])
    async def quota_stats_get() -> dict[str, Any]:
        return _quota_stats(app_settings)

    @app.post("/api/quota-stats", dependencies=[Depends(require_bearer_token)])
    @app.post("/api/v1/quota-stats", dependencies=[Depends(require_bearer_token)])
    @app.post("/v1/quota-stats", dependencies=[Depends(require_bearer_token)])
    async def quota_stats_post(payload: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
        if payload and payload.get("action") not in (None, "force_refresh"):
            raise HTTPException(status_code=400, detail="Unsupported action")
        return _quota_stats(app_settings)

    @app.get("/api/overview", dependencies=[Depends(require_bearer_token)])
    async def overview(call_limit: Annotated[int, Query(ge=1, le=1000)] = 30) -> dict[str, Any]:
        return _overview(app_settings, call_limit=call_limit)

    return app


def _quota_stats(settings: Settings) -> dict[str, Any]:
    return build_quota_stats(
        db_path=settings.state_db,
        lookback_days=settings.lookback_days,
        timezone_name=settings.timezone_name,
        model_pricing=_combined_model_pricing(settings),
    )


def _overview(settings: Settings, *, call_limit: int = 30) -> dict[str, Any]:
    return build_overview(
        db_path=settings.state_db,
        lookback_days=settings.lookback_days,
        timezone_name=settings.timezone_name,
        model_pricing=_combined_model_pricing(settings),
        call_limit=call_limit,
    )


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _optional_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    if not stripped or stripped.lower() in {"0", "false", "off", "none", "null"}:
        return None
    return stripped


def _model_pricing_env(name: str) -> dict[str, ModelPricing]:
    value = os.getenv(name)
    if value is None:
        return {}
    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}

    pricing: dict[str, ModelPricing] = {}
    for model_key, raw_prices in raw.items():
        if not isinstance(model_key, str) or not isinstance(raw_prices, dict):
            continue
        pricing[model_key] = ModelPricing(
            input_uncached=_float_value(raw_prices.get("input_uncached"), 0.0),
            input_cached=_float_value(raw_prices.get("input_cached"), 0.0),
            output=_float_value(raw_prices.get("output"), 0.0),
        )
    return pricing


def _float_value(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


_AETHER_PRICING_CACHE: dict[str, Any] = {"url": None, "expires_at": 0.0, "pricing": {}}


def _combined_model_pricing(settings: Settings) -> dict[str, ModelPricing]:
    pricing = dict(settings.model_pricing or {})
    pricing.update(_aether_model_pricing(settings.aether_models_url, settings.aether_pricing_ttl_seconds))
    return pricing


def _aether_model_pricing(url: str | None, ttl_seconds: int) -> dict[str, ModelPricing]:
    if not url:
        return {}

    now = time.time()
    ttl = max(60, ttl_seconds)
    cached_url = _AETHER_PRICING_CACHE.get("url")
    cached_pricing = _AETHER_PRICING_CACHE.get("pricing") or {}
    if cached_url == url and now < float(_AETHER_PRICING_CACHE.get("expires_at") or 0):
        return dict(cached_pricing)

    try:
        request = UrlRequest(url, headers={"User-Agent": "hermes-codexbar-cost-api/0.1"})
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        pricing = _aether_model_pricing_from_payload(payload)
        _AETHER_PRICING_CACHE.update({"url": url, "expires_at": now + ttl, "pricing": pricing})
        return dict(pricing)
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        backoff = min(300, ttl)
        _AETHER_PRICING_CACHE.update({"url": url, "expires_at": now + backoff, "pricing": cached_pricing})
        return dict(cached_pricing)


def _aether_cached_input_cost(model_id: str, model: dict[str, Any], input_cost: float) -> float:
    cached_value = model.get("cached_input_cost")
    if cached_value is not None:
        return _float_value(cached_value, input_cost)
    normalized_model = model_id.strip().lower()
    owner = str(model.get("owned_by") or "").strip().lower()
    is_openai_frontier_model = owner == "openai" and normalized_model.startswith(("gpt-4", "gpt-5", "o1", "o3", "o4"))
    if is_openai_frontier_model and input_cost > 0:
        # OpenAI-style prompt caching prices cached input at 10% of normal input.
        # Aether's model list currently omits cached_input_cost for GPT models even
        # though cached tokens are present in Hermes usage rows.
        return input_cost * 0.1
    return input_cost


def _aether_model_pricing_from_payload(payload: Any) -> dict[str, ModelPricing]:
    models = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(models, list):
        return {}

    pricing: dict[str, ModelPricing] = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        input_cost = _float_value(model.get("input_cost"), 0.0)
        output_cost = _float_value(model.get("output_cost"), 0.0)
        cached_input_cost = _aether_cached_input_cost(model_id, model, input_cost)
        if input_cost <= 0 and output_cost <= 0:
            continue
        model_pricing = ModelPricing(
            input_uncached=input_cost,
            input_cached=cached_input_cost,
            output=output_cost,
        )
        for provider in ("aether", "custom", "custom:aether"):
            pricing[f"{provider}/{model_id}"] = model_pricing
    return pricing


app = create_app()
