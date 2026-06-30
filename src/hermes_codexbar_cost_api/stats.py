from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass
class TokenTotals:
    input_cached: int = 0
    input_uncached: int = 0
    output: int = 0

    def add(self, other: "TokenTotals") -> None:
        self.input_cached += other.input_cached
        self.input_uncached += other.input_uncached
        self.output += other.output

    def as_dict(self) -> dict[str, int]:
        return {
            "input_cached": self.input_cached,
            "input_uncached": self.input_uncached,
            "output": self.output,
        }

    def total(self) -> int:
        return self.input_cached + self.input_uncached + self.output


@dataclass(frozen=True)
class ModelPricing:
    input_uncached: float = 0.0
    input_cached: float = 0.0
    output: float = 0.0


@dataclass
class GroupTotals:
    key: str
    requests: int = 0
    tokens: TokenTotals = field(default_factory=TokenTotals)
    cost: float = 0.0
    models: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)

    def add_row(self, row: "SessionUsage") -> None:
        self.requests += row.requests
        self.tokens.add(row.tokens)
        self.cost += row.cost
        if row.model:
            self.models.add(row.model)
        if row.source:
            self.sources.add(row.source)


@dataclass
class SessionUsage:
    provider: str
    model: str
    source: str
    requests: int
    tokens: TokenTotals
    cost: float
    timestamp: datetime | None
    session_id: str = ""
    session_title: str = ""
    client: str = "hermes"


@dataclass
class RecentCall:
    id: int
    session_id: str
    provider: str
    model: str
    source: str
    client: str
    timestamp: datetime | None
    finish_reason: str
    tool_call_count: int
    total_tokens: int
    approx_cost: float
    metric_basis: str
    session_title: str


@dataclass(frozen=True)
class SpendingWindow:
    start: datetime
    end: datetime


PROVIDER_ALIASES = {
    "custom": "aether",
    "custom:aether": "aether",
}
QUOTA_STATS_SPENDING_WINDOWS = ("today", "this_month")
QUOTA_STATS_PREFERRED_PROVIDERS = ("openai-api",)
QUOTA_STATS_EXCLUDED_PROVIDERS = {"hermes", "hermes_billing"}
MODEL_SWITCH_RE = re.compile(
    r"model was just switched from\s+(?P<from>[^\n]+?)\s+to\s+(?P<to>[^\n]+?)\s+via\s+(?P<via>[\w:.-]+)",
    re.IGNORECASE,
)


def build_quota_stats(
    db_path: str | Path,
    lookback_days: int,
    model_pricing: dict[str, ModelPricing] | None = None,
    *,
    timezone_name: str = "Europe/Berlin",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return CodexBar LLM Proxy-compatible quota stats for Hermes usage."""

    reference_time = _reference_time(now)
    timestamp = reference_time.timestamp()
    spending_timezone = _load_timezone(timezone_name)
    spending_windows = _spending_windows(reference_time, spending_timezone)
    try:
        expanded_db_path = Path(db_path).expanduser()
        sessions = _read_sessions(expanded_db_path, lookback_days, model_pricing or {}, reference_time)
        sessions.extend(_read_codex_sessions(expanded_db_path, lookback_days, model_pricing or {}, reference_time))
        status = "active"
        error = None
    except Exception as exc:
        sessions = []
        status = "error"
        error = str(exc)

    hermes = GroupTotals(key="Hermes")
    by_provider: dict[str, GroupTotals] = {}

    for session in sessions:
        hermes.add_row(session)
        by_provider.setdefault(session.provider, GroupTotals(session.provider)).add_row(session)

    providers: dict[str, Any] = {}

    today_window = spending_windows["today"]
    today_sessions = _sessions_in_window(sessions, today_window)
    today_totals = GroupTotals("today")
    for session in today_sessions:
        today_totals.add_row(session)
    providers["today"] = _provider_payload(
        name="today",
        totals=today_totals,
        status=status,
        credentials=_credential_payloads(today_sessions, status=status),
    )

    for window_name in (name for name in QUOTA_STATS_SPENDING_WINDOWS if name != "today"):
        spending_window = spending_windows[window_name]
        window_sessions = _sessions_in_window(sessions, spending_window)
        window_totals = GroupTotals(window_name)
        for session in window_sessions:
            window_totals.add_row(session)
        providers[window_name] = _provider_payload(
            name=window_name,
            totals=window_totals,
            status=status,
            credentials=_credential_payloads(window_sessions, status=status),
        )

    providers["Hermes"] = _provider_payload(
        name="Hermes",
        totals=hermes,
        status=status,
        credentials=_credential_payloads(sessions, status=status, error=error),
        error=error,
    )

    for provider_name in _quota_stats_provider_order(by_provider):
        totals = by_provider[provider_name]
        provider_sessions = [session for session in sessions if session.provider == provider_name]
        providers[provider_name] = _provider_payload(
            name=provider_name,
            totals=totals,
            status=status,
            credentials=_credential_payloads(provider_sessions, status=status),
        )

    if not sessions and "Hermes" not in providers:
        providers["Hermes"] = _provider_payload(
            name="Hermes",
            totals=hermes,
            status=status,
            credentials=_credential_payloads(sessions, status=status, error=error),
            error=error,
        )

    active_count = sum(provider["active_count"] for provider in providers.values())
    credential_count = sum(provider["credential_count"] for provider in providers.values())
    hermes_provider = providers.get("Hermes", {})
    hermes_tokens = hermes_provider.get("tokens", {})
    hermes_total_tokens = sum(hermes_tokens.values()) if isinstance(hermes_tokens, dict) else 0

    return {
        "providers": providers,
        "summary": {
            "total_providers": len(providers),
            "total_credentials": credential_count,
            "active_credentials": active_count,
            # CodexBar's top "Requests" row is hardcoded from summary.total_requests.
            # Keep it as the overall Hermes aggregate.
            "total_requests": hermes_provider.get("total_requests", 0),
            "total_tokens": hermes_total_tokens,
            "approx_cost": hermes_provider.get("approx_cost", 0.0),
        },
        "timestamp": timestamp,
    }


def _quota_stats_provider_order(by_provider: dict[str, GroupTotals]) -> list[str]:
    provider_names = set(by_provider) - QUOTA_STATS_EXCLUDED_PROVIDERS
    ordered = [provider_name for provider_name in QUOTA_STATS_PREFERRED_PROVIDERS if provider_name in provider_names]
    return ordered


def build_overview(
    db_path: str | Path,
    lookback_days: int,
    model_pricing: dict[str, ModelPricing] | None = None,
    *,
    timezone_name: str = "Europe/Berlin",
    now: datetime | None = None,
    recent_limit: int = 10000,
    call_limit: int = 30,
) -> dict[str, Any]:
    """Return dashboard-oriented Hermes spend analytics."""

    reference_time = _reference_time(now)
    spending_timezone = _load_timezone(timezone_name)
    spending_windows = _spending_windows(reference_time, spending_timezone)
    try:
        expanded_db_path = Path(db_path).expanduser()
        sessions = _read_sessions(expanded_db_path, lookback_days, model_pricing or {}, reference_time)
        sessions.extend(_read_codex_sessions(expanded_db_path, lookback_days, model_pricing or {}, reference_time))
        all_recent_calls = _read_recent_calls(
            expanded_db_path,
            lookback_days,
            reference_time,
            model_pricing or {},
            recent_limit=recent_limit,
        )
        all_recent_calls.extend(
            _read_codex_recent_calls(
                expanded_db_path,
                lookback_days,
                model_pricing or {},
                reference_time,
                recent_limit=recent_limit,
            )
        )
        all_recent_calls = _limit_recent_calls(all_recent_calls, recent_limit)
        recent_calls = _limit_recent_calls(all_recent_calls, call_limit)
        status = "active"
        error = None
    except Exception as exc:
        sessions = []
        all_recent_calls = []
        recent_calls = []
        status = "error"
        error = str(exc)

    lookback_total = GroupTotals("lookback_total")
    by_provider: dict[str, GroupTotals] = {}
    by_model: dict[str, GroupTotals] = {}
    by_source: dict[str, GroupTotals] = {}
    by_model_providers: dict[str, set[str]] = {}

    for session in sessions:
        lookback_total.add_row(session)
        by_provider.setdefault(session.provider, GroupTotals(session.provider)).add_row(session)
        by_source.setdefault(session.source or "unknown-source", GroupTotals(session.source or "unknown-source")).add_row(session)
        model_name = session.model or "unknown-model"
        by_model.setdefault(model_name, GroupTotals(model_name)).add_row(session)
        by_model_providers.setdefault(model_name, set()).add(session.provider)

    summary: dict[str, Any] = {
        "lookback_total": _overview_totals_payload("Lookback total", lookback_total),
    }
    for window_name, spending_window in spending_windows.items():
        window_totals = GroupTotals(window_name)
        for session in _sessions_in_window(sessions, spending_window):
            window_totals.add_row(session)
        summary[window_name] = {
            **_overview_totals_payload(_summary_label(window_name), window_totals),
            "start": spending_window.start.isoformat(),
            "end": spending_window.end.isoformat(),
        }

    providers = [
        {
            **_overview_totals_payload("Hermes", lookback_total),
            "key": "hermes",
            "kind": "aggregate",
            "status": status,
        }
    ]
    if error:
        providers[0]["error"] = error

    for provider_name, totals in sorted(by_provider.items(), key=lambda item: (-item[1].cost, item[0])):
        provider_key = provider_name if provider_name != "hermes" else "hermes_billing"
        providers.append(
            {
                **_overview_totals_payload(provider_key, totals),
                "key": provider_key,
                "kind": "provider",
                "status": status,
            }
        )

    models = [
        {
            **_overview_totals_payload(model_name, totals),
            "key": model_name,
            "providers": sorted(by_model_providers.get(model_name, set())),
        }
        for model_name, totals in sorted(by_model.items(), key=lambda item: (-item[1].cost, item[0]))
    ]

    sources = [
        {
            **_overview_totals_payload(source_name, totals),
            "key": source_name,
        }
        for source_name, totals in sorted(by_source.items(), key=lambda item: (-item[1].cost, item[0]))
    ]

    return {
        "status": status,
        "error": error,
        "generated_at": reference_time.astimezone(spending_timezone).isoformat(),
        "timezone": timezone_name,
        "lookback_days": lookback_days,
        "summary": summary,
        "providers": providers,
        "models": models,
        "sources": sources,
        "daily": _daily_series(sessions, lookback_days, reference_time, spending_timezone),
        "hourly": _hourly_series(all_recent_calls, reference_time, spending_timezone),
        "recent_sessions": _recent_sessions(sessions, spending_timezone, recent_limit),
        "recent_calls": _recent_calls_payload(recent_calls, spending_timezone),
        "recent_call_limit": call_limit,
    }


def _overview_totals_payload(label: str, totals: GroupTotals) -> dict[str, Any]:
    return {
        "label": label,
        "requests": totals.requests,
        "total_requests": totals.requests,
        "tokens": totals.tokens.as_dict(),
        "total_tokens": totals.tokens.total(),
        "approx_cost": round(totals.cost, 6),
        "model_count": len(totals.models),
        "source_count": len(totals.sources),
    }


def _summary_label(window_name: str) -> str:
    return {
        "today": "Today",
        "this_week": "This week",
        "this_month": "This month",
    }.get(window_name, window_name.replace("_", " ").title())


def _daily_series(
    sessions: list[SessionUsage],
    lookback_days: int,
    reference_time: datetime,
    spending_timezone: timezone | ZoneInfo,
) -> list[dict[str, Any]]:
    day_count = max(1, lookback_days)
    local_today = reference_time.astimezone(spending_timezone).date()
    first_day = local_today - timedelta(days=day_count - 1)
    buckets = {
        (first_day + timedelta(days=offset)).isoformat(): GroupTotals((first_day + timedelta(days=offset)).isoformat())
        for offset in range(day_count)
    }

    for session in sessions:
        if session.timestamp is None:
            continue
        local_date = session.timestamp.astimezone(spending_timezone).date().isoformat()
        if local_date in buckets:
            buckets[local_date].add_row(session)

    return [
        {"date": date, **_overview_totals_payload(date, totals)}
        for date, totals in sorted(buckets.items())
    ]


def _hourly_series(
    calls: list[RecentCall],
    reference_time: datetime,
    spending_timezone: timezone | ZoneInfo,
) -> list[dict[str, Any]]:
    local_now = reference_time.astimezone(spending_timezone)
    current_hour = local_now.replace(minute=0, second=0, microsecond=0)
    first_hour = current_hour - timedelta(hours=23)
    buckets: dict[str, dict[str, Any]] = {
        (first_hour + timedelta(hours=offset)).isoformat(): {
            "requests": 0,
            "total_tokens": 0,
            "approx_cost": 0.0,
        }
        for offset in range(24)
    }

    for call in calls:
        if call.timestamp is None:
            continue
        local_hour = call.timestamp.astimezone(spending_timezone).replace(minute=0, second=0, microsecond=0)
        key = local_hour.isoformat()
        if key in buckets:
            buckets[key]["requests"] += 1
            buckets[key]["total_tokens"] += call.total_tokens
            buckets[key]["approx_cost"] += call.approx_cost

    return [
        {
            "hour": hour,
            "label": hour,
            "requests": values["requests"],
            "total_requests": values["requests"],
            "tokens": {"input_cached": 0, "input_uncached": 0, "output": values["total_tokens"]},
            "total_tokens": values["total_tokens"],
            "approx_cost": round(values["approx_cost"], 6),
            "model_count": 0,
            "source_count": 0,
        }
        for hour, values in sorted(buckets.items())
    ]


def _recent_sessions(
    sessions: list[SessionUsage],
    spending_timezone: timezone | ZoneInfo,
    recent_limit: int,
) -> list[dict[str, Any]]:
    fallback_time = datetime.min.replace(tzinfo=timezone.utc)
    ordered = sorted(
        sessions,
        key=lambda session: session.timestamp or fallback_time,
        reverse=True,
    )
    return [
        {
            "session_id": session.session_id,
            "session_title": session.session_title,
            "client": session.client,
            "occurred_at": session.timestamp.astimezone(spending_timezone).isoformat() if session.timestamp else None,
            "provider": session.provider,
            "model": session.model,
            "source": session.source,
            "requests": session.requests,
            "total_requests": session.requests,
            "tokens": session.tokens.as_dict(),
            "total_tokens": session.tokens.total(),
            "approx_cost": round(session.cost, 6),
        }
        for session in ordered[: max(0, recent_limit)]
    ]


def _recent_calls_payload(
    calls: list[RecentCall],
    spending_timezone: timezone | ZoneInfo,
) -> list[dict[str, Any]]:
    return [
        {
            "id": call.id,
            "session_id": call.session_id,
            "occurred_at": call.timestamp.astimezone(spending_timezone).isoformat() if call.timestamp else None,
            "provider": call.provider,
            "model": call.model,
            "source": call.source,
            "client": call.client,
            "finish_reason": call.finish_reason,
            "tool_call_count": call.tool_call_count,
            "total_tokens": call.total_tokens,
            "approx_cost": round(call.approx_cost, 6),
            "metric_basis": call.metric_basis,
            "session_title": call.session_title,
        }
        for call in calls
    ]


def _provider_payload(
    *,
    name: str,
    totals: GroupTotals,
    status: str,
    credentials: list[dict[str, Any]],
    error: str | None = None,
) -> dict[str, Any]:
    active = 1 if status == "active" else 0
    credential_count = max(1, len(credentials))
    payload: dict[str, Any] = {
        "credential_count": credential_count,
        "active_count": active,
        "exhausted_count": 0,
        "total_requests": totals.requests,
        "tokens": totals.tokens.as_dict(),
        "approx_cost": round(totals.cost, 6),
        "quota_groups": {},
        "credentials": credentials
        or [
            {
                "name": name,
                "status": "disabled" if status == "error" else status,
                "total_requests": 0,
                "tokens": TokenTotals().as_dict(),
                "approx_cost": 0.0,
            }
        ],
    }
    if error:
        payload["status"] = "error"
        payload["error"] = error
    return payload


def _credential_payloads(
    sessions: list[SessionUsage],
    *,
    status: str,
    error: str | None = None,
) -> list[dict[str, Any]]:
    by_credential: dict[tuple[str, str, str], GroupTotals] = {}
    for session in sessions:
        key = (session.provider, session.model or "unknown-model", session.source or "unknown-source")
        display_key = " / ".join(key)
        by_credential.setdefault(key, GroupTotals(display_key)).add_row(session)

    credentials = []
    for provider, model, source in sorted(by_credential):
        totals = by_credential[(provider, model, source)]
        credential: dict[str, Any] = {
            "name": totals.key,
            "provider": provider,
            "model": model,
            "source": source,
            "status": status,
            "total_requests": totals.requests,
            "tokens": totals.tokens.as_dict(),
            "approx_cost": round(totals.cost, 6),
        }
        if error:
            credential["error"] = error
        credentials.append(credential)
    return credentials


def _read_sessions(
    db_path: Path,
    lookback_days: int,
    model_pricing: dict[str, ModelPricing],
    reference_time: datetime,
) -> list[SessionUsage]:
    if not db_path.exists():
        raise FileNotFoundError(f"Hermes state database not found: {db_path}")

    uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "sessions"):
            raise RuntimeError("Hermes state database has no sessions table")

        columns = _table_columns(conn, "sessions")
        select_parts = {
            "billing_provider": _column_expr(columns, "billing_provider", "'hermes'"),
            "billing_base_url": _column_expr(columns, "billing_base_url", "''"),
            "model": _column_expr(columns, "model", "'unknown-model'"),
            "source": _column_expr(columns, "source", "'unknown-source'"),
            "api_call_count": _numeric_expr(columns, "api_call_count"),
            "input_tokens": _numeric_expr(columns, "input_tokens"),
            "cache_read_tokens": _numeric_expr(columns, "cache_read_tokens"),
            "cache_write_tokens": _numeric_expr(columns, "cache_write_tokens"),
            "output_tokens": _numeric_expr(columns, "output_tokens"),
            "reasoning_tokens": _numeric_expr(columns, "reasoning_tokens"),
            "actual_cost_usd": _nullable_numeric_expr(columns, "actual_cost_usd"),
            "estimated_cost_usd": _nullable_numeric_expr(columns, "estimated_cost_usd"),
            "session_timestamp": _session_timestamp_expr(columns),
            "session_id": _column_expr(columns, "id", "''"),
            "session_title": _column_expr(columns, "title", "''"),
            "ended_at": _column_expr(columns, "ended_at", "NULL"),
            "has_ended_at": "1" if "ended_at" in columns else "0",
        }

        where, params = _where_clause(columns, lookback_days, reference_time)
        sql = f"""
            SELECT
                {select_parts["billing_provider"]} AS billing_provider,
                {select_parts["billing_base_url"]} AS billing_base_url,
                {select_parts["model"]} AS model,
                {select_parts["source"]} AS source,
                {select_parts["api_call_count"]} AS api_call_count,
                {select_parts["input_tokens"]} AS input_tokens,
                {select_parts["cache_read_tokens"]} AS cache_read_tokens,
                {select_parts["cache_write_tokens"]} AS cache_write_tokens,
                {select_parts["output_tokens"]} AS output_tokens,
                {select_parts["reasoning_tokens"]} AS reasoning_tokens,
                {select_parts["actual_cost_usd"]} AS actual_cost_usd,
                {select_parts["estimated_cost_usd"]} AS estimated_cost_usd,
                {select_parts["session_timestamp"]} AS session_timestamp,
                {select_parts["session_id"]} AS session_id,
                {select_parts["session_title"]} AS session_title,
                {select_parts["ended_at"]} AS ended_at,
                {select_parts["has_ended_at"]} AS has_ended_at
            FROM sessions
            {where}
        """
        rows = conn.execute(sql, params).fetchall()
        can_split_segments = _table_exists(conn, "messages") and "content" in _table_columns(conn, "messages")
        sessions: list[SessionUsage] = []
        for row in rows:
            session = _row_to_usage(row, model_pricing)
            if can_split_segments:
                sessions.extend(_split_session_by_model_switches(conn, row, session, model_pricing))
            else:
                sessions.append(session)

    return sessions


def _read_recent_calls(
    db_path: Path,
    lookback_days: int,
    reference_time: datetime,
    model_pricing: dict[str, ModelPricing],
    *,
    recent_limit: int,
) -> list[RecentCall]:
    if not db_path.exists():
        return []

    uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "messages") or not _table_exists(conn, "sessions"):
            return []

        session_columns = _table_columns(conn, "sessions")
        message_columns = _table_columns(conn, "messages")
        required_message_columns = {"id", "timestamp", "role", "session_id"}
        if not required_message_columns <= message_columns:
            return []

        lookback_time = reference_time.astimezone(timezone.utc) - timedelta(days=lookback_days)
        params: dict[str, Any] = {
            "lookback_unix": lookback_time.timestamp(),
            "lookback_iso": lookback_time.isoformat(),
            "limit": max(0, recent_limit),
        }
        where_parts = ["m.role = 'assistant'"]
        if lookback_days > 0:
            where_parts.append(
                "(m.timestamp IS NULL OR "
                "(typeof(m.timestamp) IN ('integer', 'real') AND m.timestamp >= :lookback_unix) OR "
                "(typeof(m.timestamp) = 'text' AND m.timestamp >= :lookback_iso))"
            )
        if "active" in message_columns:
            where_parts.append("(m.active IS NULL OR m.active = 1)")
        if "archived" in session_columns:
            where_parts.append("(s.archived IS NULL OR s.archived = 0)")

        sql = f"""
            SELECT
                m.id AS id,
                m.session_id AS session_id,
                m.timestamp AS timestamp,
                {_column_expr(message_columns, "finish_reason", "''")} AS finish_reason,
                {_column_expr(message_columns, "tool_calls", "NULL")} AS tool_calls,
                {_nullable_numeric_expr(message_columns, "token_count")} AS message_token_count,
                {_column_expr(session_columns, "billing_provider", "'hermes'")} AS billing_provider,
                {_column_expr(session_columns, "billing_base_url", "''")} AS billing_base_url,
                {_column_expr(session_columns, "model", "'unknown-model'")} AS model,
                {_column_expr(session_columns, "source", "'unknown-source'")} AS source,
                {_numeric_expr(session_columns, "input_tokens")} AS input_tokens,
                {_numeric_expr(session_columns, "cache_read_tokens")} AS cache_read_tokens,
                {_numeric_expr(session_columns, "cache_write_tokens")} AS cache_write_tokens,
                {_numeric_expr(session_columns, "output_tokens")} AS output_tokens,
                {_numeric_expr(session_columns, "reasoning_tokens")} AS reasoning_tokens,
                {_nullable_numeric_expr(session_columns, "actual_cost_usd")} AS actual_cost_usd,
                {_nullable_numeric_expr(session_columns, "estimated_cost_usd")} AS estimated_cost_usd,
                {_column_expr(session_columns, "title", "''")} AS session_title,
                {_column_expr(session_columns, "ended_at", "NULL")} AS ended_at,
                {"1" if "ended_at" in session_columns else "0"} AS has_ended_at,
                COALESCE(call_counts.assistant_call_count, 1) AS assistant_call_count
            FROM messages m
            JOIN sessions s ON s.id = m.session_id
            LEFT JOIN (
                SELECT session_id, COUNT(*) AS assistant_call_count
                FROM messages
                WHERE role = 'assistant'
                GROUP BY session_id
            ) call_counts ON call_counts.session_id = m.session_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY m.timestamp DESC, m.id DESC
            LIMIT :limit
        """
        rows = conn.execute(sql, params).fetchall()

    return [_row_to_recent_call(row, model_pricing) for row in rows]


def _row_to_recent_call(row: sqlite3.Row, model_pricing: dict[str, ModelPricing]) -> RecentCall:
    raw_provider = str(row["billing_provider"] or "hermes")
    billing_base_url = str(row["billing_base_url"] or "")
    model = str(row["model"] or "unknown-model")
    provider = _provider_for_model(
        raw_provider,
        model,
        model_pricing,
        billing_base_url=billing_base_url,
        is_active_session=_is_active_session_row(row),
    )
    display_model = _model_for_provider(provider, model, model_pricing)
    session_tokens = TokenTotals(
        input_uncached=_int(row["input_tokens"]),
        input_cached=_int(row["cache_read_tokens"]) + _int(row["cache_write_tokens"]),
        output=_int(row["output_tokens"]) + _int(row["reasoning_tokens"]),
    )
    message_token_count = _int(row["message_token_count"])
    assistant_call_count = max(1, _int(row["assistant_call_count"]))
    session_cost = _cost_from_row(raw_provider, provider, display_model, session_tokens, row, model_pricing)
    if message_token_count > 0:
        total_tokens = message_token_count
        metric_basis = "message"
    else:
        total_tokens = round(session_tokens.total() / assistant_call_count)
        metric_basis = "session_avg"
    raw_source = str(row["source"] or "unknown-source")
    return RecentCall(
        id=_int(row["id"]),
        session_id=str(row["session_id"] or ""),
        provider=provider,
        model=display_model,
        source=_normalize_source(raw_source),
        client=_client_from_source(raw_source),
        timestamp=_parse_timestamp(row["timestamp"]),
        finish_reason=str(row["finish_reason"] or "unknown"),
        tool_call_count=_count_tool_calls(row["tool_calls"]),
        total_tokens=total_tokens,
        approx_cost=session_cost / assistant_call_count,
        metric_basis=metric_basis,
        session_title=str(row["session_title"] or ""),
    )



def _limit_recent_calls(calls: list[RecentCall], recent_limit: int) -> list[RecentCall]:
    fallback_time = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(calls, key=lambda call: call.timestamp or fallback_time, reverse=True)[: max(0, recent_limit)]


def _count_tool_calls(value: Any) -> int:
    if not value:
        return 0
    if isinstance(value, (list, tuple)):
        return len(value)
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 1
    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, dict):
        tool_calls = parsed.get("tool_calls")
        if isinstance(tool_calls, list):
            return len(tool_calls)
        return 1
    return 0



def _read_codex_sessions(
    db_path: Path,
    lookback_days: int,
    model_pricing: dict[str, ModelPricing],
    reference_time: datetime,
) -> list[SessionUsage]:
    if not _should_include_local_codex(db_path):
        return []
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return []

    lookback_time = reference_time.astimezone(timezone.utc) - timedelta(days=lookback_days)
    codex_sessions: list[SessionUsage] = []
    for path in sessions_dir.rglob("*.jsonl"):
        usage = _codex_session_usage(path, model_pricing)
        if usage is None:
            continue
        if lookback_days > 0 and usage.timestamp is not None and usage.timestamp < lookback_time:
            continue
        codex_sessions.append(usage)
    return codex_sessions


def _should_include_local_codex(db_path: Path) -> bool:
    default_state_db = Path.home() / ".hermes" / "state.db"
    try:
        return db_path.resolve() == default_state_db.resolve()
    except OSError:
        return db_path.expanduser() == default_state_db



def _read_codex_recent_calls(
    db_path: Path,
    lookback_days: int,
    model_pricing: dict[str, ModelPricing],
    reference_time: datetime,
    *,
    recent_limit: int,
) -> list[RecentCall]:
    if not _should_include_local_codex(db_path):
        return []
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return []

    lookback_time = reference_time.astimezone(timezone.utc) - timedelta(days=lookback_days)
    calls: list[RecentCall] = []
    for path in sessions_dir.rglob("*.jsonl"):
        calls.extend(_codex_recent_calls_from_file(path, model_pricing, lookback_time, lookback_days))
    return _limit_recent_calls(calls, recent_limit)


def _codex_recent_calls_from_file(
    path: Path,
    model_pricing: dict[str, ModelPricing],
    lookback_time: datetime,
    lookback_days: int,
) -> list[RecentCall]:
    model = "unknown-model"
    session_id = path.stem
    calls: list[RecentCall] = []
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return []

    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("type") == "session_meta":
            session_id = str(payload.get("id") or session_id)
            model = str(payload.get("model") or model)
        payload_model = payload.get("model")
        if payload_model:
            model = str(payload_model)
        if event.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        timestamp = _parse_timestamp(event.get("timestamp"))
        if lookback_days > 0 and timestamp is not None and timestamp < lookback_time:
            continue
        usage = payload.get("info", {}).get("last_token_usage") or payload.get("info", {}).get("total_token_usage")
        if not isinstance(usage, dict):
            continue
        input_total = _int(usage.get("input_tokens"))
        input_cached = _int(usage.get("cached_input_tokens"))
        output = _int(usage.get("output_tokens")) + _int(usage.get("reasoning_output_tokens"))
        tokens = TokenTotals(
            input_uncached=max(0, input_total - input_cached),
            input_cached=input_cached,
            output=output,
        )
        calls.append(
            RecentCall(
                id=line_number,
                session_id=session_id,
                provider="openai-api",
                model=model,
                source="codex-cli",
                client="codex",
                timestamp=timestamp,
                finish_reason="token_count",
                tool_call_count=0,
                total_tokens=tokens.total(),
                approx_cost=_calculate_model_cost("openai-api", "codex", model, tokens, model_pricing),
                metric_basis="codex_event",
                session_title=f"Codex {session_id[:8]}",
            )
        )
    return calls


def _codex_session_usage(path: Path, model_pricing: dict[str, ModelPricing]) -> SessionUsage | None:
    model = "unknown-model"
    session_id = path.stem
    timestamp: datetime | None = None
    latest_usage: dict[str, Any] | None = None
    token_event_count = 0

    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return None

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_time = _parse_timestamp(event.get("timestamp"))
        if event_time is not None:
            timestamp = event_time
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("type") == "session_meta":
            session_id = str(payload.get("id") or session_id)
            model = str(payload.get("model") or model)
        payload_model = payload.get("model")
        if payload_model:
            model = str(payload_model)
        if event.get("type") == "event_msg" and payload.get("type") == "token_count":
            total_usage = payload.get("info", {}).get("total_token_usage")
            if isinstance(total_usage, dict):
                latest_usage = total_usage
                token_event_count += 1

    if latest_usage is None:
        return None

    input_total = _int(latest_usage.get("input_tokens"))
    input_cached = _int(latest_usage.get("cached_input_tokens"))
    output = _int(latest_usage.get("output_tokens")) + _int(latest_usage.get("reasoning_output_tokens"))
    tokens = TokenTotals(
        input_uncached=max(0, input_total - input_cached),
        input_cached=input_cached,
        output=output,
    )
    cost = _calculate_model_cost("openai-api", "codex", model, tokens, model_pricing)
    return SessionUsage(
        provider="openai-api",
        model=model,
        source="codex-cli",
        requests=token_event_count,
        tokens=tokens,
        cost=cost,
        timestamp=timestamp,
        session_id=session_id,
        session_title=f"Codex {session_id[:8]}",
        client="codex",
    )


def _row_to_usage(row: sqlite3.Row, model_pricing: dict[str, ModelPricing]) -> SessionUsage:
    raw_provider = str(row["billing_provider"] or "hermes")
    billing_base_url = str(row["billing_base_url"] or "")
    model = str(row["model"] or "unknown-model")
    provider = _provider_for_model(
        raw_provider,
        model,
        model_pricing,
        billing_base_url=billing_base_url,
        is_active_session=_is_active_session_row(row),
    )
    display_model = _model_for_provider(provider, model, model_pricing)
    tokens = TokenTotals(
        input_uncached=_int(row["input_tokens"]),
        input_cached=_int(row["cache_read_tokens"]) + _int(row["cache_write_tokens"]),
        output=_int(row["output_tokens"]) + _int(row["reasoning_tokens"]),
    )
    cost = _cost_from_row(raw_provider, provider, display_model, tokens, row, model_pricing)
    return SessionUsage(
        provider=provider,
        model=display_model,
        source=_normalize_source(str(row["source"] or "unknown-source")),
        requests=_int(row["api_call_count"]),
        tokens=tokens,
        cost=cost,
        timestamp=_parse_timestamp(row["session_timestamp"]),
        session_id=str(row["session_id"] or ""),
        session_title=str(row["session_title"] or ""),
        client="hermes",
    )


def _split_session_by_model_switches(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    session: SessionUsage,
    model_pricing: dict[str, ModelPricing],
) -> list[SessionUsage]:
    if not session.session_id or session.requests <= 0 or session.tokens.total() <= 0:
        return [session]

    messages = conn.execute(
        """
        SELECT role, content, timestamp
        FROM messages
        WHERE session_id = ? AND role IN ('user', 'assistant')
        ORDER BY timestamp ASC, id ASC
        """,
        (session.session_id,),
    ).fetchall()
    switches = [_parse_model_switch(str(message["content"] or "")) for message in messages if message["role"] == "user"]
    switches = [switch for switch in switches if switch is not None]
    if not switches:
        return [session]

    first_switch = switches[0]
    current_model = first_switch["from_model"]
    current_provider = _infer_provider_for_model(current_model, session.provider)
    segments: list[dict[str, Any]] = []

    def segment_for(provider: str, model: str) -> dict[str, Any]:
        if segments and segments[-1]["provider"] == provider and segments[-1]["model"] == model:
            return segments[-1]
        segment = {"provider": provider, "model": model, "assistant_count": 0, "timestamp": None}
        segments.append(segment)
        return segment

    segment_for(current_provider, current_model)
    for message in messages:
        if message["role"] == "user":
            switch = _parse_model_switch(str(message["content"] or ""))
            if switch is not None:
                current_model = switch["to_model"]
                current_provider = _provider_from_switch_note(switch["via"], current_model, current_provider)
                segment_for(current_provider, current_model)
            continue
        segment = segment_for(current_provider, current_model)
        segment["assistant_count"] += 1
        segment["timestamp"] = _parse_timestamp(message["timestamp"]) or segment["timestamp"]

    segments = [segment for segment in segments if segment["assistant_count"] > 0]
    if len(segments) <= 1:
        return [session]

    weights = [int(segment["assistant_count"]) for segment in segments]
    request_parts = _allocate_int(session.requests, weights)
    input_cached_parts = _allocate_int(session.tokens.input_cached, weights)
    input_uncached_parts = _allocate_int(session.tokens.input_uncached, weights)
    output_parts = _allocate_int(session.tokens.output, weights)

    split_sessions: list[SessionUsage] = []
    for index, segment in enumerate(segments):
        provider = str(segment["provider"])
        model = _model_for_provider(provider, str(segment["model"]), model_pricing)
        tokens = TokenTotals(
            input_cached=input_cached_parts[index],
            input_uncached=input_uncached_parts[index],
            output=output_parts[index],
        )
        cost = _calculate_model_cost(provider, provider, model, tokens, model_pricing)
        if cost <= 0 and session.cost > 0:
            cost = session.cost * (weights[index] / max(1, sum(weights)))
        split_sessions.append(
            SessionUsage(
                provider=provider,
                model=model,
                source=session.source,
                requests=request_parts[index],
                tokens=tokens,
                cost=cost,
                timestamp=segment["timestamp"] or session.timestamp,
                session_id=session.session_id,
                session_title=f"{session.session_title} · {model}" if session.session_title else model,
                client=session.client,
            )
        )
    return split_sessions


def _parse_model_switch(content: str) -> dict[str, str] | None:
    match = MODEL_SWITCH_RE.search(content)
    if match is None:
        return None
    return {
        "from_model": _clean_model_name(match.group("from")),
        "to_model": _clean_model_name(match.group("to")),
        "via": match.group("via").strip().lower(),
    }


def _clean_model_name(value: str) -> str:
    return value.strip().strip("`'\" .,:;[]()")


def _provider_from_switch_note(via: str, model: str, fallback: str) -> str:
    normalized = via.strip().lower()
    if "aether" in normalized:
        return "aether"
    if "openai" in normalized:
        return "openai-api"
    return _infer_provider_for_model(model, fallback)


def _infer_provider_for_model(model: str, fallback: str) -> str:
    if _is_known_aether_only_model(model):
        return "aether"
    if _is_known_openai_model(model):
        return "openai-api"
    return fallback


def _allocate_int(total: int, weights: list[int]) -> list[int]:
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return [0 for _ in weights]
    if total >= len(weights):
        base = [1 if weight > 0 else 0 for weight in weights]
        remaining_total = total - sum(base)
        if remaining_total <= 0:
            return base
        remaining = _allocate_int_without_minimum(remaining_total, weights)
        return [base[index] + remaining[index] for index in range(len(weights))]
    return _allocate_int_without_minimum(total, weights)


def _allocate_int_without_minimum(total: int, weights: list[int]) -> list[int]:
    weight_sum = sum(weights)
    raw_parts = [(total * weight) / weight_sum for weight in weights]
    parts = [int(part) for part in raw_parts]
    remainder = total - sum(parts)
    order = sorted(range(len(weights)), key=lambda index: raw_parts[index] - parts[index], reverse=True)
    for index in order[:remainder]:
        parts[index] += 1
    return parts


def _cost_from_row(
    raw_provider: str,
    provider: str,
    model: str,
    tokens: TokenTotals,
    row: sqlite3.Row,
    model_pricing: dict[str, ModelPricing],
) -> float:
    actual_cost = _float(row["actual_cost_usd"])
    estimated_cost = _float(row["estimated_cost_usd"])
    if actual_cost is not None and actual_cost > 0:
        return actual_cost
    if estimated_cost is not None and estimated_cost > 0:
        return estimated_cost
    return _calculate_model_cost(raw_provider, provider, model, tokens, model_pricing)


def _calculate_model_cost(
    raw_provider: str,
    provider: str,
    model: str,
    tokens: TokenTotals,
    model_pricing: dict[str, ModelPricing],
) -> float:
    pricing = (
        model_pricing.get(f"{provider}/{model}")
        or model_pricing.get(f"{raw_provider}/{model}")
        or model_pricing.get(model)
    )
    if pricing is None:
        return 0.0
    return (
        (tokens.input_uncached / 1_000_000) * pricing.input_uncached
        + (tokens.input_cached / 1_000_000) * pricing.input_cached
        + (tokens.output / 1_000_000) * pricing.output
    )


def _normalize_provider(provider: str) -> str:
    return PROVIDER_ALIASES.get(provider, provider)


def _provider_for_model(
    raw_provider: str,
    model: str,
    model_pricing: dict[str, ModelPricing],
    *,
    billing_base_url: str = "",
    is_active_session: bool = False,
) -> str:
    provider = _normalize_provider(raw_provider)
    normalized_base_url = billing_base_url.strip().lower()
    if provider == "openai-api" and "api.openai.com" in normalized_base_url:
        return "openai-api"
    # Hermes sessions can span model/provider switches. The session row may keep
    # an old OpenAI billing provider while its model has changed to a clearly
    # non-OpenAI/Aether-routed model. Keep this intentionally narrow: Aether's
    # catalog also contains OpenAI models like gpt-5.5, and those must not be
    # relabeled just because Aether can proxy them.
    if provider == "openai-api" and _is_known_aether_only_model(model):
        return "aether"
    if provider == "aether" and _is_known_openai_model(model):
        return "openai-api"
    return provider


def _is_known_aether_only_model(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized.startswith(("glm-", "kimi-", "qwen-", "deepseek-", "doubao-"))


def _is_known_openai_model(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized.startswith(("gpt-", "o1", "o3", "o4"))


def _model_for_provider(provider: str, model: str, model_pricing: dict[str, ModelPricing]) -> str:
    if model_pricing.get(f"{provider}/{model}") is not None:
        return model
    if provider == "openai-api" and model_pricing.get("openai-api/gpt-5.5") is not None:
        return "gpt-5.5"
    return model


def _is_active_session_row(row: sqlite3.Row) -> bool:
    return _int(row["has_ended_at"]) == 1 and row["ended_at"] is None


def _normalize_source(source: str) -> str:
    normalized = source.strip() or "unknown-source"
    return {"codex": "codex-cli", "cli": "hermes-cli", "hermes": "hermes-cli"}.get(normalized, normalized)


def _client_from_source(source: str) -> str:
    normalized = source.strip() or "unknown-source"
    if normalized == "codex":
        return "codex"
    return "hermes"


def _where_clause(columns: set[str], lookback_days: int, reference_time: datetime) -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}

    if "archived" in columns:
        clauses.append("(archived IS NULL OR archived = 0)")
    elif "is_archived" in columns:
        clauses.append("(is_archived IS NULL OR is_archived = 0)")

    time_column = next(
        (column for column in ("updated_at", "last_updated", "ended_at", "created_at", "started_at") if column in columns),
        None,
    )
    if time_column and lookback_days > 0:
        lookback_time = reference_time.astimezone(timezone.utc) - timedelta(days=lookback_days)
        params["lookback_unix"] = lookback_time.timestamp()
        params["lookback_iso"] = lookback_time.isoformat()
        clauses.append(
            f"({time_column} IS NULL OR "
            f"(typeof({time_column}) IN ('integer', 'real') AND {time_column} >= :lookback_unix) OR "
            f"(typeof({time_column}) = 'text' AND {time_column} >= :lookback_iso))"
        )

    if not clauses:
        return "", {}
    return "WHERE " + " AND ".join(clauses), params


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _column_expr(columns: set[str], column: str, fallback: str) -> str:
    return column if column in columns else fallback


def _numeric_expr(columns: set[str], column: str) -> str:
    return f"COALESCE({column}, 0)" if column in columns else "0"


def _nullable_numeric_expr(columns: set[str], column: str) -> str:
    return column if column in columns else "NULL"


def _session_timestamp_expr(columns: set[str]) -> str:
    timestamp_columns = [column for column in ("updated_at", "started_at") if column in columns]
    if not timestamp_columns:
        return "NULL"
    if len(timestamp_columns) == 1:
        return timestamp_columns[0]
    return "COALESCE(updated_at, started_at)"


def _int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sessions_in_window(sessions: list[SessionUsage], spending_window: SpendingWindow) -> list[SessionUsage]:
    window_sessions = []
    for session in sessions:
        if session.timestamp is None:
            continue
        timestamp = session.timestamp.astimezone(spending_window.start.tzinfo)
        if spending_window.start <= timestamp < spending_window.end:
            window_sessions.append(session)
    return window_sessions


def _spending_windows(reference_time: datetime, spending_timezone: timezone | ZoneInfo) -> dict[str, SpendingWindow]:
    local_now = reference_time.astimezone(spending_timezone)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    return {
        "today": SpendingWindow(start=today_start, end=today_start + timedelta(days=1)),
        "this_week": SpendingWindow(start=week_start, end=week_start + timedelta(days=7)),
        "this_month": SpendingWindow(start=month_start, end=next_month_start),
    }


def _reference_time(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _load_timezone(timezone_name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name != "Europe/Berlin":
            try:
                return ZoneInfo("Europe/Berlin")
            except ZoneInfoNotFoundError:
                pass
        return timezone.utc


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str):
        return None

    raw_value = value.strip()
    if not raw_value:
        return None
    try:
        timestamp = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp
