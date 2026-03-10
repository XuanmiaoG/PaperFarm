"""Advanced parallel worker runtime for multi-GPU experiment execution."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from open_researcher.agents import get_agent
from open_researcher.config import ResearchConfig
from open_researcher.failure_memory import FailureMemoryLedger
from open_researcher.gpu_manager import GPUManager
from open_researcher.research_loop import has_pending_ideas
from open_researcher.watchdog import TimeoutWatchdog
from open_researcher.worker_plugins import (
    FailureMemoryPlugin,
    GPUAllocatorPlugin,
    WorkerRuntimePlugins,
    WorktreeIsolationPlugin,
)


@dataclass(slots=True)
class ParallelRuntimeProfile:
    """Explicit advanced runtime feature selection for parallel workers."""

    name: str
    gpu_allocation: bool
    failure_memory: bool
    worktree_isolation: bool


def resolve_parallel_runtime_profile(cfg: ResearchConfig) -> ParallelRuntimeProfile:
    """Resolve which advanced runtime plugins are enabled for parallel execution."""
    enabled = [
        cfg.enable_gpu_allocation,
        cfg.enable_failure_memory,
        cfg.enable_worktree_isolation,
    ]
    if all(enabled):
        name = "advanced"
    elif any(enabled):
        name = "custom"
    else:
        name = "minimal"
    return ParallelRuntimeProfile(
        name=name,
        gpu_allocation=cfg.enable_gpu_allocation,
        failure_memory=cfg.enable_failure_memory,
        worktree_isolation=cfg.enable_worktree_isolation,
    )


def build_parallel_worker_plugins(
    repo_path: Path,
    research_dir: Path,
    cfg: ResearchConfig,
) -> tuple[ParallelRuntimeProfile, WorkerRuntimePlugins]:
    """Build the concrete worker plugin bundle for the chosen runtime profile."""
    profile = resolve_parallel_runtime_profile(cfg)
    plugins = WorkerRuntimePlugins(
        gpu_allocator=GPUAllocatorPlugin(GPUManager(research_dir / "gpu_status.json", cfg.remote_hosts))
        if profile.gpu_allocation
        else None,
        failure_memory=FailureMemoryPlugin(
            FailureMemoryLedger(research_dir / "failure_memory_ledger.json")
        )
        if profile.failure_memory
        else None,
        workspace_isolation=WorktreeIsolationPlugin(repo_path)
        if profile.worktree_isolation
        else None,
    )
    return profile, plugins


def run_parallel_worker_loop(
    repo_path: Path,
    research_dir: Path,
    cfg: ResearchConfig,
    idea_agent,
    exp_agent,
    on_output: Callable[[str], None],
    *,
    stop: threading.Event | None = None,
) -> dict[str, int]:
    """Run advanced multi-worker experiment execution until ideas are exhausted."""
    from open_researcher.idea_pool import IdeaPool
    from open_researcher.worker import WorkerManager

    stop_event = stop or threading.Event()
    exit_codes: dict[str, int] = {}
    idea_pool = IdeaPool(research_dir / "idea_pool.json")
    watchdog = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: exp_agent.terminate())
    profile, plugins = build_parallel_worker_plugins(repo_path, research_dir, cfg)

    def agent_factory():
        name = cfg.worker_agent or exp_agent.name
        return get_agent(name, config=cfg.agent_config.get(name))

    wm = WorkerManager(
        repo_path=repo_path,
        research_dir=research_dir,
        gpu_manager=None,
        idea_pool=idea_pool,
        agent_factory=agent_factory,
        max_workers=cfg.max_workers,
        on_output=on_output,
        runtime_plugins=plugins,
    )

    cycle = 0
    try:
        on_output(
            "[system] Parallel runtime profile "
            f"{profile.name} (gpu={profile.gpu_allocation}, "
            f"failure_memory={profile.failure_memory}, "
            f"worktree={profile.worktree_isolation})"
        )
        while not stop_event.is_set():
            cycle += 1
            on_output(f"[system] === Cycle {cycle}: Starting Idea Agent ===")
            try:
                code = idea_agent.run(
                    repo_path, on_output=on_output, program_file="idea_program.md"
                )
            except Exception as exc:
                on_output(f"[idea] Agent error: {exc}")
                code = 1
            exit_codes["idea"] = code

            if not has_pending_ideas(research_dir):
                on_output("[system] No pending ideas after idea agent. Stopping.")
                break

            on_output(f"[system] Launching {cfg.max_workers} parallel workers...")
            watchdog.reset()
            wm.start()
            wm.join()
            watchdog.stop()

            if not has_pending_ideas(research_dir):
                on_output("[system] All ideas processed.")
                break
    finally:
        watchdog.stop()

    on_output("[system] Parallel execution finished.")
    return exit_codes
