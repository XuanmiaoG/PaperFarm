# Beta Release Implementation Plan

> **Historical note (2026-03-10):** This plan predates the `IdeaBacklog` / `IdeaPool` split. Any examples using `claimed_by`, `assigned_experiment`, or claim-token metadata now describe parallel-worker mode only, not the default serial backlog path.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring open-researcher to beta quality by implementing all README-promised features across 4 independent modules.

**Architecture:** 4 parallel modules (D→C→B→A merge order): Module D (robustness + cross-platform), Module C (runtime controls), Module B (CLI charts + subcommands), Module A (TUI multi-view). Each module works in an isolated worktree. Shared interfaces are stable (results.tsv, idea_pool.json, activity.json, control.json, config.yaml).

**Tech Stack:** Python 3.10+, Textual, plotext, textual-plotext, filelock, typer, rich, pyyaml

**Design Doc:** `docs/plans/2026-03-09-beta-release-design.md`

---

## Module D: Robustness + Cross-Platform + Tests

> Merge first. No UI changes. Fixes internal locking, error handling, and platform compatibility.

### Task D1: Add filelock dependency

**Files:**
- Modify: `pyproject.toml:28` (dependencies list)

**Step 1: Add filelock to dependencies**

In `pyproject.toml`, add `"filelock>=3.12.0"` to the `dependencies` list:

```python
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    "jinja2>=3.1.0",
    "pyyaml>=6.0",
    "textual>=0.85.0",
    "filelock>=3.12.0",
]
```

**Step 2: Install**

Run: `pip install -e ".[dev]"`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add filelock dependency for cross-platform file locking"
```

---

### Task D2: Migrate idea_pool.py from fcntl to filelock

**Files:**
- Modify: `src/open_researcher/idea_pool.py`
- Test: `tests/test_idea_pool.py`

**Step 1: Write concurrency test**

Add to `tests/test_idea_pool.py`:

```python
import threading

def test_concurrent_adds(tmp_path):
    """Multiple threads adding ideas should not lose data."""
    pool_path = tmp_path / "idea_pool.json"
    pool_path.write_text('{"ideas": []}')

    pool = IdeaPool(pool_path)
    errors = []

    def add_idea(i):
        try:
            pool.add(f"idea-{i}", source="test", category="general", priority=5)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=add_idea, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(pool.all_ideas()) == 20


def test_concurrent_claim(tmp_path):
    """Two threads claiming should not get the same idea."""
    pool_path = tmp_path / "idea_pool.json"
    pool_path.write_text('{"ideas": []}')

    pool = IdeaPool(pool_path)
    for i in range(5):
        pool.add(f"idea-{i}")

    claimed = []
    def claim():
        idea = pool.claim_idea("worker")
        if idea:
            claimed.append(idea["id"])

    threads = [threading.Thread(target=claim) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All claimed IDs must be unique
    assert len(claimed) == len(set(claimed))
```

**Step 2: Run test to verify current behavior**

Run: `pytest tests/test_idea_pool.py::test_concurrent_adds tests/test_idea_pool.py::test_concurrent_claim -v`

**Step 3: Rewrite idea_pool.py to use filelock**

Replace `fcntl` with `filelock` in `src/open_researcher/idea_pool.py`. Key changes:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock


class IdeaPool:
    """Read/write idea_pool.json with cross-platform file locking."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = FileLock(str(path) + ".lock")

    def _read(self) -> dict:
        if not self.path.exists():
            return {"ideas": []}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"ideas": []}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def _next_id(self, data: dict) -> str:
        existing = [i["id"] for i in data["ideas"]]
        n = 1
        while f"idea-{n:03d}" in existing:
            n += 1
        return f"idea-{n:03d}"

    def _atomic_update(self, updater) -> dict:
        """Lock file, read, apply updater function, write back, return result."""
        with self._lock:
            data = self._read()
            result = updater(data)
            self._write(data)
            return result

    def add(self, description, source="original", category="general",
            priority=5, gpu_hint="auto"):
        def _do(data):
            idea = {
                "id": self._next_id(data),
                "description": description,
                "source": source,
                "category": category,
                "priority": priority,
                "status": "pending",
                "gpu_hint": gpu_hint,
                "claimed_by": None,
                "assigned_experiment": None,
                "result": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            data["ideas"].append(idea)
            return idea
        return self._atomic_update(_do)

    def claim_idea(self, worker_id):
        """Atomically claim the highest-priority pending idea."""
        with self._lock:
            data = self._read()
            pending = [i for i in data["ideas"] if i["status"] == "pending"]
            pending.sort(key=lambda x: x["priority"])
            if not pending:
                return None
            target = pending[0]
            for idea in data["ideas"]:
                if idea["id"] == target["id"]:
                    idea["status"] = "running"
                    idea["claimed_by"] = worker_id
                    break
            self._write(data)
            return target

    # Keep all other methods (list_by_status, all_ideas, update_status,
    # mark_done, delete, update_priority, summary) using self._atomic_update
    # exactly as before, just remove fcntl references.
```

Remove `import fcntl` entirely.

**Step 4: Run all idea_pool tests**

Run: `pytest tests/test_idea_pool.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/open_researcher/idea_pool.py tests/test_idea_pool.py
git commit -m "refactor: migrate idea_pool from fcntl to filelock for cross-platform support"
```

---

### Task D3: Migrate activity.py from fcntl to filelock + atomic update

**Files:**
- Modify: `src/open_researcher/activity.py`
- Test: `tests/test_activity.py`

**Step 1: Write concurrency test**

Add to `tests/test_activity.py`:

```python
import threading

def test_concurrent_updates(tmp_path):
    """Multiple threads updating different keys should not lose data."""
    research = tmp_path
    (research / "activity.json").write_text("{}")

    monitor = ActivityMonitor(research)
    errors = []

    def update(key):
        try:
            monitor.update(key, status="running", detail=f"doing {key}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=update, args=(f"agent-{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    all_data = monitor.get_all()
    assert len(all_data) == 10
```

**Step 2: Rewrite activity.py with filelock + atomic read-modify-write**

```python
"""Activity monitor — track real-time agent status via activity.json."""

import json
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock


class ActivityMonitor:
    """Read/write activity.json for agent status tracking."""

    def __init__(self, research_dir: Path):
        self.path = research_dir / "activity.json"
        self._lock = FileLock(str(self.path) + ".lock")

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def update(self, agent_key: str, **kwargs) -> None:
        with self._lock:
            data = self._read()
            entry = data.get(agent_key, {})
            entry.update(kwargs)
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            data[agent_key] = entry
            self._write(data)

    def get(self, agent_key: str) -> dict | None:
        with self._lock:
            data = self._read()
            return data.get(agent_key)

    def update_worker(self, agent_key: str, worker_id: str, **kwargs) -> None:
        with self._lock:
            data = self._read()
            entry = data.get(agent_key, {})
            workers = entry.get("workers", [])
            found = False
            for w in workers:
                if w["id"] == worker_id:
                    w.update(kwargs)
                    w["updated_at"] = datetime.now(timezone.utc).isoformat()
                    found = True
                    break
            if not found:
                worker = {"id": worker_id, **kwargs,
                          "updated_at": datetime.now(timezone.utc).isoformat()}
                workers.append(worker)
            entry["workers"] = workers
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            data[agent_key] = entry
            self._write(data)

    def remove_worker(self, agent_key: str, worker_id: str) -> None:
        with self._lock:
            data = self._read()
            entry = data.get(agent_key, {})
            workers = entry.get("workers", [])
            entry["workers"] = [w for w in workers if w["id"] != worker_id]
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            data[agent_key] = entry
            self._write(data)

    def get_all(self) -> dict:
        with self._lock:
            return self._read()
```

**Step 3: Run tests**

Run: `pytest tests/test_activity.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/open_researcher/activity.py tests/test_activity.py
git commit -m "refactor: migrate activity from fcntl to filelock with atomic updates"
```

---

### Task D4: Add filelock to GPUManager

**Files:**
- Modify: `src/open_researcher/gpu_manager.py`
- Test: `tests/test_gpu_manager.py`

**Step 1: Add FileLock to GPUManager**

Add `from filelock import FileLock` and `self._lock = FileLock(str(status_file) + ".lock")` in `__init__`. Wrap `_read`+`_write` sequences in `allocate()`, `allocate_group()`, `release()`, `release_group()`, `refresh()` with `with self._lock:`.

**Step 2: Run tests**

Run: `pytest tests/test_gpu_manager.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/open_researcher/gpu_manager.py
git commit -m "fix: add file locking to GPUManager for concurrent safety"
```

---

### Task D5: Harden status_cmd.py against bad data

**Files:**
- Modify: `src/open_researcher/status_cmd.py:85-101,160-165`
- Test: `tests/test_status.py`

**Step 1: Write bad data test**

Add to `tests/test_status.py`:

```python
def test_parse_state_with_corrupt_metric(tmp_path):
    """Should not crash on non-numeric metric values."""
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text(
        "mode: autonomous\nmetrics:\n  primary:\n    name: acc\n    direction: higher_is_better\n"
    )
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        "2026-03-08T10:00:00\ta1b2c3d\tacc\tNaN\t{}\tkeep\tbaseline\n"
        "2026-03-08T11:00:00\tb2c3d4e\tacc\tcorrupt\t{}\tkeep\texp1\n"
    )
    state = parse_research_state(tmp_path)
    # Should not crash — values may be None or partial
    assert state["total"] == 2


def test_parse_state_with_missing_fields(tmp_path):
    """Should handle TSV rows with missing columns."""
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text(
        "mode: autonomous\nmetrics:\n  primary:\n    name: acc\n    direction: higher_is_better\n"
    )
    # Row with only 3 fields instead of 7
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        "2026-03-08\ta1b\tacc\n"
    )
    state = parse_research_state(tmp_path)
    assert state["total"] >= 0  # Should not crash
```

**Step 2: Run tests, verify they FAIL**

Run: `pytest tests/test_status.py::test_parse_state_with_corrupt_metric tests/test_status.py::test_parse_state_with_missing_fields -v`

**Step 3: Fix parse_research_state**

In `status_cmd.py`, wrap metric parsing in try/except:

```python
# Replace lines ~85-101 with safe parsing:
state["total"] = len(rows)
state["keep"] = sum(1 for r in rows if r.get("status") == "keep")
state["discard"] = sum(1 for r in rows if r.get("status") == "discard")
state["crash"] = sum(1 for r in rows if r.get("status") == "crash")
state["recent"] = rows[-5:] if rows else []

higher = state["direction"] == "higher_is_better"
keep_rows = [r for r in rows if r.get("status") == "keep"]
values = []
for r in keep_rows:
    try:
        v = float(r.get("metric_value", ""))
        if v == v:  # filter NaN
            values.append(v)
    except (ValueError, TypeError):
        continue

if values:
    state["baseline_value"] = values[0]
    state["current_value"] = values[-1]
    state["best_value"] = max(values) if higher else min(values)
else:
    state["baseline_value"] = None
    state["current_value"] = None
    state["best_value"] = None
```

Similarly fix `print_status` around line 160-165 to use safe float conversion.

**Step 4: Run tests, verify PASS**

Run: `pytest tests/test_status.py -v`

**Step 5: Commit**

```bash
git add src/open_researcher/status_cmd.py tests/test_status.py
git commit -m "fix: harden status_cmd against corrupt/missing metric data"
```

---

### Task D6: Harden results_cmd.py and export_cmd.py

**Files:**
- Modify: `src/open_researcher/results_cmd.py:42-53`
- Modify: `src/open_researcher/export_cmd.py`
- Test: `tests/test_results.py`, `tests/test_export.py`

**Step 1: Write bad data test for results**

```python
def test_print_results_with_missing_fields(tmp_path, capsys):
    """Should not crash when TSV has missing fields."""
    research = tmp_path / ".research"
    research.mkdir()
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        "2026-03-08\ta1b\n"
    )
    # Should not raise
    from open_researcher.results_cmd import print_results
    try:
        print_results(tmp_path)
    except (KeyError, SystemExit):
        pass  # SystemExit(1) is OK for missing .research
```

**Step 2: Fix results_cmd.py — use .get() with defaults**

Replace direct `row["field"]` with `row.get("field", "<missing>")`.

**Step 3: Add `--output` to export_cmd.py and handle missing config**

Add graceful fallback when config.yaml is missing. Add `--output` option.

**Step 4: Run tests**

Run: `pytest tests/test_results.py tests/test_export.py -v`

**Step 5: Commit**

```bash
git add src/open_researcher/results_cmd.py src/open_researcher/export_cmd.py tests/test_results.py tests/test_export.py
git commit -m "fix: harden results and export commands against bad data"
```

---

### Task D7: Add git repo validation to init_cmd.py

**Files:**
- Modify: `src/open_researcher/init_cmd.py:14-18`
- Test: `tests/test_init.py`

**Step 1: Write test**

```python
def test_init_fails_without_git(tmp_path):
    """init should fail if not in a git repo."""
    import os
    os.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0
    assert "git" in result.output.lower()
```

**Step 2: Add git check at top of do_init**

```python
# At the start of do_init, before .research check:
git_dir = repo_path / ".git"
if not git_dir.exists():
    print("[ERROR] Not a git repository. Run 'git init' first.", file=sys.stderr)
    raise SystemExit(1)
```

**Step 3: Run tests**

Run: `pytest tests/test_init.py -v`

**Step 4: Commit**

```bash
git add src/open_researcher/init_cmd.py tests/test_init.py
git commit -m "fix: validate git repo before init"
```

---

### Task D8: Fix _has_pending_ideas to use IdeaPool

**Files:**
- Modify: `src/open_researcher/run_cmd.py:39-48`

**Step 1: Replace raw JSON read with IdeaPool.summary()**

```python
def _has_pending_ideas(research_dir: Path) -> bool:
    """Check if idea_pool.json has any pending ideas (thread-safe)."""
    from open_researcher.idea_pool import IdeaPool
    pool = IdeaPool(research_dir / "idea_pool.json")
    return pool.summary().get("pending", 0) > 0
```

**Step 2: Run tests**

Run: `pytest tests/test_run.py -v`

**Step 3: Commit**

```bash
git add src/open_researcher/run_cmd.py
git commit -m "fix: use IdeaPool for thread-safe pending idea check"
```

---

## Module C: Runtime Controls

> Merge after D. Implements timeout, crash counter, collaborative mode, parallel workers.

### Task C1: Implement config reader utility

**Files:**
- Create: `src/open_researcher/config.py`
- Test: `tests/test_config.py`

**Step 1: Write test**

```python
from open_researcher.config import load_config

def test_load_config(tmp_path):
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text(
        "mode: collaborative\nexperiment:\n  timeout: 300\n  max_consecutive_crashes: 5\n"
    )
    cfg = load_config(research)
    assert cfg.mode == "collaborative"
    assert cfg.timeout == 300
    assert cfg.max_crashes == 5

def test_load_config_defaults(tmp_path):
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text("mode: autonomous\n")
    cfg = load_config(research)
    assert cfg.timeout == 600
    assert cfg.max_crashes == 3
    assert cfg.max_workers == 0
```

**Step 2: Implement config.py**

```python
"""Typed config reader for .research/config.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ResearchConfig:
    mode: str = "autonomous"
    timeout: int = 600
    max_crashes: int = 3
    max_workers: int = 0
    worker_agent: str = ""
    primary_metric: str = ""
    direction: str = ""
    web_search: bool = True
    search_interval: int = 5
    remote_hosts: list = None

    def __post_init__(self):
        if self.remote_hosts is None:
            self.remote_hosts = []


def load_config(research_dir: Path) -> ResearchConfig:
    """Load and parse config.yaml into a typed dataclass."""
    config_path = research_dir / "config.yaml"
    if not config_path.exists():
        return ResearchConfig()
    raw = yaml.safe_load(config_path.read_text()) or {}
    exp = raw.get("experiment", {})
    metrics = raw.get("metrics", {}).get("primary", {})
    gpu = raw.get("gpu", {})
    research = raw.get("research", {})
    return ResearchConfig(
        mode=raw.get("mode", "autonomous"),
        timeout=exp.get("timeout", 600),
        max_crashes=exp.get("max_consecutive_crashes", 3),
        max_workers=exp.get("max_parallel_workers", 0),
        worker_agent=exp.get("worker_agent", ""),
        primary_metric=metrics.get("name", ""),
        direction=metrics.get("direction", ""),
        web_search=research.get("web_search", True),
        search_interval=research.get("search_interval", 5),
        remote_hosts=gpu.get("remote_hosts", []),
    )
```

**Step 3: Run tests**

Run: `pytest tests/test_config.py -v`

**Step 4: Commit**

```bash
git add src/open_researcher/config.py tests/test_config.py
git commit -m "feat: add typed config reader for runtime controls"
```

---

### Task C2: Implement timeout watchdog

**Files:**
- Create: `src/open_researcher/watchdog.py`
- Test: `tests/test_watchdog.py`

**Step 1: Write test**

```python
import threading
import time
from unittest.mock import MagicMock

from open_researcher.watchdog import TimeoutWatchdog

def test_watchdog_fires_on_timeout():
    callback = MagicMock()
    wd = TimeoutWatchdog(timeout_seconds=0.5, on_timeout=callback)
    wd.start()
    time.sleep(1.0)
    wd.stop()
    callback.assert_called_once()

def test_watchdog_reset_prevents_timeout():
    callback = MagicMock()
    wd = TimeoutWatchdog(timeout_seconds=0.5, on_timeout=callback)
    wd.start()
    time.sleep(0.3)
    wd.reset()
    time.sleep(0.3)
    wd.stop()
    callback.assert_not_called()
```

**Step 2: Implement watchdog.py**

```python
"""Timeout watchdog — kill agent if experiment exceeds time limit."""

import threading
from typing import Callable


class TimeoutWatchdog:
    """Resettable watchdog timer that fires a callback on timeout."""

    def __init__(self, timeout_seconds: int, on_timeout: Callable[[], None]):
        self.timeout = timeout_seconds
        self.on_timeout = on_timeout
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self._cancel_timer()
            self._timer = threading.Timer(self.timeout, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def reset(self) -> None:
        self.start()

    def stop(self) -> None:
        with self._lock:
            self._cancel_timer()

    def _fire(self) -> None:
        self.on_timeout()

    def _cancel_timer(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
```

**Step 3: Run tests**

Run: `pytest tests/test_watchdog.py -v`

**Step 4: Commit**

```bash
git add src/open_researcher/watchdog.py tests/test_watchdog.py
git commit -m "feat: add timeout watchdog for experiment time limits"
```

---

### Task C3: Implement crash counter

**Files:**
- Create: `src/open_researcher/crash_counter.py`
- Test: `tests/test_crash_counter.py`

**Step 1: Write test**

```python
from open_researcher.crash_counter import CrashCounter

def test_crash_counter_triggers_at_limit():
    cc = CrashCounter(max_crashes=3)
    assert not cc.record("keep")
    assert not cc.record("crash")
    assert not cc.record("crash")
    assert cc.record("crash")  # 3rd consecutive crash

def test_crash_counter_resets_on_success():
    cc = CrashCounter(max_crashes=3)
    cc.record("crash")
    cc.record("crash")
    cc.record("keep")  # resets
    assert not cc.record("crash")
    assert not cc.record("crash")
    assert cc.record("crash")  # 3rd again
```

**Step 2: Implement crash_counter.py**

```python
"""Crash counter — pause experiments after N consecutive crashes."""


class CrashCounter:
    """Track consecutive crashes and signal when limit is reached."""

    def __init__(self, max_crashes: int = 3):
        self.max_crashes = max_crashes
        self.consecutive = 0

    def record(self, status: str) -> bool:
        """Record an experiment result. Returns True if limit reached."""
        if status == "crash":
            self.consecutive += 1
            return self.consecutive >= self.max_crashes
        else:
            self.consecutive = 0
            return False

    def reset(self) -> None:
        self.consecutive = 0
```

**Step 3: Run tests**

Run: `pytest tests/test_crash_counter.py -v`

**Step 4: Commit**

```bash
git add src/open_researcher/crash_counter.py tests/test_crash_counter.py
git commit -m "feat: add crash counter for consecutive crash detection"
```

---

### Task C4: Implement collaborative mode phase gate

**Files:**
- Create: `src/open_researcher/phase_gate.py`
- Test: `tests/test_phase_gate.py`

**Step 1: Write test**

```python
import json
from open_researcher.phase_gate import PhaseGate

def test_phase_gate_detects_transition(tmp_path):
    research = tmp_path
    progress = research / "experiment_progress.json"
    control = research / "control.json"
    progress.write_text(json.dumps({"phase": "understand"}))
    control.write_text(json.dumps({"paused": False, "skip_current": False}))

    gate = PhaseGate(research, mode="collaborative")
    # Simulate phase change
    progress.write_text(json.dumps({"phase": "evaluate"}))
    gate.check()

    ctrl = json.loads(control.read_text())
    assert ctrl["paused"] is True

def test_phase_gate_noop_in_autonomous(tmp_path):
    research = tmp_path
    progress = research / "experiment_progress.json"
    control = research / "control.json"
    progress.write_text(json.dumps({"phase": "understand"}))
    control.write_text(json.dumps({"paused": False, "skip_current": False}))

    gate = PhaseGate(research, mode="autonomous")
    progress.write_text(json.dumps({"phase": "evaluate"}))
    gate.check()

    ctrl = json.loads(control.read_text())
    assert ctrl["paused"] is False
```

**Step 2: Implement phase_gate.py**

```python
"""Phase gate — pause for human review in collaborative mode."""

import json
from pathlib import Path


class PhaseGate:
    """Monitor phase transitions and auto-pause in collaborative mode."""

    def __init__(self, research_dir: Path, mode: str = "autonomous"):
        self.research_dir = research_dir
        self.mode = mode
        self._last_phase = self._read_phase()

    def _read_phase(self) -> str:
        path = self.research_dir / "experiment_progress.json"
        if not path.exists():
            return "init"
        try:
            return json.loads(path.read_text()).get("phase", "init")
        except (json.JSONDecodeError, OSError):
            return "init"

    def check(self) -> str | None:
        """Check for phase transition. Returns new phase name if paused, else None."""
        current = self._read_phase()
        if current != self._last_phase:
            self._last_phase = current
            if self.mode == "collaborative":
                self._pause(current)
                return current
        return None

    def _pause(self, phase: str) -> None:
        ctrl_path = self.research_dir / "control.json"
        try:
            ctrl = json.loads(ctrl_path.read_text())
        except (json.JSONDecodeError, OSError):
            ctrl = {}
        ctrl["paused"] = True
        ctrl["pause_reason"] = f"Phase completed: {phase}"
        ctrl_path.write_text(json.dumps(ctrl, indent=2))
```

**Step 3: Run tests**

Run: `pytest tests/test_phase_gate.py -v`

**Step 4: Commit**

```bash
git add src/open_researcher/phase_gate.py tests/test_phase_gate.py
git commit -m "feat: add phase gate for collaborative mode"
```

---

### Task C5: Integrate watchdog + crash counter + phase gate into run_cmd.py

**Files:**
- Modify: `src/open_researcher/run_cmd.py`
- Test: `tests/test_run.py`

**Step 1: Write integration test**

```python
def test_run_multi_stops_on_consecutive_crashes(tmp_path):
    """Should pause after max_consecutive_crashes."""
    # Setup .research with crash limit = 2
    repo = tmp_path
    _setup_research_dir(repo)
    research = repo / ".research"
    (research / "config.yaml").write_text(
        "mode: autonomous\nexperiment:\n  max_consecutive_crashes: 2\n"
        "metrics:\n  primary:\n    name: acc\n    direction: higher_is_better\n"
    )
    # ... (mock agents that produce crashes)
```

**Step 2: Integrate into run_cmd.py**

In `do_run` and `do_run_multi`:
- Load config with `load_config(research)`
- Create `TimeoutWatchdog(cfg.timeout, on_timeout=terminate_agent)`
- Create `CrashCounter(cfg.max_crashes)`
- Create `PhaseGate(research, cfg.mode)`
- After each agent run, check crash counter and phase gate
- Watchdog resets on each new experiment start

**Step 3: Run tests**

Run: `pytest tests/test_run.py -v`

**Step 4: Commit**

```bash
git add src/open_researcher/run_cmd.py tests/test_run.py
git commit -m "feat: integrate timeout, crash counter, and collaborative mode into run"
```

---

### Task C6: Implement parallel workers

**Files:**
- Create: `src/open_researcher/worker.py`
- Modify: `src/open_researcher/run_cmd.py`
- Test: `tests/test_worker.py`

**Step 1: Write worker test**

```python
from open_researcher.worker import WorkerManager

def test_worker_manager_creates_worktrees(tmp_path):
    """Should create N worktrees for N workers."""
    # ... test worktree creation
```

**Step 2: Implement worker.py**

```python
"""Parallel worker manager — run experiments across multiple GPUs."""

import subprocess
import threading
from pathlib import Path

from open_researcher.gpu_manager import GPUManager
from open_researcher.idea_pool import IdeaPool


class WorkerManager:
    """Orchestrate parallel experiment workers."""

    def __init__(self, repo_path, research_dir, gpu_manager, idea_pool,
                 agent_factory, max_workers, on_output):
        self.repo_path = repo_path
        self.research_dir = research_dir
        self.gpu_manager = gpu_manager
        self.idea_pool = idea_pool
        self.agent_factory = agent_factory
        self.max_workers = max_workers
        self.on_output = on_output
        self._workers = []
        self._stop = threading.Event()

    def start(self):
        gpus = self.gpu_manager.refresh()
        available = [g for g in gpus if g["allocated_to"] is None]
        n = min(self.max_workers or len(available), len(available)) or 1
        for i in range(n):
            t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            t.start()
            self._workers.append(t)

    def stop(self):
        self._stop.set()

    def _worker_loop(self, worker_id):
        wid = f"worker-{worker_id}"
        while not self._stop.is_set():
            idea = self.idea_pool.claim_idea(wid)
            if not idea:
                break
            # Create worktree, run experiment, merge or discard
            self.on_output(f"[{wid}] Claimed: {idea['description'][:50]}")
            # ... implementation
```

**Step 3: Integrate into run_cmd.py when max_workers > 1**

**Step 4: Run tests**

Run: `pytest tests/test_worker.py -v`

**Step 5: Commit**

```bash
git add src/open_researcher/worker.py tests/test_worker.py src/open_researcher/run_cmd.py
git commit -m "feat: add parallel worker orchestration for multi-GPU experiments"
```

---

## Module B: CLI Charts + Subcommands

> Merge after C. New files only, minimal changes to existing code.

### Task B1: Add plotext dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add plotext**

```python
dependencies = [
    ...
    "plotext>=5.3.0",
]
```

**Step 2: Install**

Run: `pip install -e ".[dev]"`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add plotext dependency for terminal charts"
```

---

### Task B2: Implement results --chart and --json

**Files:**
- Modify: `src/open_researcher/results_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Test: `tests/test_results.py`

**Step 1: Write test**

```python
def test_results_json(tmp_path, capsys):
    research = tmp_path / ".research"
    research.mkdir()
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        "2026-03-08T10:00:00\ta1b\tacc\t0.85\t{}\tkeep\tbaseline\n"
    )
    from open_researcher.results_cmd import print_results_json
    print_results_json(tmp_path)
    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["status"] == "keep"
```

**Step 2: Add chart and json functions to results_cmd.py**

```python
import json as json_mod
import plotext as plt

def print_results_chart(repo_path: Path, metric: str | None = None,
                         last: int | None = None) -> None:
    rows = load_results(repo_path)
    if not rows:
        print("No results to chart.")
        return
    if last:
        rows = rows[-last:]

    config_path = repo_path / ".research" / "config.yaml"
    cfg = yaml.safe_load(config_path.read_text()) or {}
    primary = cfg.get("metrics", {}).get("primary", {})
    metric_name = metric or primary.get("name", "metric")

    values = []
    colors = []
    for r in rows:
        try:
            values.append(float(r.get("metric_value", 0)))
        except (ValueError, TypeError):
            values.append(0)
        status = r.get("status", "")
        if status == "keep":
            colors.append("green")
        elif status == "discard":
            colors.append("red")
        else:
            colors.append("yellow")

    x = list(range(1, len(values) + 1))
    plt.clear_figure()
    plt.plot(x, values, marker="braille")
    plt.scatter(x, values, color=colors)
    if values:
        plt.hline(values[0], color="blue")  # baseline
        best = max(values) if primary.get("direction") == "higher_is_better" else min(values)
        plt.hline(best, color="cyan")  # best
    plt.title(f"{metric_name} over experiments")
    plt.xlabel("Experiment #")
    plt.ylabel(metric_name)
    plt.show()


def print_results_json(repo_path: Path) -> None:
    rows = load_results(repo_path)
    print(json_mod.dumps(rows, indent=2))
```

**Step 3: Update cli.py results command**

```python
@app.command()
def results(
    chart: str = typer.Option(None, "--chart", help="Show chart for metric (default: primary)"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON"),
    last: int = typer.Option(None, "--last", help="Show only last N experiments"),
):
    """Print experiment results table."""
    from open_researcher.results_cmd import print_results, print_results_chart, print_results_json
    if json_out:
        print_results_json(Path.cwd())
    elif chart is not None:
        metric = chart if chart != "" else None
        print_results_chart(Path.cwd(), metric=metric, last=last)
    else:
        print_results(Path.cwd())
```

**Step 4: Run tests**

Run: `pytest tests/test_results.py -v`

**Step 5: Commit**

```bash
git add src/open_researcher/results_cmd.py src/open_researcher/cli.py tests/test_results.py
git commit -m "feat: add results --chart and --json options"
```

---

### Task B3: Implement status --sparkline

**Files:**
- Modify: `src/open_researcher/status_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Test: `tests/test_status.py`

**Step 1: Write test**

```python
def test_sparkline_output(tmp_path, capsys):
    """status --sparkline should include a sparkline character."""
    # Setup research dir with 5 results
    # ...
    from open_researcher.status_cmd import print_status
    print_status(tmp_path, sparkline=True)
    captured = capsys.readouterr()
    # Should contain block characters
    assert any(c in captured.out for c in "▁▂▃▄▅▆▇█")
```

**Step 2: Add sparkline generation**

```python
SPARK_CHARS = "▁▂▃▄▅▆▇█"

def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if lo == hi:
        return SPARK_CHARS[4] * len(values)
    return "".join(
        SPARK_CHARS[min(int((v - lo) / (hi - lo) * 7), 7)]
        for v in values
    )
```

Add sparkline to `print_status` when `sparkline=True`.

**Step 3: Update cli.py**

Add `sparkline: bool = typer.Option(False, "--sparkline")` to status command.

**Step 4: Run tests**

Run: `pytest tests/test_status.py -v`

**Step 5: Commit**

```bash
git add src/open_researcher/status_cmd.py src/open_researcher/cli.py tests/test_status.py
git commit -m "feat: add sparkline to status command"
```

---

### Task B4: Implement doctor command

**Files:**
- Create: `src/open_researcher/doctor_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Test: `tests/test_doctor.py`

**Step 1: Write test**

```python
def test_doctor_in_valid_repo(tmp_path):
    """doctor should pass all checks in a valid setup."""
    (tmp_path / ".git").mkdir()
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text("mode: autonomous\n")
    (research / "results.tsv").write_text("timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n")
    (research / "idea_pool.json").write_text('{"ideas": []}')
    (research / "activity.json").write_text("{}")

    from open_researcher.doctor_cmd import run_doctor
    results = run_doctor(tmp_path)
    assert all(r["status"] in ("OK", "WARN") for r in results)

def test_doctor_no_git(tmp_path):
    from open_researcher.doctor_cmd import run_doctor
    results = run_doctor(tmp_path)
    git_check = next(r for r in results if "git" in r["check"].lower())
    assert git_check["status"] == "FAIL"
```

**Step 2: Implement doctor_cmd.py**

```python
"""Doctor command — preflight health checks."""

import json
import shutil
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table


def run_doctor(repo_path: Path) -> list[dict]:
    """Run all health checks, return list of {check, status, detail}."""
    checks = []

    # 1. Git repo
    git_ok = (repo_path / ".git").exists()
    checks.append({"check": "Git repository", "status": "OK" if git_ok else "FAIL",
                    "detail": "" if git_ok else "Not a git repo — run 'git init'"})

    # 2. .research/ exists
    research = repo_path / ".research"
    r_ok = research.is_dir()
    checks.append({"check": ".research/ directory", "status": "OK" if r_ok else "FAIL",
                    "detail": "" if r_ok else "Run 'open-researcher init' first"})

    if r_ok:
        # 3. config.yaml
        cfg_path = research / "config.yaml"
        try:
            yaml.safe_load(cfg_path.read_text())
            checks.append({"check": "config.yaml", "status": "OK", "detail": ""})
        except Exception as e:
            checks.append({"check": "config.yaml", "status": "FAIL", "detail": str(e)})

        # 4. results.tsv
        tsv = research / "results.tsv"
        checks.append({"check": "results.tsv", "status": "OK" if tsv.exists() else "WARN",
                        "detail": "" if tsv.exists() else "Missing — will be created on first experiment"})

        # 5. idea_pool.json
        pool = research / "idea_pool.json"
        try:
            json.loads(pool.read_text())
            checks.append({"check": "idea_pool.json", "status": "OK", "detail": ""})
        except Exception:
            checks.append({"check": "idea_pool.json", "status": "WARN", "detail": "Missing or corrupt"})

        # 6. activity.json
        act = research / "activity.json"
        try:
            json.loads(act.read_text())
            checks.append({"check": "activity.json", "status": "OK", "detail": ""})
        except Exception:
            checks.append({"check": "activity.json", "status": "WARN", "detail": "Missing or corrupt"})

    # 7. Agent binaries
    for agent_name, binary in [("claude-code", "claude"), ("codex", "codex"),
                                ("aider", "aider"), ("opencode", "opencode")]:
        found = shutil.which(binary) is not None
        checks.append({"check": f"Agent: {agent_name}", "status": "OK" if found else "WARN",
                        "detail": "" if found else f"'{binary}' not on PATH"})

    # 8. Python version
    import platform
    py = platform.python_version_tuple()
    py_ok = int(py[0]) >= 3 and int(py[1]) >= 10
    checks.append({"check": "Python >= 3.10", "status": "OK" if py_ok else "FAIL",
                    "detail": f"Found {'.'.join(py)}"})

    return checks


def print_doctor(repo_path: Path) -> None:
    results = run_doctor(repo_path)
    console = Console()
    table = Table(title="Open Researcher Health Check")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    status_style = {"OK": "green", "WARN": "yellow", "FAIL": "red"}
    for r in results:
        table.add_row(r["check"], r["status"], r["detail"],
                       style=status_style.get(r["status"], ""))
    console.print(table)

    fails = sum(1 for r in results if r["status"] == "FAIL")
    if fails:
        console.print(f"\n[red]{fails} check(s) failed.[/red]")
        raise SystemExit(1)
```

**Step 3: Add to cli.py**

```python
@app.command()
def doctor():
    """Run health checks on the research environment."""
    from open_researcher.doctor_cmd import print_doctor
    print_doctor(Path.cwd())
```

**Step 4: Run tests**

Run: `pytest tests/test_doctor.py -v`

**Step 5: Commit**

```bash
git add src/open_researcher/doctor_cmd.py src/open_researcher/cli.py tests/test_doctor.py
git commit -m "feat: add doctor command for preflight checks"
```

---

### Task B5: Implement ideas subcommand

**Files:**
- Create: `src/open_researcher/ideas_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Test: `tests/test_ideas_cmd.py`

**Step 1-5:** Create `ideas_app = typer.Typer()` with list/add/edit/delete/prioritize subcommands. Each delegates to `IdeaPool`. Add `app.add_typer(ideas_app, name="ideas")` in cli.py. Write tests for each subcommand.

**Commit:** `feat: add ideas CLI subcommand for pool management`

---

### Task B6: Implement config subcommand

**Files:**
- Create: `src/open_researcher/config_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Test: `tests/test_config_cmd.py`

**Step 1-5:** Create `config_app = typer.Typer()` with show/set/validate. show prints formatted config, set updates yaml, validate checks required fields.

**Commit:** `feat: add config CLI subcommand`

---

### Task B7: Implement logs subcommand

**Files:**
- Create: `src/open_researcher/logs_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Test: `tests/test_logs_cmd.py`

**Step 1-5:** Create `logs` command with `--follow` (tail -f equivalent), `--agent` filter, `--errors` filter.

**Commit:** `feat: add logs CLI subcommand`

---

## Module A: TUI Multi-View Console

> Merge last. Rewrites tui/ directory.

### Task A1: Add textual-plotext dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add dependency**

```python
dependencies = [
    ...
    "textual-plotext>=1.0.0",
]
```

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add textual-plotext dependency for TUI charts"
```

---

### Task A2: Create TabbedContent layout in app.py

**Files:**
- Modify: `src/open_researcher/tui/app.py`
- Modify: `src/open_researcher/tui/styles.css`

**Step 1: Rewrite compose() to use TabbedContent**

```python
from textual.widgets import TabbedContent, TabPane, RichLog, Markdown

def compose(self) -> ComposeResult:
    yield StatsBar(id="stats-bar")
    with TabbedContent(id="tabs"):
        with TabPane("Overview", id="tab-overview"):
            yield ExperimentStatusPanel(id="exp-status")
            yield RecentExperiments(id="recent-exp")
        with TabPane("Ideas", id="tab-ideas"):
            yield IdeaListPanel(id="idea-list")
        with TabPane("Charts", id="tab-charts"):
            yield MetricChart(id="metric-chart")
        with TabPane("Logs", id="tab-logs"):
            yield RichLog(id="agent-log", wrap=True, markup=True)
        with TabPane("Docs", id="tab-docs"):
            yield DocViewer(id="doc-viewer")
    yield HotkeyBar(id="hotkey-bar")
```

**Step 2: Add Tab switching keybindings**

```python
BINDINGS = [
    ("1", "switch_tab('tab-overview')", "Overview"),
    ("2", "switch_tab('tab-ideas')", "Ideas"),
    ("3", "switch_tab('tab-charts')", "Charts"),
    ("4", "switch_tab('tab-logs')", "Logs"),
    ("5", "switch_tab('tab-docs')", "Docs"),
    # ... existing bindings
]

def action_switch_tab(self, tab_id: str) -> None:
    self.query_one("#tabs", TabbedContent).active = tab_id
```

**Step 3: Update styles.css for tabbed layout**

**Step 4: Run TUI manually to verify**

Run: `python -c "from open_researcher.tui.app import ResearchApp; ResearchApp(Path('.')).run()"`

**Step 5: Commit**

```bash
git add src/open_researcher/tui/app.py src/open_researcher/tui/styles.css
git commit -m "feat: add TabbedContent layout with 5 tabs"
```

---

### Task A3: Implement Charts tab with textual-plotext

**Files:**
- Modify: `src/open_researcher/tui/widgets.py`
- Test: `tests/test_tui.py`

**Step 1: Create MetricChart widget**

```python
from textual_plotext import PlotextPlot

class MetricChart(PlotextPlot):
    """Experiment metric trend chart."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._values = []
        self._statuses = []

    def update_data(self, rows: list[dict]) -> None:
        self._values = []
        self._statuses = []
        for r in rows:
            try:
                self._values.append(float(r.get("metric_value", 0)))
            except (ValueError, TypeError):
                self._values.append(0)
            self._statuses.append(r.get("status", ""))
        self.refresh()

    def on_mount(self) -> None:
        self.replot()

    def replot(self) -> None:
        plt = self.plt
        plt.clear_figure()
        if not self._values:
            plt.title("No experiment data yet")
            self.refresh()
            return

        x = list(range(1, len(self._values) + 1))
        plt.plot(x, self._values, marker="braille")

        # Color scatter points by status
        for status, color in [("keep", "green"), ("discard", "red"), ("crash", "yellow")]:
            sx = [x[i] for i, s in enumerate(self._statuses) if s == status]
            sy = [self._values[i] for i, s in enumerate(self._statuses) if s == status]
            if sx:
                plt.scatter(sx, sy, color=color, marker="dot")

        if self._values:
            plt.hline(self._values[0], color="blue")  # baseline
        plt.title("Primary Metric Trend")
        plt.xlabel("Experiment #")
        self.refresh()
```

**Step 2: Wire into app.py _refresh_data**

```python
# In _refresh_data, add chart refresh:
try:
    rows = load_results(self.repo_path)
    self.query_one("#metric-chart", MetricChart).update_data(rows)
except (NoMatches, Exception):
    pass
```

**Step 3: Run tests**

Run: `pytest tests/test_tui.py -v`

**Step 4: Commit**

```bash
git add src/open_researcher/tui/widgets.py src/open_researcher/tui/app.py tests/test_tui.py
git commit -m "feat: add MetricChart widget with plotext trend visualization"
```

---

### Task A4: Implement Ideas tab with master-detail and filtering

**Files:**
- Modify: `src/open_researcher/tui/widgets.py`
- Test: `tests/test_tui.py`

**Step 1: Create FilterableIdeaList and IdeaDetail widgets**

Add filtering by status/category, detail panel showing full idea info + experiment result.

**Step 2: Add keybindings for filter (f) and enter (detail)**

**Step 3: Test and commit**

```bash
git commit -m "feat: add Ideas tab with filtering and detail view"
```

---

### Task A5: Implement Docs tab

**Files:**
- Modify: `src/open_researcher/tui/widgets.py`

**Step 1: Create DocViewer widget**

```python
from textual.widgets import Markdown, OptionList

class DocViewer(Static):
    """Document viewer for .research/ markdown files."""

    DOC_FILES = [
        "project-understanding.md",
        "literature.md",
        "evaluation.md",
        "ideas.md",
    ]

    def compose(self) -> ComposeResult:
        yield OptionList(*self.DOC_FILES, id="doc-list")
        yield Markdown("Select a document", id="doc-content")
```

**Step 2: Handle selection to load and render markdown**

**Step 3: Commit**

```bash
git commit -m "feat: add Docs tab with markdown viewer"
```

---

### Task A6: Add RecentExperiments widget to Overview tab

**Files:**
- Modify: `src/open_researcher/tui/widgets.py`

**Step 1: Create RecentExperiments widget showing last 5 results with colored status**

**Step 2: Wire into _refresh_data**

**Step 3: Commit**

```bash
git commit -m "feat: add RecentExperiments widget to Overview tab"
```

---

### Task A7: Update Logs tab with search

**Files:**
- Modify: `src/open_researcher/tui/app.py`

**Step 1: Add search input widget above RichLog in Logs tab**

**Step 2: Implement `/` keybinding to focus search input**

**Step 3: Filter log lines by search term**

**Step 4: Commit**

```bash
git commit -m "feat: add search to Logs tab"
```

---

## Final Integration

### Task F1: Update README.md

**Files:**
- Modify: `README.md`

**Step 1:** Replace `dashboard` with TUI dashboard description. Add new commands. Update comparison table. Add platform support note.

**Step 2: Commit**

```bash
git commit -m "docs: update README to match beta feature set"
```

---

### Task F2: Run full test suite

Run: `pytest -v`
Expected: All PASS

---

### Task F3: Bump version to 0.2.0-beta

**Files:**
- Modify: `pyproject.toml:6`

Change `version = "0.1.0"` to `version = "0.2.0b1"`.

```bash
git commit -m "chore: bump version to 0.2.0b1"
```
