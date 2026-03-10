"""Tests for headless bootstrap flow."""

import json
import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


def test_headless_scout_phase(tmp_path):
    """Headless mode should run scout agent and emit structured events."""
    _make_git_repo(tmp_path)

    mock_agent = MagicMock()
    mock_agent.name = "mock-agent"
    mock_agent.run.return_value = 0
    mock_agent.terminate = MagicMock()

    buf = StringIO()

    with patch("open_researcher.headless._resolve_agent", return_value=mock_agent):
        from open_researcher.headless import do_start_headless

        do_start_headless(
            repo_path=tmp_path,
            goal="test goal",
            max_experiments=0,
            agent_name=None,
            tag="test",
            multi=False,
            stream=buf,
        )

    output = buf.getvalue()
    lines = [json.loads(line) for line in output.strip().splitlines() if line.strip()]
    events = [r["event"] for r in lines]
    assert "session_started" in events
    assert "scout_started" in events


def test_headless_max_experiments_limit(tmp_path):
    """Headless mode should stop after max_experiments."""
    _make_git_repo(tmp_path)

    mock_agent = MagicMock()
    mock_agent.name = "mock-agent"

    def fake_run(workdir, on_output=None, program_file="program.md", env=None):
        if on_output:
            on_output("[exp] done")
        return 0

    mock_agent.run.side_effect = fake_run
    mock_agent.terminate = MagicMock()

    buf = StringIO()

    with patch("open_researcher.headless._resolve_agent", return_value=mock_agent), \
         patch("open_researcher.headless._has_pending_ideas", return_value=True):
        from open_researcher.headless import do_start_headless

        do_start_headless(
            repo_path=tmp_path,
            goal="test",
            max_experiments=3,
            agent_name=None,
            tag="test",
            multi=True,
            stream=buf,
        )

    output = buf.getvalue()
    lines = [json.loads(line) for line in output.strip().splitlines() if line.strip()]
    events = [r["event"] for r in lines]
    assert "limit_reached" in events


def test_headless_single_agent(tmp_path):
    """Single-agent headless should run program.md and emit events."""
    _make_git_repo(tmp_path)

    mock_agent = MagicMock()
    mock_agent.name = "mock-agent"
    mock_agent.run.return_value = 0
    mock_agent.terminate = MagicMock()

    buf = StringIO()

    with patch("open_researcher.headless._resolve_agent", return_value=mock_agent):
        from open_researcher.headless import do_start_headless

        do_start_headless(
            repo_path=tmp_path,
            goal="test single agent",
            max_experiments=0,
            agent_name=None,
            tag="test",
            multi=False,
            stream=buf,
        )

    output = buf.getvalue()
    lines = [json.loads(line) for line in output.strip().splitlines() if line.strip()]
    events = [r["event"] for r in lines]
    assert "session_started" in events
    assert "scout_started" in events
    assert "scout_completed" in events
    assert "session_completed" in events


def test_headless_scout_failure_stops(tmp_path):
    """If scout fails, headless should stop and emit scout_failed."""
    _make_git_repo(tmp_path)

    mock_agent = MagicMock()
    mock_agent.name = "mock-agent"
    mock_agent.run.return_value = 1  # Scout fails
    mock_agent.terminate = MagicMock()

    buf = StringIO()

    with patch("open_researcher.headless._resolve_agent", return_value=mock_agent):
        from open_researcher.headless import do_start_headless

        do_start_headless(
            repo_path=tmp_path,
            goal="test failure",
            max_experiments=0,
            agent_name=None,
            tag="test",
            multi=False,
            stream=buf,
        )

    output = buf.getvalue()
    lines = [json.loads(line) for line in output.strip().splitlines() if line.strip()]
    events = [r["event"] for r in lines]
    assert "scout_failed" in events
    assert "session_completed" not in events
