"""Headless mode — structured JSON Lines logging for CLI-only operation."""

from pathlib import Path

from open_researcher.agent_runtime import resolve_agent
from open_researcher.config import load_config
from open_researcher.event_journal import EventJournal
from open_researcher.parallel_runtime import run_parallel_worker_loop
from open_researcher.research_events import (
    ReviewAutoConfirmed,
    SessionCompleted,
    SessionStarted,
)
from open_researcher.research_loop import (
    ResearchLoop,
)
from open_researcher.research_loop import (
    has_pending_ideas as _has_pending_ideas,
)
from open_researcher.research_loop import (
    read_latest_status as _read_latest_status,
)
from open_researcher.research_loop import (
    set_paused as _set_paused,
)
from open_researcher.workflow_options import apply_worker_override

_resolve_agent = resolve_agent


class HeadlessLogger:
    """Emit structured JSON Lines events to a stream and optional log file."""

    def __init__(self, stream=None, log_path: Path | None = None):
        self._journal = EventJournal(log_path or Path("events.jsonl"), stream=stream)

    def emit(self, level: str, phase: str, event: str, **kwargs) -> None:
        self._journal.emit(level, phase, event, **kwargs)

    def make_output_callback(self, phase: str):
        """Return a callback compatible with agent.run(on_output=...)."""
        def on_output(line: str):
            self.emit("info", phase, "agent_output", detail=line)
        return on_output

    def on_event(self, event) -> None:
        """Render a typed research event as a JSONL record."""
        self._journal.emit_typed(event)

    def close(self):
        self._journal.close()


def do_start_headless(
    repo_path: Path,
    goal: str,
    max_experiments: int = 0,
    agent_name: str | None = None,
    tag: str | None = None,
    multi: bool = False,
    idea_agent_name: str | None = None,
    exp_agent_name: str | None = None,
    workers: int | None = None,
    stream=None,
) -> None:
    """Run the full bootstrap flow without TUI — structured JSON Lines to stdout."""
    from datetime import date

    from open_researcher.run_cmd import do_start_init, render_scout_program

    if tag is None:
        tag = date.today().strftime("%b%d").lower()

    # Phase 0: Bootstrap
    research = do_start_init(repo_path, tag=tag)
    cfg = apply_worker_override(load_config(research), workers)
    use_multi_agent = bool(multi or idea_agent_name or exp_agent_name or workers is not None)

    # Override max_experiments: CLI flag > config > default
    if max_experiments > 0:
        cfg.max_experiments = max_experiments
    effective_max = cfg.max_experiments

    logger = HeadlessLogger(stream=stream, log_path=research / "events.jsonl")
    logger.on_event(
        SessionStarted(
            goal=goal,
            max_experiments=effective_max,
            repo=str(repo_path),
        )
    )

    # Resolve agents
    scout_agent = _resolve_agent(agent_name, cfg.agent_config)
    if use_multi_agent:
        idea_agent = _resolve_agent(idea_agent_name or agent_name, cfg.agent_config)
        exp_agent = _resolve_agent(exp_agent_name or agent_name, cfg.agent_config)
    else:
        idea_agent = None
        exp_agent = None

    try:
        # Phase 1: Goal
        render_scout_program(research, tag=tag, goal=goal)
        (research / "goal.md").write_text(f"# Research Goal\n\n{goal}\n")

        loop = ResearchLoop(
            repo_path,
            research,
            cfg,
            logger.on_event,
            has_pending_ideas_fn=_has_pending_ideas,
            read_latest_status_fn=_read_latest_status,
            pause_fn=_set_paused,
        )

        code = loop.run_scout(scout_agent)
        if code != 0:
            return

        # Phase 3: Auto-confirm (no review in headless)
        logger.on_event(ReviewAutoConfirmed())

        # Phase 4: Experiments
        if use_multi_agent and idea_agent and exp_agent:
            if cfg.max_workers > 1:
                run_parallel_worker_loop(
                    repo_path,
                    research,
                    cfg,
                    idea_agent,
                    exp_agent,
                    logger.make_output_callback("experimenting"),
                )
            else:
                loop.run_multi_agent(idea_agent, exp_agent, max_experiments=effective_max)
        else:
            loop.run_single_agent(scout_agent, max_experiments=effective_max)

        logger.on_event(SessionCompleted())
    finally:
        scout_agent.terminate()
        if idea_agent:
            idea_agent.terminate()
        if exp_agent:
            exp_agent.terminate()
        logger.close()
