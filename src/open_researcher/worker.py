"""Parallel worker manager -- run experiments across multiple GPUs."""

import logging
import threading
from pathlib import Path
from typing import Callable

from open_researcher.activity import ActivityMonitor
from open_researcher.gpu_manager import GPUManager
from open_researcher.idea_pool import IdeaPool
from open_researcher.worker_plugins import (
    WorkerRuntimePlugins,
    build_legacy_worker_plugins,
)

logger = logging.getLogger(__name__)


class WorkerManager:
    """Orchestrate parallel experiment workers across GPUs."""

    def __init__(
        self,
        repo_path: Path,
        research_dir: Path,
        gpu_manager: GPUManager | None,
        idea_pool: IdeaPool,
        agent_factory: Callable,
        max_workers: int,
        on_output: Callable[[str], None],
        runtime_plugins: WorkerRuntimePlugins | None = None,
    ):
        self.repo_path = repo_path
        self.research_dir = research_dir
        self.idea_pool = idea_pool
        self.agent_factory = agent_factory
        self.max_workers = max_workers
        self.on_output = on_output
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._activity = ActivityMonitor(research_dir)
        self._plugins = runtime_plugins or build_legacy_worker_plugins(
            repo_path=repo_path,
            research_dir=research_dir,
            gpu_manager=gpu_manager,
        )

    def start(self) -> None:
        """Start worker threads based on available GPUs."""
        self._stop.clear()
        self._workers.clear()
        slots: list[dict | None]
        if self._plugins.gpu_allocator is not None:
            slots = self._plugins.gpu_allocator.worker_slots(self.max_workers)
        else:
            n_workers = max(self.max_workers, 1) if self.max_workers > 0 else 1
            slots = [None] * n_workers

        for i, gpu in enumerate(slots):
            t = threading.Thread(
                target=self._worker_loop, args=(i, gpu), daemon=True
            )
            t.start()
            self._workers.append(t)
        self.on_output(f"[system] Started {len(slots)} worker(s)")

    def stop(self) -> None:
        """Signal all workers to stop."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for all worker threads to finish."""
        for t in self._workers:
            t.join(timeout=timeout)

    def _worker_loop(self, worker_id: int, gpu: dict | None) -> None:
        wid = f"worker-{worker_id}"
        allocation = (
            self._plugins.gpu_allocator.allocate(wid, gpu)
            if self._plugins.gpu_allocator is not None
            else None
        )
        gpu_env = allocation.env if allocation is not None else {}
        for line in allocation.log_lines if allocation is not None else []:
            self.on_output(line)

        while not self._stop.is_set():
            idea = self.idea_pool.claim_idea(wid)
            if not idea:
                self.on_output(f"[{wid}] No more pending ideas, stopping")
                break

            idea_description = str(idea.get("description", ""))
            claim_token = str(idea.get("claim_token", "")).strip()
            memory_context = (
                self._plugins.failure_memory.prepare(idea_description, wid)
                if self._plugins.failure_memory is not None
                else None
            )
            failure_class = (
                memory_context.failure_class if memory_context is not None else "general_failure"
            )
            ranked_fix_actions = (
                memory_context.ranked_fix_actions if memory_context is not None else []
            )
            first_fix_action = (
                memory_context.first_fix_action if memory_context is not None else "generate_new_plan"
            )
            for line in memory_context.log_lines if memory_context is not None else []:
                self.on_output(line)

            self._activity.update_worker(
                "experiment_agent",
                wid,
                status="running",
                idea=idea_description[:50],
                failure_class=failure_class,
                memory_policy="rank_historical_success" if memory_context is not None else "disabled",
                ranked_fixes=ranked_fix_actions[:3],
                first_fix_action=first_fix_action,
            )
            self.on_output(f"[{wid}] Running: {idea_description[:60]}")
            if gpu_env:
                self.on_output(f"[{wid}] Using GPU env: {gpu_env}")

            workspace = (
                self._plugins.workspace_isolation.acquire(wid, str(idea["id"]))
                if self._plugins.workspace_isolation is not None
                else None
            )
            workdir = workspace.workdir if workspace is not None else self.repo_path
            for line in workspace.log_lines if workspace is not None else []:
                self.on_output(line)

            # Create agent and run in isolated worktree
            agent = self.agent_factory()
            run_code = 1
            try:
                run_env = {
                    **gpu_env,
                    "OPEN_RESEARCHER_MEMORY_POLICY": (
                        "rank_historical_success" if memory_context is not None else "disabled"
                    ),
                    "OPEN_RESEARCHER_FAILURE_CLASS": failure_class,
                    "OPEN_RESEARCHER_RANKED_FIXES": ",".join(ranked_fix_actions[:3]),
                    "OPEN_RESEARCHER_FIRST_FIX_ACTION": first_fix_action,
                }
                code = agent.run(
                    workdir,
                    on_output=self.on_output,
                    program_file="experiment_program.md",
                    env=run_env,
                )
                run_code = int(code)
                if code == 0:
                    applied = self.idea_pool.mark_done(
                        idea["id"],
                        metric_value=None,
                        verdict="completed",
                        claim_token=claim_token or None,
                    )
                    if not applied:
                        self.on_output(
                            f"[{wid}] Claim race detected for {idea['id']}; winner already finalized, cleanup applied"
                        )
                else:
                    applied = self.idea_pool.update_status(
                        idea["id"], "skipped", claim_token=claim_token or None
                    )
                    if not applied:
                        self.on_output(
                            f"[{wid}] Claim race detected for {idea['id']}; skip write suppressed, cleanup applied"
                        )
            except Exception as exc:
                self.on_output(f"[{wid}] Error: {exc}")
                applied = self.idea_pool.update_status(
                    idea["id"], "skipped", claim_token=claim_token or None
                )
                if not applied:
                    self.on_output(
                        f"[{wid}] Claim race detected for {idea['id']}; error skip suppressed, cleanup applied"
                    )
                run_code = 1
            finally:
                try:
                    if self._plugins.failure_memory is not None and memory_context is not None:
                        self._plugins.failure_memory.record(memory_context, run_code)
                except Exception as exc:
                    logger.debug("Failure memory record failed: %s", exc)
                if workspace is not None:
                    workspace.cleanup()
                    if workdir != self.repo_path:
                        self.on_output(f"[{wid}] Worktree cleaned up")

        self._activity.update_worker(
            "experiment_agent", wid, status="idle"
        )
        if self._plugins.gpu_allocator is not None and allocation is not None:
            self._plugins.gpu_allocator.release(allocation)
