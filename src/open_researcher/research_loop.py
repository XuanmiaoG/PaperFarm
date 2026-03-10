"""Core research loop shared by TUI and headless entrypoints."""

from __future__ import annotations

import threading
from pathlib import Path

from open_researcher.config import ResearchConfig
from open_researcher.crash_counter import CrashCounter
from open_researcher.phase_gate import PhaseGate
from open_researcher.research_events import (
    AgentOutput,
    AllIdeasProcessed,
    CrashLimitReached,
    EventHandler,
    ExperimentCompleted,
    ExperimentStarted,
    IdeaAgentDone,
    IdeaCycleStarted,
    LimitReached,
    NoPendingIdeas,
    PhaseTransition,
    ScoutCompleted,
    ScoutFailed,
    ScoutStarted,
)
from open_researcher.watchdog import TimeoutWatchdog


def read_latest_status(research_dir: Path) -> str:
    """Read the latest status from results.tsv (last non-header line)."""
    results_path = research_dir / "results.tsv"
    if not results_path.exists():
        return ""
    try:
        lines = results_path.read_text().strip().splitlines()
        if len(lines) < 2:
            return ""
        parts = lines[-1].split("\t")
        if len(parts) >= 6:
            return parts[5].strip()
        return ""
    except OSError:
        return ""


def set_paused(research_dir: Path, reason: str) -> None:
    """Pause the current research session with a reason."""
    from open_researcher.control_plane import issue_control_command

    issue_control_command(
        research_dir / "control.json",
        command="pause",
        source="watchdog",
        reason=reason,
    )


def has_pending_ideas(research_dir: Path) -> bool:
    """Check whether the idea pool still contains pending ideas."""
    from open_researcher.idea_pool import IdeaBacklog

    pool = IdeaBacklog(research_dir / "idea_pool.json")
    return pool.summary().get("pending", 0) > 0


class ResearchLoop:
    """Run the core Scout -> Idea/Experiment loop and emit typed events."""

    def __init__(
        self,
        repo_path: Path,
        research_dir: Path,
        cfg: ResearchConfig,
        emit: EventHandler,
        *,
        has_pending_ideas_fn=has_pending_ideas,
        read_latest_status_fn=read_latest_status,
        pause_fn=set_paused,
    ):
        self.repo_path = repo_path
        self.research_dir = research_dir
        self.cfg = cfg
        self.emit = emit
        self._has_pending_ideas = has_pending_ideas_fn
        self._read_latest_status = read_latest_status_fn
        self._pause = pause_fn

    def _effective_max_experiments(self, override: int | None = None) -> int:
        if override is not None and override > 0:
            return override
        return self.cfg.max_experiments

    def _make_output_callback(self, phase: str):
        def on_output(line: str) -> None:
            self.emit(AgentOutput(phase=phase, detail=line))

        return on_output

    def _run_agent(self, agent, *, phase: str, program_file: str, error_tag: str) -> int:
        try:
            return agent.run(
                self.repo_path,
                on_output=self._make_output_callback(phase),
                program_file=program_file,
            )
        except Exception as exc:
            self.emit(AgentOutput(phase=phase, detail=f"[{error_tag}] Agent error: {exc}"))
            return 1

    def run_scout(self, agent) -> int:
        """Run the Scout phase once."""
        self.emit(ScoutStarted())
        code = self._run_agent(
            agent,
            phase="scouting",
            program_file="scout_program.md",
            error_tag="scout",
        )
        self.emit(ScoutCompleted(exit_code=code))
        if code != 0:
            self.emit(ScoutFailed(exit_code=code))
        return code

    def run_single_agent(self, agent, *, max_experiments: int | None = None) -> int:
        """Run the single-agent experiment path."""
        effective_max = self._effective_max_experiments(max_experiments)
        watchdog = TimeoutWatchdog(self.cfg.timeout, on_timeout=lambda: agent.terminate())

        self.emit(ExperimentStarted(experiment_num=1, max_experiments=effective_max))
        watchdog.start()
        try:
            code = self._run_agent(
                agent,
                phase="experimenting",
                program_file="program.md",
                error_tag="agent",
            )
        finally:
            watchdog.stop()

        self.emit(ExperimentCompleted(experiment_num=1, exit_code=code))
        return code

    def run_multi_agent(
        self,
        idea_agent,
        exp_agent,
        *,
        stop: threading.Event | None = None,
        max_experiments: int | None = None,
    ) -> dict[str, int]:
        """Run the alternating idea/experiment loop until a stop condition is hit."""
        stop_event = stop or threading.Event()
        effective_max = self._effective_max_experiments(max_experiments)
        crash_counter = CrashCounter(self.cfg.max_crashes)
        phase_gate = PhaseGate(self.research_dir, self.cfg.mode)
        watchdog = TimeoutWatchdog(self.cfg.timeout, on_timeout=lambda: exp_agent.terminate())

        exit_codes: dict[str, int] = {}
        experiments_completed = 0
        cycle = 0
        finished_all = False

        try:
            while not stop_event.is_set():
                cycle += 1
                self.emit(IdeaCycleStarted(cycle=cycle))

                code = self._run_agent(
                    idea_agent,
                    phase="experimenting",
                    program_file="idea_program.md",
                    error_tag="idea",
                )
                exit_codes["idea"] = code
                self.emit(IdeaAgentDone(cycle=cycle, exit_code=code))

                if not self._has_pending_ideas(self.research_dir):
                    self.emit(NoPendingIdeas())
                    finished_all = True
                    break

                while not stop_event.is_set():
                    experiments_completed += 1
                    self.emit(
                        ExperimentStarted(
                            experiment_num=experiments_completed,
                            max_experiments=effective_max,
                        )
                    )

                    watchdog.reset()
                    try:
                        code = self._run_agent(
                            exp_agent,
                            phase="experimenting",
                            program_file="experiment_program.md",
                            error_tag="exp",
                        )
                    finally:
                        watchdog.stop()

                    exit_codes["exp"] = code
                    self.emit(
                        ExperimentCompleted(
                            experiment_num=experiments_completed,
                            exit_code=code,
                        )
                    )

                    if effective_max > 0 and experiments_completed >= effective_max:
                        self.emit(LimitReached(max_experiments=effective_max))
                        return exit_codes

                    status = self._read_latest_status(self.research_dir)
                    if status and crash_counter.record(status):
                        self._pause(
                            self.research_dir,
                            f"Crash limit reached: {self.cfg.max_crashes} consecutive crashes",
                        )
                        self.emit(CrashLimitReached(max_crashes=self.cfg.max_crashes))
                        return exit_codes

                    phase = phase_gate.check()
                    if phase:
                        self.emit(PhaseTransition(next_phase=phase))
                        return exit_codes

                    if not self._has_pending_ideas(self.research_dir):
                        break
        finally:
            watchdog.stop()

        if finished_all:
            self.emit(AllIdeasProcessed())
        return exit_codes
