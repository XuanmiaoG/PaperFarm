# Headless Mode + Max Experiments Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--headless` mode to `start` command with JSON Lines structured logging and `--max-experiments` limit.

**Architecture:** Extend `start` command with three new CLI flags. When `--headless` is set, bypass TUI entirely and run Scout → Experiment loop synchronously with structured JSON Lines output to stdout. `max_experiments` is tracked as a counter in the dual-agent loop.

**Tech Stack:** Python 3.10+, Typer CLI, JSON Lines logging

---

### Task 1: Add `max_experiments` to ResearchConfig

**Files:**
- Modify: `src/open_researcher/config.py:10-21`
- Modify: `tests/test_config.py`

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_load_config_max_experiments(research_dir):
    """max_experiments should be parsed from config."""
    config_data = {
        "experiment": {
            "max_experiments": 20,
        },
    }
    config_path = research_dir / "config.yaml"
    config_path.write_text(yaml.dump(config_data))
    cfg = load_config(research_dir)
    assert cfg.max_experiments == 20


def test_load_config_max_experiments_default(research_dir):
    """max_experiments defaults to 0 (unlimited)."""
    config_path = research_dir / "config.yaml"
    config_path.write_text(yaml.dump({"mode": "autonomous"}))
    cfg = load_config(research_dir)
    assert cfg.max_experiments == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_config.py::test_load_config_max_experiments tests/test_config.py::test_load_config_max_experiments_default -v`
Expected: FAIL — `ResearchConfig` has no `max_experiments` attribute

**Step 3: Write minimal implementation**

In `src/open_researcher/config.py`, add `max_experiments` field to dataclass and parsing:

```python
@dataclass
class ResearchConfig:
    mode: str = "autonomous"
    timeout: int = 600
    max_crashes: int = 3
    max_experiments: int = 0      # <-- NEW: 0 = unlimited
    max_workers: int = 0
    worker_agent: str = ""
    # ... rest unchanged
```

In `load_config()`, add parsing:

```python
    return ResearchConfig(
        # ... existing fields ...
        max_experiments=exp.get("max_experiments", 0),
        # ... rest unchanged
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/open_researcher/config.py tests/test_config.py
git commit -m "feat: add max_experiments to ResearchConfig"
```

---

### Task 2: Update config.yaml template

**Files:**
- Modify: `src/open_researcher/templates/config.yaml.j2:10-14`

**Step 1: Add max_experiments to template**

In `src/open_researcher/templates/config.yaml.j2`, under the `experiment:` section, add:

```yaml
experiment:
  timeout: 600                  # seconds per experiment before kill
  max_consecutive_crashes: 3    # pause after N consecutive crashes
  max_experiments: 0            # 0 = unlimited; set to N to stop after N experiments
  max_parallel_workers: 0       # 0 = auto (one per available GPU), 1 = serial
  worker_agent: ""              # agent for sub-workers (default: same as master)
```

**Step 2: Verify template renders**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -c "from jinja2 import Environment, PackageLoader; env = Environment(loader=PackageLoader('open_researcher', 'templates')); t = env.get_template('config.yaml.j2'); print(t.render(tag='test')); assert 'max_experiments' in t.render(tag='test')"`
Expected: Output includes `max_experiments: 0`

**Step 3: Commit**

```bash
git add src/open_researcher/templates/config.yaml.j2
git commit -m "feat: add max_experiments to config template"
```

---

### Task 3: Create HeadlessLogger

**Files:**
- Create: `src/open_researcher/headless.py`
- Create: `tests/test_headless.py`

**Step 1: Write the failing tests**

Create `tests/test_headless.py`:

```python
"""Tests for headless mode logger."""

import json
from io import StringIO
from pathlib import Path

from open_researcher.headless import HeadlessLogger


def test_emit_writes_jsonl_to_stream():
    """emit() should write a single JSON line to the stream."""
    buf = StringIO()
    logger = HeadlessLogger(stream=buf)
    logger.emit("info", "scouting", "scout_started", detail="analyzing")
    line = buf.getvalue().strip()
    record = json.loads(line)
    assert record["level"] == "info"
    assert record["phase"] == "scouting"
    assert record["event"] == "scout_started"
    assert record["detail"] == "analyzing"
    assert "ts" in record


def test_emit_writes_to_log_file(tmp_path):
    """emit() should also write to log file when provided."""
    log_path = tmp_path / "events.jsonl"
    buf = StringIO()
    logger = HeadlessLogger(stream=buf, log_path=log_path)
    logger.emit("info", "experimenting", "experiment_started", idea="idea-001")
    logger.close()
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "experiment_started"
    assert record["idea"] == "idea-001"


def test_emit_extra_kwargs():
    """Extra keyword arguments appear in the JSON record."""
    buf = StringIO()
    logger = HeadlessLogger(stream=buf)
    logger.emit("info", "experimenting", "experiment_completed",
                idea="idea-002", metric_value=0.95, experiment_num=3, max_experiments=10)
    record = json.loads(buf.getvalue().strip())
    assert record["metric_value"] == 0.95
    assert record["experiment_num"] == 3
    assert record["max_experiments"] == 10


def test_make_output_callback():
    """make_output_callback returns a callable that emits agent_output events."""
    buf = StringIO()
    logger = HeadlessLogger(stream=buf)
    cb = logger.make_output_callback("experimenting")
    cb("[exp] Running experiment #1")
    record = json.loads(buf.getvalue().strip())
    assert record["event"] == "agent_output"
    assert record["detail"] == "[exp] Running experiment #1"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_headless.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'open_researcher.headless'`

**Step 3: Write minimal implementation**

Create `src/open_researcher/headless.py`:

```python
"""Headless mode — structured JSON Lines logging for CLI-only operation."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class HeadlessLogger:
    """Emit structured JSON Lines events to a stream and optional log file."""

    def __init__(self, stream=None, log_path: Path | None = None):
        self._stream = stream or sys.stdout
        self._log_file = open(log_path, "a") if log_path else None  # noqa: SIM115

    def emit(self, level: str, phase: str, event: str, **kwargs) -> None:
        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": level,
            "phase": phase,
            "event": event,
            **kwargs,
        }
        line = json.dumps(record, ensure_ascii=False)
        self._stream.write(line + "\n")
        self._stream.flush()
        if self._log_file:
            self._log_file.write(line + "\n")
            self._log_file.flush()

    def make_output_callback(self, phase: str):
        """Return a callback compatible with agent.run(on_output=...)."""
        def on_output(line: str):
            self.emit("info", phase, "agent_output", detail=line)
        return on_output

    def close(self):
        if self._log_file:
            self._log_file.close()
            self._log_file = None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_headless.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/open_researcher/headless.py tests/test_headless.py
git commit -m "feat: add HeadlessLogger with JSON Lines output"
```

---

### Task 4: Add do_start_headless() flow

**Files:**
- Modify: `src/open_researcher/headless.py`
- Create: `tests/test_headless_flow.py`

**Step 1: Write the failing test**

Create `tests/test_headless_flow.py`:

```python
"""Tests for headless start flow."""

import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import json


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
    lines = [json.loads(l) for l in output.strip().splitlines() if l.strip()]
    events = [r["event"] for r in lines]
    assert "session_started" in events
    assert "scout_started" in events


def test_headless_max_experiments_limit(tmp_path):
    """Headless mode should stop after max_experiments."""
    _make_git_repo(tmp_path)

    call_count = 0
    mock_agent = MagicMock()
    mock_agent.name = "mock-agent"

    def fake_run(workdir, on_output=None, program_file="program.md", env=None):
        nonlocal call_count
        call_count += 1
        # Simulate agent producing an idea then running experiment
        if on_output:
            on_output("[exp] done")
        return 0

    mock_agent.run.side_effect = fake_run
    mock_agent.terminate = MagicMock()

    buf = StringIO()

    # Patch idea pool to always have pending ideas (so loop doesn't stop early)
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
    lines = [json.loads(l) for l in output.strip().splitlines() if l.strip()]
    events = [r["event"] for r in lines]
    assert "limit_reached" in events
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_headless_flow.py -v`
Expected: FAIL — `do_start_headless` not found

**Step 3: Write implementation**

Add `do_start_headless()` to `src/open_researcher/headless.py`:

```python
"""Headless mode — structured JSON Lines logging for CLI-only operation."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from open_researcher.config import load_config
from open_researcher.run_cmd import _has_pending_ideas, _read_latest_status, _resolve_agent, _set_paused


class HeadlessLogger:
    """Emit structured JSON Lines events to a stream and optional log file."""

    def __init__(self, stream=None, log_path: Path | None = None):
        self._stream = stream or sys.stdout
        self._log_file = open(log_path, "a") if log_path else None  # noqa: SIM115

    def emit(self, level: str, phase: str, event: str, **kwargs) -> None:
        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": level,
            "phase": phase,
            "event": event,
            **kwargs,
        }
        line = json.dumps(record, ensure_ascii=False)
        self._stream.write(line + "\n")
        self._stream.flush()
        if self._log_file:
            self._log_file.write(line + "\n")
            self._log_file.flush()

    def make_output_callback(self, phase: str):
        """Return a callback compatible with agent.run(on_output=...)."""
        def on_output(line: str):
            self.emit("info", phase, "agent_output", detail=line)
        return on_output

    def close(self):
        if self._log_file:
            self._log_file.close()
            self._log_file = None


def do_start_headless(
    repo_path: Path,
    goal: str,
    max_experiments: int = 0,
    agent_name: str | None = None,
    tag: str | None = None,
    multi: bool = False,
    idea_agent_name: str | None = None,
    exp_agent_name: str | None = None,
    stream=None,
) -> None:
    """Run the full start flow without TUI — structured JSON Lines to stdout."""
    from datetime import date

    from open_researcher.crash_counter import CrashCounter
    from open_researcher.phase_gate import PhaseGate
    from open_researcher.start_cmd import do_start_init, render_scout_program
    from open_researcher.watchdog import TimeoutWatchdog

    if tag is None:
        tag = date.today().strftime("%b%d").lower()

    # Phase 0: Bootstrap
    research = do_start_init(repo_path, tag=tag)
    cfg = load_config(research)

    # Override max_experiments: CLI flag > config > default
    if max_experiments > 0:
        cfg.max_experiments = max_experiments
    effective_max = cfg.max_experiments

    logger = HeadlessLogger(stream=stream, log_path=research / "events.jsonl")
    logger.emit("info", "init", "session_started",
                goal=goal, max_experiments=effective_max, repo=str(repo_path))

    # Resolve agents
    scout_agent = _resolve_agent(agent_name, cfg.agent_config)
    if multi or idea_agent_name or exp_agent_name:
        idea_agent = _resolve_agent(idea_agent_name or agent_name, cfg.agent_config)
        exp_agent = _resolve_agent(exp_agent_name or agent_name, cfg.agent_config)
    else:
        idea_agent = None
        exp_agent = None

    try:
        # Phase 1: Goal
        render_scout_program(research, tag=tag, goal=goal)
        (research / "goal.md").write_text(f"# Research Goal\n\n{goal}\n")

        # Phase 2: Scout
        logger.emit("info", "scouting", "scout_started")
        scout_output = logger.make_output_callback("scouting")
        code = scout_agent.run(repo_path, on_output=scout_output, program_file="scout_program.md")
        logger.emit("info", "scouting", "scout_completed", exit_code=code)

        if code != 0:
            logger.emit("error", "scouting", "scout_failed", exit_code=code)
            return

        # Phase 3: Auto-confirm (no review in headless)
        logger.emit("info", "reviewing", "auto_confirmed")

        # Phase 4: Experiments
        if multi and idea_agent and exp_agent:
            _run_dual_agent_headless(
                repo_path, research, cfg, idea_agent, exp_agent, logger, effective_max,
            )
        else:
            _run_single_agent_headless(
                repo_path, research, cfg, scout_agent, logger, effective_max,
            )

        logger.emit("info", "done", "session_completed")
    finally:
        scout_agent.terminate()
        if idea_agent:
            idea_agent.terminate()
        if exp_agent:
            exp_agent.terminate()
        logger.close()


def _run_single_agent_headless(repo_path, research, cfg, agent, logger, max_experiments):
    """Single-agent headless: run program.md."""
    from open_researcher.watchdog import TimeoutWatchdog

    watchdog = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: agent.terminate())
    watchdog.start()

    logger.emit("info", "experimenting", "experiment_started", experiment_num=1, max_experiments=max_experiments)
    output_cb = logger.make_output_callback("experimenting")
    code = agent.run(repo_path, on_output=output_cb, program_file="program.md")
    watchdog.stop()
    logger.emit("info", "experimenting", "experiment_completed", exit_code=code, experiment_num=1)


def _run_dual_agent_headless(repo_path, research, cfg, idea_agent, exp_agent, logger, max_experiments):
    """Dual-agent headless: alternate idea + experiment agents with max_experiments limit."""
    from open_researcher.crash_counter import CrashCounter
    from open_researcher.phase_gate import PhaseGate
    from open_researcher.watchdog import TimeoutWatchdog

    crash_counter = CrashCounter(cfg.max_crashes)
    phase_gate = PhaseGate(research, cfg.mode)
    watchdog = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: exp_agent.terminate())

    experiments_completed = 0
    cycle = 0

    while True:
        cycle += 1
        logger.emit("info", "experimenting", "idea_cycle_started", cycle=cycle)

        # Idea Agent
        idea_output = logger.make_output_callback("experimenting")
        code = idea_agent.run(repo_path, on_output=idea_output, program_file="idea_program.md")
        logger.emit("info", "experimenting", "idea_agent_done", cycle=cycle, exit_code=code)

        if not _has_pending_ideas(research):
            logger.emit("info", "done", "no_pending_ideas")
            break

        # Experiment Agent loop
        while True:
            experiments_completed += 1
            logger.emit("info", "experimenting", "experiment_started",
                        experiment_num=experiments_completed, max_experiments=max_experiments)

            watchdog.reset()
            exp_output = logger.make_output_callback("experimenting")
            code = exp_agent.run(repo_path, on_output=exp_output, program_file="experiment_program.md")
            watchdog.stop()

            logger.emit("info", "experimenting", "experiment_completed",
                        experiment_num=experiments_completed, exit_code=code)

            # Check max_experiments limit
            if max_experiments > 0 and experiments_completed >= max_experiments:
                logger.emit("info", "done", "limit_reached",
                            detail=f"Max experiments ({max_experiments}) reached")
                return

            # Crash counter
            status = _read_latest_status(research)
            if status and crash_counter.record(status):
                logger.emit("error", "experimenting", "crash_limit",
                            detail=f"Crash limit ({cfg.max_crashes}) reached")
                _set_paused(research, f"Crash limit: {cfg.max_crashes}")
                return

            # Phase gate
            phase = phase_gate.check()
            if phase:
                logger.emit("info", "experimenting", "phase_transition", phase=phase)
                _set_paused(research, f"Phase: {phase}")
                return

            if not _has_pending_ideas(research):
                break

    logger.emit("info", "done", "all_ideas_processed")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_headless_flow.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/open_researcher/headless.py tests/test_headless_flow.py
git commit -m "feat: add do_start_headless() flow with max_experiments"
```

---

### Task 5: Wire CLI flags into start command

**Files:**
- Modify: `src/open_researcher/cli.py:105-123`
- Modify: `src/open_researcher/start_cmd.py:42-49`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_start_headless_requires_goal():
    """start --headless without --goal should fail."""
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        result = runner.invoke(app, ["start", "--headless"])
        assert result.exit_code != 0
        assert "goal" in result.stdout.lower() or "goal" in str(result.exception).lower()


def test_start_headless_help():
    """start --help should show --headless and --max-experiments flags."""
    result = runner.invoke(app, ["start", "--help"])
    assert result.exit_code == 0
    assert "--headless" in result.stdout
    assert "--max-experiments" in result.stdout
    assert "--goal" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_cli.py::test_start_headless_requires_goal tests/test_cli.py::test_start_headless_help -v`
Expected: FAIL — `--headless` not recognized

**Step 3: Write implementation**

Modify `src/open_researcher/cli.py` — update the `start` command:

```python
@app.command()
def start(
    agent: str = typer.Option(None, help="Agent to use (claude-code, codex, aider, opencode)."),
    tag: str = typer.Option(None, help="Experiment tag (e.g. mar10). Defaults to today's date."),
    multi: bool = typer.Option(False, "--multi", help="Enable dual-agent mode (Idea + Experiment)."),
    idea_agent: str = typer.Option(None, "--idea-agent", help="Agent for idea generation (multi mode)."),
    exp_agent: str = typer.Option(None, "--exp-agent", help="Agent for experiments (multi mode)."),
    headless: bool = typer.Option(False, "--headless", help="Run without TUI, output JSON Lines to stdout."),
    goal: str = typer.Option(None, "--goal", help="Research goal (required for --headless)."),
    max_experiments: int = typer.Option(0, "--max-experiments", help="Stop after N experiments (0 = unlimited)."),
):
    """Zero-config start: auto-init, analyze repo, confirm plan, then run experiments."""
    if headless:
        if not goal:
            console.print("[red]Error:[/red] --goal is required when using --headless.")
            raise typer.Exit(code=1)
        from open_researcher.headless import do_start_headless

        do_start_headless(
            repo_path=Path.cwd(),
            goal=goal,
            max_experiments=max_experiments,
            agent_name=agent,
            tag=tag,
            multi=multi,
            idea_agent_name=idea_agent,
            exp_agent_name=exp_agent,
        )
    else:
        from open_researcher.start_cmd import do_start

        do_start(
            repo_path=Path.cwd(),
            agent_name=agent,
            tag=tag,
            multi=multi,
            idea_agent_name=idea_agent,
            exp_agent_name=exp_agent,
        )
```

Also add `console = Console()` import at the top of cli.py (after existing imports):

```python
from rich.console import Console
console = Console()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/open_researcher/cli.py tests/test_cli.py
git commit -m "feat: wire --headless, --goal, --max-experiments into start command"
```

---

### Task 6: Add max_experiments to TUI dual-agent loop

**Files:**
- Modify: `src/open_researcher/start_cmd.py:149-203`
- Modify: `src/open_researcher/run_cmd.py:415-478`

**Step 1: Pass max_experiments through do_start**

In `src/open_researcher/start_cmd.py`, update `do_start()` signature to accept `max_experiments`:

In the `_alternating()` function inside `_start_experiment_agents()`, add counter logic:

```python
def _alternating():
    cycle = 0
    experiments_completed = 0
    effective_max = cfg.max_experiments
    while not stop.is_set():
        cycle += 1
        # ... idea agent code unchanged ...

        exp_run = 0
        while not stop.is_set():
            exp_run += 1
            experiments_completed += 1
            # ... experiment agent code unchanged ...

            # Check max_experiments limit (after existing crash/phase checks)
            if effective_max > 0 and experiments_completed >= effective_max:
                on_output(f"[system] Max experiments ({effective_max}) reached. Stopping.")
                stop.set()
                break

            # ... rest unchanged ...
```

Do the same in `src/open_researcher/run_cmd.py` `_alternating()` (lines 415-478).

**Step 2: Verify existing tests still pass**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/ -v --timeout=30`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add src/open_researcher/start_cmd.py src/open_researcher/run_cmd.py
git commit -m "feat: enforce max_experiments limit in dual-agent loops"
```

---

### Task 7: Integration test — full headless flow

**Files:**
- Modify: `tests/test_headless_flow.py`

**Step 1: Write integration test**

Add to `tests/test_headless_flow.py`:

```python
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
    lines = [json.loads(l) for l in output.strip().splitlines() if l.strip()]
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
    lines = [json.loads(l) for l in output.strip().splitlines() if l.strip()]
    events = [r["event"] for r in lines]
    assert "scout_failed" in events
    assert "session_completed" not in events
```

**Step 2: Run all tests**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_headless.py tests/test_headless_flow.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_headless_flow.py
git commit -m "test: add integration tests for headless flow"
```

---

### Task 8: Final verification — run full test suite

**Step 1: Run all tests**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/ -v --timeout=30`
Expected: ALL PASS

**Step 2: Manual smoke test**

Run: `cd /Users/shatianming/Downloads/open-researcher && open-researcher start --help`
Expected: Shows `--headless`, `--goal`, `--max-experiments` in help output

**Step 3: Final commit with design doc**

```bash
git add docs/plans/
git commit -m "docs: add headless mode design and implementation plan"
```
