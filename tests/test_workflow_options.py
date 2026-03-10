"""Tests for CLI workflow option normalization."""

import pytest

from open_researcher.workflow_options import build_workflow_selection


def test_build_workflow_selection_defaults():
    selection = build_workflow_selection(agent=None)
    assert selection.frontend_mode == "interactive"
    assert selection.use_multi_agent is False
    assert selection.workers is None
    assert selection.idea_agent_name is None
    assert selection.exp_agent_name is None


def test_build_workflow_selection_workers_enable_multi_agent():
    selection = build_workflow_selection(agent="codex", workers=2)
    assert selection.use_multi_agent is True
    assert selection.workers == 2
    assert selection.idea_agent_name == "codex"
    assert selection.exp_agent_name == "codex"


def test_build_workflow_selection_legacy_flags_add_notices():
    selection = build_workflow_selection(agent="codex", headless=True, multi=True)
    assert selection.frontend_mode == "headless"
    assert selection.use_multi_agent is True
    assert len(selection.notices) == 2


def test_build_workflow_selection_rejects_invalid_mode():
    with pytest.raises(ValueError):
        build_workflow_selection(agent=None, mode="batch")


def test_build_workflow_selection_rejects_invalid_workers():
    with pytest.raises(ValueError):
        build_workflow_selection(agent=None, workers=0)
