"""TUI renderer for typed research loop events."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from open_researcher.event_journal import EventJournal
from open_researcher.log_output import make_safe_output
from open_researcher.research_events import (
    AgentOutput,
    AllIdeasProcessed,
    CrashLimitReached,
    ExperimentStarted,
    IdeaAgentDone,
    IdeaCycleStarted,
    LimitReached,
    NoPendingIdeas,
    PhaseTransition,
    ResearchEvent,
    ScoutStarted,
)

if TYPE_CHECKING:
    from open_researcher.tui.app import ResearchApp


class TUIEventRenderer:
    """Render typed research events into the existing unified TUI log."""

    def __init__(self, app: "ResearchApp", research_dir: Path):
        self._app = app
        self._safe_output = make_safe_output(app.append_log, research_dir / "run.log")
        self._journal = EventJournal(research_dir / "events.jsonl")

    def close(self) -> None:
        if hasattr(self._safe_output, "close"):
            self._safe_output.close()
        self._journal.close()

    def make_output_callback(self, phase: str):
        def on_output(line: str) -> None:
            self.on_event(AgentOutput(phase=phase, detail=line))

        return on_output

    def _set_phase(self, phase: str) -> None:
        try:
            self._app.call_from_thread(setattr, self._app, "app_phase", phase)
        except RuntimeError:
            pass

    def on_event(self, event: ResearchEvent) -> None:
        self._journal.emit_typed(event)

        if isinstance(event, AgentOutput):
            self._safe_output(event.detail)
            return

        if isinstance(event, ScoutStarted):
            self._set_phase("scouting")
            return

        if isinstance(event, IdeaCycleStarted):
            self._set_phase("experimenting")
            self._safe_output(f"[system] === Cycle {event.cycle}: Starting Idea Agent ===")
            return

        if isinstance(event, IdeaAgentDone):
            self._safe_output(f"[system] Idea Agent done (code={event.exit_code}).")
            return

        if isinstance(event, ExperimentStarted):
            self._set_phase("experimenting")
            self._safe_output(f"[exp] Starting experiment agent (run #{event.experiment_num})...")
            return

        if isinstance(event, NoPendingIdeas):
            self._safe_output("[system] No pending ideas. Stopping.")
            return

        if isinstance(event, LimitReached):
            self._safe_output(f"[system] Max experiments ({event.max_experiments}) reached. Stopping.")
            return

        if isinstance(event, CrashLimitReached):
            self._safe_output(
                f"[system] Crash limit reached ({event.max_crashes} consecutive crashes). Pausing."
            )
            return

        if isinstance(event, PhaseTransition):
            self._safe_output(f"[system] Phase transition to '{event.next_phase}' — pausing for review.")
            return

        if isinstance(event, AllIdeasProcessed):
            self._safe_output("[system] All cycles finished.")
