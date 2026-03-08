# Open Researcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI tool that initializes research workflows in any repo, providing templates for AI agents, git experiment management scripts, CLI status, and a web dashboard.

**Architecture:** Typer CLI with Jinja2 templates for `.research/` scaffolding, a TSV-based experiment log with git helper scripts, and a FastAPI dashboard for visualization. No LLM API calls — all intelligence comes from the external agent (opencode).

**Tech Stack:** Python 3.10+, Typer, Jinja2, FastAPI, Chart.js, PyYAML, Rich (terminal formatting), uv (packaging)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/open_researcher/__init__.py`
- Create: `src/open_researcher/cli.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "open-researcher"
version = "0.1.0"
description = "Research workflow framework for AI agents — initialize, track, and visualize automated experiments in any repo"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    "jinja2>=3.1.0",
    "pyyaml>=6.0",
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
]

[project.scripts]
open-researcher = "open_researcher.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 2: Create package __init__.py**

```python
"""Open Researcher — research workflow framework for AI agents."""

__version__ = "0.1.0"
```

**Step 3: Create minimal CLI entry point**

```python
# src/open_researcher/cli.py
import typer

app = typer.Typer(
    name="open-researcher",
    help="Research workflow framework for AI agents",
)


@app.command()
def init(tag: str = typer.Option(None, help="Experiment tag (e.g. mar8). Defaults to today's date.")):
    """Initialize .research/ directory in the current repo."""
    typer.echo(f"init called with tag={tag}")


@app.command()
def status():
    """Show current research progress."""
    typer.echo("status called")


@app.command()
def results():
    """Print experiment results table."""
    typer.echo("results called")


@app.command()
def dashboard(port: int = typer.Option(8384, help="Dashboard port")):
    """Launch web dashboard."""
    typer.echo(f"dashboard called on port {port}")


@app.command()
def export():
    """Export experiment report as Markdown."""
    typer.echo("export called")


if __name__ == "__main__":
    app()
```

**Step 4: Install in dev mode and verify CLI works**

Run: `uv pip install -e .`
Then: `open-researcher --help`
Expected: Help text showing init, status, results, dashboard, export commands

**Step 5: Commit**

```bash
git add pyproject.toml src/
git commit -m "feat: project scaffolding with Typer CLI skeleton"
```

---

### Task 2: Template Files

Create the Jinja2 templates that `init` will render into `.research/`.

**Files:**
- Create: `src/open_researcher/templates/program.md.j2`
- Create: `src/open_researcher/templates/config.yaml.j2`
- Create: `src/open_researcher/templates/project-understanding.md.j2`
- Create: `src/open_researcher/templates/evaluation.md.j2`

**Step 1: Create program.md.j2**

This is the core "operating system" for the agent. It must be self-contained — an agent reading only this file should know exactly what to do.

```markdown
# Research Program

> This file guides your AI agent through an automated research workflow.
> Read it completely before starting. Follow each phase in order.

## Configuration

- **Mode:** Read `.research/config.yaml` → `mode` field
  - `autonomous`: proceed without human confirmation after each phase
  - `collaborative`: pause and ask human to confirm before advancing
- **Environment:** Read `.research/config.yaml` → `environment` field for execution instructions
- **Tag:** `{{ tag }}`
- **Branch:** `research/{{ tag }}`

---

## Phase 1: Understand the Project

**Goal:** Build a comprehensive understanding of this repository.

**Instructions:**
1. Read ALL source files, documentation, configs, and tests in this repo
2. Identify:
   - The project's purpose and core functionality
   - Code structure and key modules/classes/functions
   - Existing tests and evaluation mechanisms
   - Dependencies and environment requirements
   - Entry points (CLI commands, scripts, HTTP endpoints)
3. Write your analysis to `.research/project-understanding.md` following the template there
4. If `mode: collaborative` → stop and ask the human to review before continuing

---

## Phase 2: Design Evaluation

**Goal:** Create a measurable evaluation system for experiments.

**Instructions:**
1. Based on your project understanding, design an evaluation system:
   - **Primary metric**: one number that determines keep/discard (e.g. accuracy, loss, test_pass_rate, latency_ms)
   - **Secondary metrics**: additional numbers for context (optional)
   - **Evaluation method**: exact commands to run and how to extract the metric from output
   - **Baseline method**: how to establish the initial baseline measurement
2. Write the evaluation design to `.research/evaluation.md` following the template there
3. Update `.research/config.yaml`:
   - Set `metrics.primary.name` to your chosen metric name
   - Set `metrics.primary.direction` to `higher_is_better` or `lower_is_better`
4. If `mode: collaborative` → stop and ask the human to review before continuing

---

## Phase 3: Establish Baseline

**Instructions:**
1. Create the experiment branch:
   ```bash
   git checkout -b research/{{ tag }}
   ```
2. Run the evaluation method from `.research/evaluation.md` to get baseline metrics
3. Record the baseline:
   ```bash
   python .research/scripts/record.py \
       --metric <primary_metric_name> \
       --value <measured_value> \
       --secondary '{}' \
       --status keep \
       --desc "baseline"
   ```
4. Commit:
   ```bash
   git add .research/
   git commit -m "research: establish baseline"
   ```

---

## Phase 4: Experiment Loop

**LOOP FOREVER:**

1. **Review state**: Check `git status` and read `.research/results.tsv` to see past experiments
2. **Propose experiment**: Think of an improvement to try. Consider:
   - What has worked/failed in past experiments (results.tsv)
   - Ideas from the codebase, papers, or domain knowledge
   - Both incremental tweaks and bold architectural changes
3. **Implement**: Make code changes
4. **Commit**: `git add -A && git commit -m "exp: <brief description>"`
5. **Run experiment**: Execute the evaluation command from `.research/evaluation.md`, redirect output:
   ```bash
   <evaluation_command> > .research/run.log 2>&1
   ```
6. **Extract results**: Parse `.research/run.log` for the primary metric
7. **Handle crash**: If the experiment crashed (no metric output):
   - Read last 50 lines of `.research/run.log` for the error
   - Try to fix (up to 2 attempts)
   - If unfixable, record as crash and rollback:
     ```bash
     python .research/scripts/record.py --metric <name> --value 0 --status crash --desc "<what failed>"
     bash .research/scripts/rollback.sh
     ```
8. **Record result**:
   ```bash
   python .research/scripts/record.py \
       --metric <name> --value <value> \
       --secondary '<json>' \
       --status <keep|discard> \
       --desc "<what you tried>"
   ```
9. **Keep or discard**:
   - **Improved** (better primary metric) → keep the commit, continue
   - **Not improved** → rollback:
     ```bash
     bash .research/scripts/rollback.sh
     ```
10. **Continue**: Go to step 1. NEVER STOP unless the human interrupts.

### Experiment Timeout

If a single experiment takes longer than the `experiment.timeout` value in config.yaml (default: 600 seconds), kill it and treat as a crash.

### Consecutive Crash Limit

If experiments crash `max_consecutive_crashes` times in a row (default: 3), pause and reconsider your approach rather than continuing to crash.

### Simplicity Principle

All else equal, prefer simpler code. A tiny improvement requiring 20 ugly lines? Not worth it. A tiny improvement from deleting code? Absolutely keep it.
```

**Step 2: Create config.yaml.j2**

```yaml
# .research/config.yaml
# Research configuration — edit this file to control agent behavior

# Intervention mode
# autonomous: agent runs freely, only pauses on crashes
# collaborative: agent pauses after each phase for human review
mode: autonomous

# Experiment control
experiment:
  timeout: 600                  # seconds per experiment before kill
  max_consecutive_crashes: 3    # pause after N consecutive crashes

# Metrics (filled by agent in Phase 2)
metrics:
  primary:
    name: ""                    # e.g. accuracy, val_loss, test_pass_rate
    direction: ""               # higher_is_better | lower_is_better

# Execution environment
# Describe how to run commands for this project.
# The agent reads this and follows your instructions.
environment: |
  # Examples:
  # Local:  just run commands directly
  # Remote: ssh user@host "cd /path && ..."
  # Docker: docker exec container_name ...
```

**Step 3: Create project-understanding.md.j2**

```markdown
# Project Understanding

> This file is filled by the AI agent during Phase 1.
> Human: review and edit as needed before the agent continues.

## Project Purpose

<!-- What does this project do? What problem does it solve? -->

## Code Structure

<!-- Key directories, modules, classes, and their roles -->

## Entry Points

<!-- CLI commands, scripts, HTTP endpoints, main functions -->

## Tests & Evaluation

<!-- Existing test suites, benchmarks, evaluation scripts -->

## Dependencies & Environment

<!-- Key dependencies, Python version, hardware requirements -->

## Key Observations

<!-- Anything notable: code quality issues, potential improvements, constraints -->
```

**Step 4: Create evaluation.md.j2**

```markdown
# Evaluation Design

> This file is filled by the AI agent during Phase 2.
> Human: review and edit as needed. This defines how experiments are judged.

## Primary Metric

- **Name:** <!-- e.g. accuracy, val_loss, test_pass_rate -->
- **Direction:** <!-- higher_is_better | lower_is_better -->
- **Why this metric:** <!-- brief justification -->

## How to Measure

### Command

```bash
# Exact command to run evaluation
```

### Extracting the Metric

```bash
# How to extract the primary metric value from output
# e.g.: grep "accuracy:" .research/run.log | awk '{print $2}'
```

## Secondary Metrics (Optional)

<!-- Additional metrics to track for context -->

| Metric | How to Extract | Purpose |
|--------|---------------|---------|
| | | |

## Baseline Method

<!-- How to establish the initial baseline measurement -->
```

**Step 5: Commit**

```bash
git add src/open_researcher/templates/
git commit -m "feat: add Jinja2 templates for .research/ scaffolding"
```

---

### Task 3: Helper Scripts (record.py and rollback.sh)

These are copied (not templated) into `.research/scripts/` during init.

**Files:**
- Create: `src/open_researcher/scripts/record.py`
- Create: `src/open_researcher/scripts/rollback.sh`
- Create: `tests/test_record.py`

**Step 1: Write test for record.py**

```python
# tests/test_record.py
import csv
import os
import subprocess
import tempfile
from pathlib import Path


def test_record_appends_to_tsv():
    """record.py should append a row to results.tsv with correct fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup: create a git repo with a commit
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, "dummy.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        # Create .research dir and empty results.tsv with header
        research_dir = Path(tmpdir, ".research")
        research_dir.mkdir()
        results_file = research_dir / "results.tsv"
        results_file.write_text("timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n")

        # Copy record.py
        record_script = Path(__file__).parent.parent / "src" / "open_researcher" / "scripts" / "record.py"
        target_script = research_dir / "scripts" / "record.py"
        target_script.parent.mkdir(parents=True, exist_ok=True)
        target_script.write_text(record_script.read_text())

        # Run record.py
        result = subprocess.run(
            [
                "python", str(target_script),
                "--metric", "accuracy",
                "--value", "0.85",
                "--secondary", '{"f1": 0.83}',
                "--status", "keep",
                "--desc", "baseline",
            ],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"record.py failed: {result.stderr}"

        # Verify results.tsv
        rows = list(csv.DictReader(results_file.open(), delimiter="\t"))
        assert len(rows) == 1
        assert rows[0]["primary_metric"] == "accuracy"
        assert rows[0]["metric_value"] == "0.85"
        assert rows[0]["status"] == "keep"
        assert rows[0]["description"] == "baseline"
        assert rows[0]["secondary_metrics"] == '{"f1": 0.83}'
        assert len(rows[0]["commit"]) == 7  # short hash
        assert rows[0]["timestamp"]  # non-empty


def test_record_creates_header_if_missing():
    """record.py should create results.tsv with header if file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, "dummy.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        research_dir = Path(tmpdir, ".research")
        research_dir.mkdir()
        scripts_dir = research_dir / "scripts"
        scripts_dir.mkdir()

        record_script = Path(__file__).parent.parent / "src" / "open_researcher" / "scripts" / "record.py"
        target_script = scripts_dir / "record.py"
        target_script.write_text(record_script.read_text())

        result = subprocess.run(
            [
                "python", str(target_script),
                "--metric", "loss",
                "--value", "0.42",
                "--status", "keep",
                "--desc", "test",
            ],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        results_file = research_dir / "results.tsv"
        assert results_file.exists()
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert lines[0].startswith("timestamp\t")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_record.py -v`
Expected: FAIL — record.py doesn't exist yet

**Step 3: Create record.py**

```python
#!/usr/bin/env python3
"""Record an experiment result to .research/results.tsv."""

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_git_short_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description="Record experiment result")
    parser.add_argument("--metric", required=True, help="Primary metric name")
    parser.add_argument("--value", required=True, type=float, help="Metric value")
    parser.add_argument("--secondary", default="{}", help="Secondary metrics as JSON")
    parser.add_argument("--status", required=True, choices=["keep", "discard", "crash"], help="Experiment status")
    parser.add_argument("--desc", required=True, help="Brief description")
    args = parser.parse_args()

    # Find .research/results.tsv relative to git root
    git_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    ).stdout.strip()
    results_path = Path(git_root) / ".research" / "results.tsv"

    header = ["timestamp", "commit", "primary_metric", "metric_value", "secondary_metrics", "status", "description"]

    # Create file with header if it doesn't exist
    if not results_path.exists():
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with results_path.open("w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(header)

    # Append row
    row = [
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        get_git_short_hash(),
        args.metric,
        f"{args.value:.6f}",
        args.secondary,
        args.status,
        args.desc,
    ]
    with results_path.open("a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(row)

    print(f"[OK] Recorded: {args.status} | {args.metric}={args.value:.6f} | {args.desc}")


if __name__ == "__main__":
    main()
```

**Step 4: Create rollback.sh**

```bash
#!/usr/bin/env bash
# Rollback the last experiment commit (git reset --hard HEAD~1).
# Used by the agent when an experiment doesn't improve the primary metric.
set -Eeuo pipefail

echo "[rollback] Resetting to previous commit..."
git reset --hard HEAD~1
echo "[OK] Rolled back to $(git rev-parse --short=7 HEAD)"
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_record.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/open_researcher/scripts/ tests/test_record.py
git commit -m "feat: add record.py and rollback.sh helper scripts with tests"
```

---

### Task 4: Init Command

Implement `open-researcher init` — renders templates into `.research/` and copies scripts.

**Files:**
- Create: `src/open_researcher/init_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Create: `tests/test_init.py`

**Step 1: Write test for init**

```python
# tests/test_init.py
import os
import subprocess
import tempfile
from pathlib import Path

from open_researcher.init_cmd import do_init


def test_init_creates_research_directory():
    """init should create .research/ with all expected files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)

        do_init(repo_path=Path(tmpdir), tag="test1")

        research = Path(tmpdir, ".research")
        assert research.is_dir()
        assert (research / "program.md").is_file()
        assert (research / "config.yaml").is_file()
        assert (research / "project-understanding.md").is_file()
        assert (research / "evaluation.md").is_file()
        assert (research / "results.tsv").is_file()
        assert (research / "scripts" / "record.py").is_file()
        assert (research / "scripts" / "rollback.sh").is_file()

        # Check tag substitution in program.md
        program = (research / "program.md").read_text()
        assert "test1" in program

        # Check results.tsv has header
        results = (research / "results.tsv").read_text()
        assert results.startswith("timestamp\t")

        # Check rollback.sh is executable
        assert os.access(research / "scripts" / "rollback.sh", os.X_OK)


def test_init_refuses_if_research_exists():
    """init should refuse if .research/ already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, ".research").mkdir()

        try:
            do_init(repo_path=Path(tmpdir), tag="test2")
            assert False, "Should have raised"
        except SystemExit:
            pass


def test_init_generates_default_tag():
    """init without tag should use today's date."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)

        do_init(repo_path=Path(tmpdir), tag=None)

        program = (Path(tmpdir) / ".research" / "program.md").read_text()
        # Should contain a date-based tag like "mar08" or similar
        assert "research/" in program
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_init.py -v`
Expected: FAIL — init_cmd module doesn't exist

**Step 3: Implement init_cmd.py**

```python
# src/open_researcher/init_cmd.py
"""Implementation of the 'init' command."""

import os
import shutil
import stat
import sys
from datetime import date
from pathlib import Path

from jinja2 import Environment, PackageLoader


def do_init(repo_path: Path, tag: str | None = None) -> None:
    """Initialize .research/ directory in the given repo."""
    research_dir = repo_path / ".research"

    if research_dir.exists():
        print(f"[ERROR] .research/ already exists at {research_dir}", file=sys.stderr)
        raise SystemExit(1)

    # Generate tag from date if not provided
    if tag is None:
        today = date.today()
        tag = today.strftime("%b%d").lower()  # e.g. "mar08"

    # Render templates
    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    context = {"tag": tag}

    research_dir.mkdir()

    # Render each template
    for template_name, output_name in [
        ("program.md.j2", "program.md"),
        ("config.yaml.j2", "config.yaml"),
        ("project-understanding.md.j2", "project-understanding.md"),
        ("evaluation.md.j2", "evaluation.md"),
    ]:
        template = env.get_template(template_name)
        content = template.render(context)
        (research_dir / output_name).write_text(content)

    # Create results.tsv with header
    header = "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
    (research_dir / "results.tsv").write_text(header)

    # Copy helper scripts
    scripts_dir = research_dir / "scripts"
    scripts_dir.mkdir()

    scripts_src = Path(__file__).parent / "scripts"
    for script_name in ["record.py", "rollback.sh"]:
        src = scripts_src / script_name
        dst = scripts_dir / script_name
        shutil.copy2(src, dst)

    # Make shell scripts executable
    rollback = scripts_dir / "rollback.sh"
    rollback.chmod(rollback.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[OK] Initialized .research/ with tag '{tag}'")
    print(f"     Branch: research/{tag}")
    print(f"     Next: point your AI agent at .research/program.md")
```

**Step 4: Wire up CLI**

Replace the `init` function in `cli.py`:

```python
# In cli.py, replace the init command:
from pathlib import Path
from open_researcher.init_cmd import do_init

@app.command()
def init(tag: str = typer.Option(None, help="Experiment tag (e.g. mar8). Defaults to today's date.")):
    """Initialize .research/ directory in the current repo."""
    do_init(repo_path=Path.cwd(), tag=tag)
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_init.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/open_researcher/init_cmd.py src/open_researcher/cli.py tests/test_init.py
git commit -m "feat: implement init command with template rendering"
```

---

### Task 5: Status Command

Implement `open-researcher status` — reads `.research/` files and displays formatted progress.

**Files:**
- Create: `src/open_researcher/status_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Create: `tests/test_status.py`

**Step 1: Write test for status parsing**

```python
# tests/test_status.py
import tempfile
from pathlib import Path

from open_researcher.status_cmd import parse_research_state


def test_parse_state_with_results():
    """Should correctly parse results.tsv and config.yaml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        # Write config
        (research / "config.yaml").write_text(
            "mode: autonomous\n"
            "metrics:\n"
            "  primary:\n"
            "    name: accuracy\n"
            "    direction: higher_is_better\n"
        )

        # Write results
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
            "2026-03-08T10:00:00\ta1b2c3d\taccuracy\t0.850000\t{}\tkeep\tbaseline\n"
            "2026-03-08T10:15:00\tb2c3d4e\taccuracy\t0.872000\t{}\tkeep\tincrease LR\n"
            "2026-03-08T10:30:00\tc3d4e5f\taccuracy\t0.840000\t{}\tdiscard\tswitch optimizer\n"
            "2026-03-08T10:45:00\td4e5f6g\taccuracy\t0.000000\t{}\tcrash\tOOM\n"
        )

        # Write project understanding (phase 1 complete)
        (research / "project-understanding.md").write_text("# Project\n\nFilled in.")

        # Write evaluation (phase 2 complete)
        (research / "evaluation.md").write_text("# Eval\n\nFilled in.")

        state = parse_research_state(Path(tmpdir))

        assert state["mode"] == "autonomous"
        assert state["primary_metric"] == "accuracy"
        assert state["direction"] == "higher_is_better"
        assert state["total"] == 4
        assert state["keep"] == 2
        assert state["discard"] == 1
        assert state["crash"] == 1
        assert state["baseline_value"] == 0.85
        assert state["current_value"] == 0.872
        assert state["best_value"] == 0.872
        assert len(state["recent"]) == 4


def test_parse_state_empty():
    """Should handle empty results.tsv (no experiments yet)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        (research / "config.yaml").write_text(
            "mode: collaborative\n"
            "metrics:\n"
            "  primary:\n"
            "    name: ''\n"
            "    direction: ''\n"
        )
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        )
        (research / "project-understanding.md").write_text("<!-- empty -->")
        (research / "evaluation.md").write_text("<!-- empty -->")

        state = parse_research_state(Path(tmpdir))
        assert state["total"] == 0
        assert state["phase"] == 1  # no understanding filled yet
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_status.py -v`
Expected: FAIL — status_cmd doesn't exist

**Step 3: Implement status_cmd.py**

```python
# src/open_researcher/status_cmd.py
"""Implementation of the 'status' command."""

import csv
import subprocess
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _detect_phase(research: Path) -> int:
    """Detect current research phase (1-4) based on file contents."""
    pu = research / "project-understanding.md"
    ev = research / "evaluation.md"
    results = research / "results.tsv"

    # Phase 1: project understanding not filled
    if pu.exists():
        content = pu.read_text()
        if "<!--" in content and content.strip().endswith("-->"):
            return 1
        has_content = any(
            line.strip() and not line.startswith("#") and not line.startswith(">") and "<!--" not in line
            for line in content.splitlines()
        )
        if not has_content:
            return 1

    # Phase 2: evaluation not filled
    if ev.exists():
        content = ev.read_text()
        has_content = any(
            line.strip() and not line.startswith("#") and not line.startswith(">") and "<!--" not in line
            for line in content.splitlines()
        )
        if not has_content:
            return 2

    # Phase 3/4: check results
    if results.exists():
        rows = list(csv.DictReader(results.open(), delimiter="\t"))
        if len(rows) == 0:
            return 3  # no baseline yet
        return 4  # experiment loop

    return 3


def parse_research_state(repo_path: Path) -> dict:
    """Parse .research/ directory into a state dict."""
    research = repo_path / ".research"
    state = {}

    # Parse config
    config_path = research / "config.yaml"
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text()) or {}
        state["mode"] = config.get("mode", "autonomous")
        metrics = config.get("metrics", {}).get("primary", {})
        state["primary_metric"] = metrics.get("name", "")
        state["direction"] = metrics.get("direction", "")
    else:
        state["mode"] = "unknown"
        state["primary_metric"] = ""
        state["direction"] = ""

    # Parse results
    results_path = research / "results.tsv"
    rows = []
    if results_path.exists():
        rows = list(csv.DictReader(results_path.open(), delimiter="\t"))

    state["total"] = len(rows)
    state["keep"] = sum(1 for r in rows if r["status"] == "keep")
    state["discard"] = sum(1 for r in rows if r["status"] == "discard")
    state["crash"] = sum(1 for r in rows if r["status"] == "crash")
    state["recent"] = rows[-5:] if rows else []

    # Compute metric values
    higher = state["direction"] == "higher_is_better"
    keep_rows = [r for r in rows if r["status"] == "keep"]
    if keep_rows:
        values = [float(r["metric_value"]) for r in keep_rows]
        state["baseline_value"] = values[0]
        state["current_value"] = values[-1]
        state["best_value"] = max(values) if higher else min(values)
    else:
        state["baseline_value"] = None
        state["current_value"] = None
        state["best_value"] = None

    state["phase"] = _detect_phase(research)

    # Git branch
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True, cwd=repo_path,
    )
    state["branch"] = result.stdout.strip() if result.returncode == 0 else "unknown"

    return state


PHASE_NAMES = {
    1: "理解项目 (Phase 1)",
    2: "设计评估 (Phase 2)",
    3: "建立基线 (Phase 3)",
    4: "实验循环 (Phase 4)",
}


def print_status(repo_path: Path) -> None:
    """Print formatted research status to terminal."""
    research = repo_path / ".research"
    if not research.exists():
        print("[ERROR] No .research/ directory found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    state = parse_research_state(repo_path)
    console = Console()

    # Build status lines
    lines = []
    lines.append(f"  阶段: {PHASE_NAMES.get(state['phase'], 'unknown')}")
    lines.append(f"  分支: {state['branch']}")
    lines.append(f"  模式: {state['mode']}")
    lines.append("")

    if state["total"] > 0:
        lines.append("  实验统计:")
        lines.append(
            f"    总数: {state['total']}  "
            f"✓ keep: {state['keep']}  "
            f"✗ discard: {state['discard']}  "
            f"💥 crash: {state['crash']}"
        )
        lines.append("")

        if state["primary_metric"]:
            lines.append(f"  主要指标: {state['primary_metric']}")
            if state["baseline_value"] is not None:
                lines.append(f"    基线:  {state['baseline_value']:.4f}")
                lines.append(f"    当前:  {state['current_value']:.4f}")
                lines.append(f"    最佳:  {state['best_value']:.4f}")
            lines.append("")

        lines.append(f"  最近 {len(state['recent'])} 次实验:")
        status_icons = {"keep": "✓", "discard": "✗", "crash": "💥"}
        for r in reversed(state["recent"]):
            icon = status_icons.get(r["status"], "?")
            val = float(r["metric_value"])
            lines.append(f"    {icon} {val:.4f}  {r['description']}")
    else:
        lines.append("  尚无实验记录")

    panel = Panel(
        "\n".join(lines),
        title="Open Researcher",
        border_style="blue",
    )
    console.print(panel)
```

**Step 4: Wire up CLI**

```python
# In cli.py, replace the status command:
from open_researcher.status_cmd import print_status

@app.command()
def status():
    """Show current research progress."""
    print_status(Path.cwd())
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_status.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/open_researcher/status_cmd.py src/open_researcher/cli.py tests/test_status.py
git commit -m "feat: implement status command with Rich formatting"
```

---

### Task 6: Results Command

Implement `open-researcher results` — formatted table of all experiments.

**Files:**
- Create: `src/open_researcher/results_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Create: `tests/test_results.py`

**Step 1: Write test**

```python
# tests/test_results.py
import tempfile
from pathlib import Path

from open_researcher.results_cmd import load_results


def test_load_results():
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
            "2026-03-08T10:00:00\ta1b2c3d\taccuracy\t0.850000\t{}\tkeep\tbaseline\n"
        )
        rows = load_results(Path(tmpdir))
        assert len(rows) == 1
        assert rows[0]["status"] == "keep"
```

**Step 2: Run test — expect FAIL**

Run: `python -m pytest tests/test_results.py -v`

**Step 3: Implement results_cmd.py**

```python
# src/open_researcher/results_cmd.py
"""Implementation of the 'results' command."""

import csv
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table


def load_results(repo_path: Path) -> list[dict]:
    results_path = repo_path / ".research" / "results.tsv"
    if not results_path.exists():
        return []
    return list(csv.DictReader(results_path.open(), delimiter="\t"))


def print_results(repo_path: Path) -> None:
    research = repo_path / ".research"
    if not research.exists():
        print("[ERROR] No .research/ directory found.", file=sys.stderr)
        raise SystemExit(1)

    rows = load_results(repo_path)
    if not rows:
        print("No experiment results yet.")
        return

    console = Console()
    table = Table(title="Experiment Results")
    table.add_column("#", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_column("Commit", style="dim")
    table.add_column("Description")
    table.add_column("Time", style="dim")

    status_styles = {"keep": "green", "discard": "yellow", "crash": "red"}

    for i, row in enumerate(rows, 1):
        style = status_styles.get(row["status"], "")
        table.add_row(
            str(i),
            row["status"],
            row["primary_metric"],
            row["metric_value"],
            row["commit"],
            row["description"],
            row["timestamp"][:19],
            style=style,
        )

    console.print(table)
```

**Step 4: Wire up CLI**

```python
# In cli.py:
from open_researcher.results_cmd import print_results

@app.command()
def results():
    """Print experiment results table."""
    print_results(Path.cwd())
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_results.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/open_researcher/results_cmd.py tests/test_results.py src/open_researcher/cli.py
git commit -m "feat: implement results command with Rich table"
```

---

### Task 7: Export Command

Implement `open-researcher export` — generates a Markdown experiment report.

**Files:**
- Create: `src/open_researcher/export_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Create: `tests/test_export.py`

**Step 1: Write test**

```python
# tests/test_export.py
import tempfile
from pathlib import Path

from open_researcher.export_cmd import generate_report


def test_generate_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()
        (research / "config.yaml").write_text(
            "mode: autonomous\nmetrics:\n  primary:\n    name: accuracy\n    direction: higher_is_better\n"
        )
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
            "2026-03-08T10:00:00\ta1b2c3d\taccuracy\t0.850000\t{}\tkeep\tbaseline\n"
            "2026-03-08T10:15:00\tb2c3d4e\taccuracy\t0.870000\t{}\tkeep\tincrease LR\n"
        )
        (research / "project-understanding.md").write_text("# Project\nTest project")
        (research / "evaluation.md").write_text("# Eval\nTest eval")

        report = generate_report(Path(tmpdir))
        assert "# Experiment Report" in report
        assert "accuracy" in report
        assert "baseline" in report
        assert "0.870000" in report
```

**Step 2: Run test — expect FAIL**

**Step 3: Implement export_cmd.py**

```python
# src/open_researcher/export_cmd.py
"""Implementation of the 'export' command."""

import sys
from pathlib import Path

import yaml

from open_researcher.results_cmd import load_results


def generate_report(repo_path: Path) -> str:
    research = repo_path / ".research"
    config = yaml.safe_load((research / "config.yaml").read_text()) or {}
    rows = load_results(repo_path)

    primary = config.get("metrics", {}).get("primary", {})
    metric_name = primary.get("name", "unknown")
    direction = primary.get("direction", "")

    lines = []
    lines.append("# Experiment Report")
    lines.append("")
    lines.append(f"**Primary Metric:** {metric_name} ({direction})")
    lines.append(f"**Total Experiments:** {len(rows)}")
    lines.append("")

    # Summary
    keep_rows = [r for r in rows if r["status"] == "keep"]
    discard_rows = [r for r in rows if r["status"] == "discard"]
    crash_rows = [r for r in rows if r["status"] == "crash"]
    lines.append(f"- Keep: {len(keep_rows)}")
    lines.append(f"- Discard: {len(discard_rows)}")
    lines.append(f"- Crash: {len(crash_rows)}")
    lines.append("")

    # Results table
    lines.append("## Results")
    lines.append("")
    lines.append("| # | Status | Value | Description |")
    lines.append("|---|--------|-------|-------------|")
    for i, row in enumerate(rows, 1):
        lines.append(f"| {i} | {row['status']} | {row['metric_value']} | {row['description']} |")
    lines.append("")

    return "\n".join(lines)


def do_export(repo_path: Path) -> None:
    research = repo_path / ".research"
    if not research.exists():
        print("[ERROR] No .research/ directory found.", file=sys.stderr)
        raise SystemExit(1)

    report = generate_report(repo_path)
    print(report)
```

**Step 4: Wire up CLI**

```python
# In cli.py:
from open_researcher.export_cmd import do_export

@app.command()
def export():
    """Export experiment report as Markdown."""
    do_export(Path.cwd())
```

**Step 5: Run tests, commit**

Run: `python -m pytest tests/test_export.py -v`

```bash
git add src/open_researcher/export_cmd.py tests/test_export.py src/open_researcher/cli.py
git commit -m "feat: implement export command for Markdown reports"
```

---

### Task 8: Web Dashboard — Backend

Implement the FastAPI backend for the dashboard.

**Files:**
- Create: `src/open_researcher/dashboard/__init__.py`
- Create: `src/open_researcher/dashboard/app.py`
- Create: `tests/test_dashboard.py`

**Step 1: Write test**

```python
# tests/test_dashboard.py
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _setup_research(tmpdir: str) -> Path:
    research = Path(tmpdir, ".research")
    research.mkdir()
    (research / "config.yaml").write_text(
        "mode: autonomous\nmetrics:\n  primary:\n    name: accuracy\n    direction: higher_is_better\n"
    )
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        "2026-03-08T10:00:00\ta1b2c3d\taccuracy\t0.850000\t{}\tkeep\tbaseline\n"
    )
    (research / "project-understanding.md").write_text("# Project\nTest")
    (research / "evaluation.md").write_text("# Eval\nTest")
    return Path(tmpdir)


def test_api_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_research(tmpdir)
        with patch("open_researcher.dashboard.app.REPO_PATH", repo):
            from open_researcher.dashboard.app import create_app
            app = create_app(repo)
            client = TestClient(app)
            resp = client.get("/api/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["primary_metric"] == "accuracy"


def test_api_results():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_research(tmpdir)
        with patch("open_researcher.dashboard.app.REPO_PATH", repo):
            from open_researcher.dashboard.app import create_app
            app = create_app(repo)
            client = TestClient(app)
            resp = client.get("/api/results")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["status"] == "keep"
```

**Step 2: Run test — expect FAIL**

**Step 3: Implement dashboard app.py**

```python
# src/open_researcher/dashboard/__init__.py
```

```python
# src/open_researcher/dashboard/app.py
"""FastAPI web dashboard for Open Researcher."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from open_researcher.results_cmd import load_results
from open_researcher.status_cmd import parse_research_state

REPO_PATH = Path.cwd()

DASHBOARD_DIR = Path(__file__).parent


def create_app(repo_path: Path | None = None) -> FastAPI:
    if repo_path is None:
        repo_path = REPO_PATH

    app = FastAPI(title="Open Researcher Dashboard")

    @app.get("/api/status")
    def api_status():
        return parse_research_state(repo_path)

    @app.get("/api/results")
    def api_results():
        return load_results(repo_path)

    @app.get("/api/docs/{name}")
    def api_doc(name: str):
        allowed = ["project-understanding.md", "evaluation.md", "program.md"]
        if name not in allowed:
            return {"error": "not found"}
        path = repo_path / ".research" / name
        if not path.exists():
            return {"content": ""}
        return {"content": path.read_text()}

    @app.get("/", response_class=HTMLResponse)
    def index():
        template_path = DASHBOARD_DIR / "templates" / "index.html"
        if template_path.exists():
            return template_path.read_text()
        return "<h1>Open Researcher Dashboard</h1><p>Templates not found.</p>"

    return app
```

**Step 4: Wire up CLI dashboard command**

```python
# In cli.py:
@app.command()
def dashboard(port: int = typer.Option(8384, help="Dashboard port")):
    """Launch web dashboard."""
    import uvicorn
    from open_researcher.dashboard.app import create_app
    web_app = create_app(Path.cwd())
    typer.echo(f"Starting dashboard at http://localhost:{port}")
    uvicorn.run(web_app, host="0.0.0.0", port=port)
```

**Step 5: Run tests, commit**

Run: `python -m pytest tests/test_dashboard.py -v`

```bash
git add src/open_researcher/dashboard/ tests/test_dashboard.py src/open_researcher/cli.py
git commit -m "feat: implement dashboard API backend"
```

---

### Task 9: Web Dashboard — Frontend

Create the HTML template with Chart.js visualization.

**Files:**
- Create: `src/open_researcher/dashboard/templates/index.html`

**Step 1: Create the dashboard HTML**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Open Researcher Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { font-size: 24px; color: #58a6ff; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
        .card h2 { font-size: 16px; color: #8b949e; margin-bottom: 12px; }
        .stat { font-size: 32px; font-weight: bold; color: #58a6ff; }
        .stat-label { font-size: 14px; color: #8b949e; }
        .stat-row { display: flex; gap: 20px; margin-top: 10px; }
        .stat-item { text-align: center; }
        .stat-item .num { font-size: 20px; font-weight: bold; }
        .keep { color: #3fb950; }
        .discard { color: #d29922; }
        .crash { color: #f85149; }
        .chart-container { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }
        th { color: #8b949e; font-weight: 600; }
        .badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .badge-keep { background: #238636; color: #fff; }
        .badge-discard { background: #9e6a03; color: #fff; }
        .badge-crash { background: #da3633; color: #fff; }
        .phase-indicator { display: inline-block; padding: 4px 12px; border-radius: 16px; background: #1f6feb; color: #fff; font-size: 14px; }
        .doc-viewer { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; white-space: pre-wrap; font-family: monospace; font-size: 13px; max-height: 400px; overflow-y: auto; }
        .tabs { display: flex; gap: 8px; margin-bottom: 12px; }
        .tab { padding: 6px 16px; border-radius: 6px; cursor: pointer; background: #21262d; border: 1px solid #30363d; color: #c9d1d9; }
        .tab.active { background: #1f6feb; border-color: #1f6feb; color: #fff; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Open Researcher</h1>
    </div>

    <div class="grid">
        <div class="card">
            <h2>Phase</h2>
            <div id="phase" class="phase-indicator">Loading...</div>
        </div>
        <div class="card">
            <h2>Primary Metric</h2>
            <div id="metric-current" class="stat">—</div>
            <div id="metric-name" class="stat-label"></div>
            <div class="stat-row">
                <div class="stat-item"><div class="stat-label">Baseline</div><div id="metric-baseline" class="num">—</div></div>
                <div class="stat-item"><div class="stat-label">Best</div><div id="metric-best" class="num">—</div></div>
            </div>
        </div>
        <div class="card">
            <h2>Experiments</h2>
            <div id="total" class="stat">0</div>
            <div class="stat-row">
                <div class="stat-item"><div class="num keep" id="n-keep">0</div><div class="stat-label">Keep</div></div>
                <div class="stat-item"><div class="num discard" id="n-discard">0</div><div class="stat-label">Discard</div></div>
                <div class="stat-item"><div class="num crash" id="n-crash">0</div><div class="stat-label">Crash</div></div>
            </div>
        </div>
    </div>

    <div class="chart-container">
        <h2 style="color: #8b949e; margin-bottom: 12px;">Metric Trend</h2>
        <canvas id="chart" height="80"></canvas>
    </div>

    <div class="card" style="margin-bottom: 20px;">
        <h2>Experiment History</h2>
        <table>
            <thead><tr><th>#</th><th>Status</th><th>Value</th><th>Description</th><th>Time</th></tr></thead>
            <tbody id="results-table"></tbody>
        </table>
    </div>

    <div>
        <div class="tabs">
            <div class="tab active" onclick="showDoc('project-understanding.md', this)">Project Understanding</div>
            <div class="tab" onclick="showDoc('evaluation.md', this)">Evaluation Design</div>
            <div class="tab" onclick="showDoc('program.md', this)">Program</div>
        </div>
        <div id="doc-viewer" class="doc-viewer">Loading...</div>
    </div>

    <script>
        const PHASE_NAMES = {1: 'Phase 1: Understand Project', 2: 'Phase 2: Design Evaluation', 3: 'Phase 3: Establish Baseline', 4: 'Phase 4: Experiment Loop'};
        let chart = null;

        async function refresh() {
            const [statusResp, resultsResp] = await Promise.all([
                fetch('/api/status'), fetch('/api/results')
            ]);
            const status = await statusResp.json();
            const results = await resultsResp.json();

            document.getElementById('phase').textContent = PHASE_NAMES[status.phase] || 'Unknown';
            document.getElementById('total').textContent = status.total;
            document.getElementById('n-keep').textContent = status.keep;
            document.getElementById('n-discard').textContent = status.discard;
            document.getElementById('n-crash').textContent = status.crash;
            document.getElementById('metric-name').textContent = status.primary_metric || '—';

            if (status.current_value != null) {
                document.getElementById('metric-current').textContent = status.current_value.toFixed(4);
                document.getElementById('metric-baseline').textContent = status.baseline_value.toFixed(4);
                document.getElementById('metric-best').textContent = status.best_value.toFixed(4);
            }

            // Table
            const tbody = document.getElementById('results-table');
            tbody.innerHTML = results.map((r, i) =>
                `<tr><td>${i+1}</td><td><span class="badge badge-${r.status}">${r.status}</span></td><td>${parseFloat(r.metric_value).toFixed(4)}</td><td>${r.description}</td><td>${r.timestamp.slice(0,19)}</td></tr>`
            ).join('');

            // Chart
            const keepResults = results.filter(r => r.status === 'keep');
            const labels = keepResults.map((_, i) => `#${i+1}`);
            const data = keepResults.map(r => parseFloat(r.metric_value));

            if (chart) chart.destroy();
            chart = new Chart(document.getElementById('chart'), {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: status.primary_metric || 'Metric',
                        data,
                        borderColor: '#58a6ff',
                        backgroundColor: 'rgba(88,166,255,0.1)',
                        fill: true, tension: 0.3, pointRadius: 4,
                    }]
                },
                options: {
                    scales: {
                        x: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } },
                        y: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } }
                    },
                    plugins: { legend: { labels: { color: '#c9d1d9' } } }
                }
            });
        }

        async function showDoc(name, el) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            const resp = await fetch(`/api/docs/${name}`);
            const data = await resp.json();
            document.getElementById('doc-viewer').textContent = data.content || '(empty)';
        }

        refresh();
        setInterval(refresh, 10000);
        showDoc('project-understanding.md', document.querySelector('.tab.active'));
    </script>
</body>
</html>
```

**Step 2: Test manually**

Run: `open-researcher init --tag test && open-researcher dashboard`
Open: http://localhost:8384
Expected: Dashboard loads showing Phase 1, empty experiments

**Step 3: Commit**

```bash
git add src/open_researcher/dashboard/templates/
git commit -m "feat: add web dashboard frontend with Chart.js"
```

---

### Task 10: Integration Test & Final CLI Polish

End-to-end test: init → record → status → results → export.

**Files:**
- Create: `tests/test_integration.py`
- Modify: `src/open_researcher/cli.py` (final version)

**Step 1: Write integration test**

```python
# tests/test_integration.py
import subprocess
import tempfile
from pathlib import Path

from open_researcher.init_cmd import do_init
from open_researcher.status_cmd import parse_research_state
from open_researcher.results_cmd import load_results
from open_researcher.export_cmd import generate_report


def test_full_workflow():
    """Test init → record → status → results → export."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup git repo with a commit
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, "train.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True)

        repo = Path(tmpdir)

        # 1. Init
        do_init(repo, tag="test1")
        assert (repo / ".research" / "program.md").exists()
        assert (repo / ".research" / "scripts" / "record.py").exists()

        # 2. Simulate agent filling in config
        import yaml
        config_path = repo / ".research" / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["metrics"]["primary"]["name"] = "accuracy"
        config["metrics"]["primary"]["direction"] = "higher_is_better"
        config_path.write_text(yaml.dump(config))

        # 3. Record baseline
        record_script = repo / ".research" / "scripts" / "record.py"
        result = subprocess.run(
            ["python", str(record_script),
             "--metric", "accuracy", "--value", "0.85",
             "--status", "keep", "--desc", "baseline"],
            cwd=tmpdir, capture_output=True, text=True,
        )
        assert result.returncode == 0

        # 4. Record an experiment
        result = subprocess.run(
            ["python", str(record_script),
             "--metric", "accuracy", "--value", "0.87",
             "--secondary", '{"f1": 0.86}',
             "--status", "keep", "--desc", "increase LR"],
            cwd=tmpdir, capture_output=True, text=True,
        )
        assert result.returncode == 0

        # 5. Check status
        state = parse_research_state(repo)
        assert state["total"] == 2
        assert state["keep"] == 2
        assert state["current_value"] == 0.87
        assert state["baseline_value"] == 0.85

        # 6. Check results
        rows = load_results(repo)
        assert len(rows) == 2

        # 7. Check export
        report = generate_report(repo)
        assert "accuracy" in report
        assert "baseline" in report
        assert "increase LR" in report
```

**Step 2: Run test**

Run: `python -m pytest tests/test_integration.py -v`
Expected: PASS

**Step 3: Finalize cli.py**

```python
# src/open_researcher/cli.py
"""Open Researcher CLI — research workflow framework for AI agents."""

from pathlib import Path

import typer

app = typer.Typer(
    name="open-researcher",
    help="Research workflow framework for AI agents. "
         "Initialize automated experiment tracking in any repo.",
)


@app.command()
def init(tag: str = typer.Option(None, help="Experiment tag (e.g. mar8). Defaults to today's date.")):
    """Initialize .research/ directory in the current repo."""
    from open_researcher.init_cmd import do_init
    do_init(repo_path=Path.cwd(), tag=tag)


@app.command()
def status():
    """Show current research progress."""
    from open_researcher.status_cmd import print_status
    print_status(Path.cwd())


@app.command()
def results():
    """Print experiment results table."""
    from open_researcher.results_cmd import print_results
    print_results(Path.cwd())


@app.command()
def dashboard(port: int = typer.Option(8384, help="Dashboard port")):
    """Launch web dashboard."""
    import uvicorn
    from open_researcher.dashboard.app import create_app
    web_app = create_app(Path.cwd())
    typer.echo(f"Starting dashboard at http://localhost:{port}")
    uvicorn.run(web_app, host="0.0.0.0", port=port)


@app.command()
def export():
    """Export experiment report as Markdown."""
    from open_researcher.export_cmd import do_export
    do_export(Path.cwd())


if __name__ == "__main__":
    app()
```

**Step 4: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add tests/test_integration.py src/open_researcher/cli.py
git commit -m "feat: add integration test and finalize CLI"
```

---

### Task 11: End-to-End Manual Verification

**Step 1: Install and test CLI**

```bash
uv pip install -e ".[dev]"
open-researcher --help
```

**Step 2: Test in a temp repo**

```bash
cd /tmp && mkdir test-repo && cd test-repo
git init && git commit --allow-empty -m "init"
open-researcher init --tag demo1
cat .research/program.md
open-researcher status
open-researcher results
```

**Step 3: Simulate experiment workflow**

```bash
python .research/scripts/record.py --metric accuracy --value 0.85 --status keep --desc "baseline"
python .research/scripts/record.py --metric accuracy --value 0.87 --status keep --desc "increase LR"
python .research/scripts/record.py --metric accuracy --value 0.84 --status discard --desc "switch optimizer"
open-researcher status
open-researcher results
open-researcher export
open-researcher dashboard
```

**Step 4: Verify dashboard at http://localhost:8384**

**Step 5: Clean up temp repo**

```bash
rm -rf /tmp/test-repo
```

**Step 6: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address issues found in manual verification"
```
