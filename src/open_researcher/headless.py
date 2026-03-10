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

    from open_researcher.start_cmd import do_start_init, render_scout_program

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
