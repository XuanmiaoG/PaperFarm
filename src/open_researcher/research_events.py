"""Typed events emitted by the core research loop."""

from dataclasses import dataclass
from typing import Callable, Literal, TypeAlias

PhaseName = Literal["init", "scouting", "reviewing", "experimenting", "done"]
LogLevel = Literal["info", "error"]


@dataclass(slots=True)
class SessionStarted:
    goal: str
    max_experiments: int
    repo: str


@dataclass(slots=True)
class ScoutStarted:
    pass


@dataclass(slots=True)
class AgentOutput:
    phase: PhaseName
    detail: str


@dataclass(slots=True)
class ScoutCompleted:
    exit_code: int


@dataclass(slots=True)
class ScoutFailed:
    exit_code: int


@dataclass(slots=True)
class ReviewAutoConfirmed:
    pass


@dataclass(slots=True)
class IdeaCycleStarted:
    cycle: int


@dataclass(slots=True)
class IdeaAgentDone:
    cycle: int
    exit_code: int


@dataclass(slots=True)
class ExperimentStarted:
    experiment_num: int
    max_experiments: int


@dataclass(slots=True)
class ExperimentCompleted:
    experiment_num: int
    exit_code: int


@dataclass(slots=True)
class NoPendingIdeas:
    pass


@dataclass(slots=True)
class LimitReached:
    max_experiments: int


@dataclass(slots=True)
class CrashLimitReached:
    max_crashes: int


@dataclass(slots=True)
class PhaseTransition:
    next_phase: str


@dataclass(slots=True)
class AllIdeasProcessed:
    pass


@dataclass(slots=True)
class SessionCompleted:
    pass


ResearchEvent: TypeAlias = (
    SessionStarted
    | ScoutStarted
    | AgentOutput
    | ScoutCompleted
    | ScoutFailed
    | ReviewAutoConfirmed
    | IdeaCycleStarted
    | IdeaAgentDone
    | ExperimentStarted
    | ExperimentCompleted
    | NoPendingIdeas
    | LimitReached
    | CrashLimitReached
    | PhaseTransition
    | AllIdeasProcessed
    | SessionCompleted
)
EventHandler = Callable[[ResearchEvent], None]


def event_name(event: ResearchEvent) -> str:
    """Return the stable event name used by renderers and logs."""
    if isinstance(event, SessionStarted):
        return "session_started"
    if isinstance(event, ScoutStarted):
        return "scout_started"
    if isinstance(event, AgentOutput):
        return "agent_output"
    if isinstance(event, ScoutCompleted):
        return "scout_completed"
    if isinstance(event, ScoutFailed):
        return "scout_failed"
    if isinstance(event, ReviewAutoConfirmed):
        return "auto_confirmed"
    if isinstance(event, IdeaCycleStarted):
        return "idea_cycle_started"
    if isinstance(event, IdeaAgentDone):
        return "idea_agent_done"
    if isinstance(event, ExperimentStarted):
        return "experiment_started"
    if isinstance(event, ExperimentCompleted):
        return "experiment_completed"
    if isinstance(event, NoPendingIdeas):
        return "no_pending_ideas"
    if isinstance(event, LimitReached):
        return "limit_reached"
    if isinstance(event, CrashLimitReached):
        return "crash_limit"
    if isinstance(event, PhaseTransition):
        return "phase_transition"
    if isinstance(event, AllIdeasProcessed):
        return "all_ideas_processed"
    if isinstance(event, SessionCompleted):
        return "session_completed"
    raise TypeError(f"Unsupported event type: {type(event)!r}")


def event_phase(event: ResearchEvent) -> PhaseName:
    """Return the logical workflow phase for an event."""
    if isinstance(event, SessionStarted):
        return "init"
    if isinstance(event, (ScoutStarted, ScoutCompleted, ScoutFailed)):
        return "scouting"
    if isinstance(event, ReviewAutoConfirmed):
        return "reviewing"
    if isinstance(event, AgentOutput):
        return event.phase
    if isinstance(
        event,
        (
            IdeaCycleStarted,
            IdeaAgentDone,
            ExperimentStarted,
            ExperimentCompleted,
            NoPendingIdeas,
            LimitReached,
            CrashLimitReached,
            PhaseTransition,
        ),
    ):
        return "experimenting"
    if isinstance(event, (AllIdeasProcessed, SessionCompleted)):
        return "done"
    raise TypeError(f"Unsupported event type: {type(event)!r}")


def event_level(event: ResearchEvent) -> LogLevel:
    """Return the default log level for an event."""
    if isinstance(event, (ScoutFailed, CrashLimitReached)):
        return "error"
    return "info"


def event_payload(event: ResearchEvent) -> dict:
    """Return event-specific payload fields for structured renderers."""
    if isinstance(event, SessionStarted):
        return {
            "goal": event.goal,
            "max_experiments": event.max_experiments,
            "repo": event.repo,
        }
    if isinstance(event, AgentOutput):
        return {"detail": event.detail}
    if isinstance(event, ScoutCompleted):
        return {"exit_code": event.exit_code}
    if isinstance(event, ScoutFailed):
        return {"exit_code": event.exit_code}
    if isinstance(event, IdeaCycleStarted):
        return {"cycle": event.cycle}
    if isinstance(event, IdeaAgentDone):
        return {"cycle": event.cycle, "exit_code": event.exit_code}
    if isinstance(event, ExperimentStarted):
        return {
            "experiment_num": event.experiment_num,
            "max_experiments": event.max_experiments,
        }
    if isinstance(event, ExperimentCompleted):
        return {
            "experiment_num": event.experiment_num,
            "exit_code": event.exit_code,
        }
    if isinstance(event, LimitReached):
        return {
            "max_experiments": event.max_experiments,
            "detail": f"Max experiments ({event.max_experiments}) reached",
        }
    if isinstance(event, CrashLimitReached):
        return {
            "max_crashes": event.max_crashes,
            "detail": f"Crash limit ({event.max_crashes}) reached",
        }
    if isinstance(event, PhaseTransition):
        return {"phase": event.next_phase}
    return {}
