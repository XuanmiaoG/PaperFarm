"""Tests for Textual TUI components."""

from open_researcher.tui.widgets import AgentStatusWidget, StatsBar


def test_stats_bar_update():
    bar = StatsBar()
    state = {"total": 7, "keep": 3, "discard": 2, "crash": 1, "best_value": 1.47, "primary_metric": "val_loss"}
    bar.update_stats(state)
    assert "7 exp" in bar.stats
    assert "3 kept" in bar.stats
    assert "1.47" in bar.stats


def test_stats_bar_empty():
    bar = StatsBar()
    bar.update_stats({"total": 0})
    assert "waiting" in bar.stats


def test_idea_pool_table_exists():
    from open_researcher.tui.widgets import IdeaPoolTable

    panel = IdeaPoolTable()
    assert panel is not None


def test_agent_status_widget_update():
    widget = AgentStatusWidget()
    activity = {
        "status": "analyzing",
        "detail": "reading codebase",
        "updated_at": "2026-03-09T12:00:00",
    }
    widget.update_status(activity)
    assert "ANALYZING" in widget.status_text
    assert "reading codebase" in widget.status_text


def test_agent_status_widget_none():
    widget = AgentStatusWidget()
    widget.update_status(None)
    assert "IDLE" in widget.status_text


def test_agent_status_widget_with_idea():
    widget = AgentStatusWidget()
    activity = {
        "status": "generating",
        "detail": "creating new hypothesis",
        "idea": "cosine-lr-schedule",
        "updated_at": "2026-03-09T14:30:00",
    }
    widget.update_status(activity)
    assert "GENERATING" in widget.status_text
    assert "cosine-lr-schedule" in widget.status_text
    assert "2026-03-09T14:30:00" in widget.status_text
