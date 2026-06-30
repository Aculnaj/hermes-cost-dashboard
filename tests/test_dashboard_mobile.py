from __future__ import annotations

from hermes_codexbar_cost_api.dashboard import DASHBOARD_HTML


def test_dashboard_contains_mobile_responsive_css() -> None:
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in DASHBOARD_HTML
    assert "@media (max-width: 720px)" in DASHBOARD_HTML
    assert "@media (max-width: 340px)" in DASHBOARD_HTML
    assert "env(safe-area-inset-top)" in DASHBOARD_HTML
    assert "min-height: 100svh" in DASHBOARD_HTML
    assert "min-height: 40px" in DASHBOARD_HTML


def test_dashboard_uses_mobile_table_and_chart_classes() -> None:
    assert 'id="dailyChart" class="chart-wrap"' in DASHBOARD_HTML
    assert 'id="sessions" class="table-scroll"' in DASHBOARD_HTML
    assert 'id="providers" class="table-scroll"' in DASHBOARD_HTML
    assert 'id="models" class="table-scroll"' in DASHBOARD_HTML
    assert "position: sticky" in DASHBOARD_HTML
    assert "-webkit-overflow-scrolling: touch" in DASHBOARD_HTML


def test_dashboard_can_copy_session_from_recent_tables() -> None:
    assert "session-copy" in DASHBOARD_HTML
    assert "copySessionText" in DASHBOARD_HTML
    assert "navigator.clipboard.writeText" in DASHBOARD_HTML


def test_dashboard_has_compact_mobile_activity_layout() -> None:
    assert "@media (max-width: 480px)" in DASHBOARD_HTML
    assert ".activity-panel .tabs" in DASHBOARD_HTML
    assert "flex: 1 1 0" in DASHBOARD_HTML
    assert "touch-action: pan-x" in DASHBOARD_HTML
    assert ".calls-table { min-width: 780px; }" in DASHBOARD_HTML
    assert ".sessions-table { min-width: 760px; }" in DASHBOARD_HTML
