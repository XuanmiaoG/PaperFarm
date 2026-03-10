"""Normalize user-facing workflow options into internal runtime selections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from open_researcher.config import ResearchConfig

FrontendMode = Literal["interactive", "headless"]


@dataclass(slots=True)
class WorkflowSelection:
    """Normalized workflow options for CLI entrypoints."""

    frontend_mode: FrontendMode
    primary_agent_name: str | None
    idea_agent_name: str | None
    exp_agent_name: str | None
    use_multi_agent: bool
    workers: int | None
    notices: list[str]


def apply_worker_override(cfg: ResearchConfig, workers: int | None) -> ResearchConfig:
    """Apply a CLI worker override onto the loaded config in place."""
    if workers is not None:
        cfg.max_workers = workers
    return cfg


def build_workflow_selection(
    *,
    agent: str | None,
    mode: str | None = None,
    headless: bool = False,
    workers: int | None = None,
    multi: bool = False,
    idea_agent: str | None = None,
    exp_agent: str | None = None,
) -> WorkflowSelection:
    """Normalize CLI-facing options into a single runtime selection."""
    notices: list[str] = []
    frontend_mode = _normalize_frontend_mode(mode, headless=headless, notices=notices)
    use_multi_agent = _normalize_multi_agent(
        workers=workers,
        multi=multi,
        idea_agent=idea_agent,
        exp_agent=exp_agent,
        notices=notices,
    )
    if workers is not None and workers < 1:
        raise ValueError("`--workers` must be >= 1.")

    if use_multi_agent:
        return WorkflowSelection(
            frontend_mode=frontend_mode,
            primary_agent_name=agent,
            idea_agent_name=idea_agent or agent,
            exp_agent_name=exp_agent or agent,
            use_multi_agent=True,
            workers=workers,
            notices=notices,
        )

    return WorkflowSelection(
        frontend_mode=frontend_mode,
        primary_agent_name=agent,
        idea_agent_name=None,
        exp_agent_name=None,
        use_multi_agent=False,
        workers=workers,
        notices=notices,
    )


def _normalize_frontend_mode(
    mode: str | None,
    *,
    headless: bool,
    notices: list[str],
) -> FrontendMode:
    normalized = str(mode or "interactive").strip().lower()
    if normalized not in {"interactive", "headless"}:
        raise ValueError("`--mode` must be either `interactive` or `headless`.")
    if headless:
        notices.append("`--headless` is deprecated; use `--mode headless`.")
        if normalized == "interactive":
            normalized = "headless"
    return normalized  # type: ignore[return-value]


def _normalize_multi_agent(
    *,
    workers: int | None,
    multi: bool,
    idea_agent: str | None,
    exp_agent: str | None,
    notices: list[str],
) -> bool:
    used_legacy_split_flags = bool(multi or idea_agent or exp_agent)
    if used_legacy_split_flags:
        notices.append(
            "`--multi`, `--idea-agent`, and `--exp-agent` are deprecated; use `--workers` and `--agent`."
        )
    return used_legacy_split_flags or workers is not None
