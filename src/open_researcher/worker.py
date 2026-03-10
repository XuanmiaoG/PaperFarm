"""Parallel worker manager -- run experiments across multiple GPUs."""

import logging
import threading
from pathlib import Path
from typing import Callable

from open_researcher.activity import ActivityMonitor
from open_researcher.failure_memory import (
    MEMORY_POLICY,
    FailureMemoryLedger,
    classify_failure,
)
from open_researcher.gpu_manager import GPUManager
from open_researcher.idea_pool import IdeaPool
from open_researcher.worktree import create_worktree, remove_worktree

logger = logging.getLogger(__name__)


class WorkerManager:
    """Orchestrate parallel experiment workers across GPUs."""

    def __init__(
        self,
        repo_path: Path,
        research_dir: Path,
        gpu_manager: GPUManager,
        idea_pool: IdeaPool,
        agent_factory: Callable,
        max_workers: int,
        on_output: Callable[[str], None],
    ):
        self.repo_path = repo_path
        self.research_dir = research_dir
        self.gpu_manager = gpu_manager
        self.idea_pool = idea_pool
        self.agent_factory = agent_factory
        self.max_workers = max_workers
        self.on_output = on_output
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._activity = ActivityMonitor(research_dir)
        self._failure_memory = FailureMemoryLedger(
            research_dir / "failure_memory_ledger.json"
        )

    def start(self) -> None:
        """Start worker threads based on available GPUs."""
        self._stop.clear()
        self._workers.clear()
        try:
            gpus = self.gpu_manager.refresh()
        except Exception:
            gpus = []
        available = [g for g in gpus if g.get("allocated_to") is None]
        if available:
            n_workers = min(self.max_workers, len(available)) if self.max_workers > 0 else len(available)
        else:
            # 无可用 GPU 时限制为最多 1 个 worker
            n_workers = min(self.max_workers, 1) if self.max_workers > 0 else 1
        n_workers = max(n_workers, 1)  # at least 1 worker

        for i in range(n_workers):
            gpu = available[i] if i < len(available) else None
            t = threading.Thread(
                target=self._worker_loop, args=(i, gpu), daemon=True
            )
            t.start()
            self._workers.append(t)
        self.on_output(f"[system] Started {n_workers} worker(s)")

    def stop(self) -> None:
        """Signal all workers to stop."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for all worker threads to finish."""
        for t in self._workers:
            t.join(timeout=timeout)

    def _worker_loop(self, worker_id: int, gpu: dict | None) -> None:
        wid = f"worker-{worker_id}"
        gpu_env: dict[str, str] = {}
        actual_host: str | None = None
        actual_device: int | None = None

        if gpu:
            # 使用 allocate 的返回值作为实际分配结果
            alloc_result = self.gpu_manager.allocate(tag=wid)
            if alloc_result is not None:
                actual_host, actual_device = alloc_result
            else:
                # allocate 未能分配，回退到已选的 gpu 信息
                actual_host, actual_device = gpu["host"], gpu["device"]
            gpu_env = {"CUDA_VISIBLE_DEVICES": str(actual_device)}
            self.on_output(f"[{wid}] Allocated GPU {actual_host}:{actual_device}")

        while not self._stop.is_set():
            idea = self.idea_pool.claim_idea(wid)
            if not idea:
                self.on_output(f"[{wid}] No more pending ideas, stopping")
                break

            idea_description = str(idea.get("description", ""))
            claim_token = str(idea.get("claim_token", "")).strip()
            failure_class = classify_failure(idea_description)
            ranked_fixes = self._failure_memory.rank_fixes(failure_class)
            ranked_fix_actions = [
                str(item.get("fix_action", "")).strip()
                for item in ranked_fixes
                if str(item.get("fix_action", "")).strip()
            ]
            first_fix_action = (
                ranked_fix_actions[0] if ranked_fix_actions else "generate_new_plan"
            )

            self._activity.update_worker(
                "experiment_agent",
                wid,
                status="running",
                idea=idea_description[:50],
                failure_class=failure_class,
                memory_policy=MEMORY_POLICY,
                ranked_fixes=ranked_fix_actions[:3],
                first_fix_action=first_fix_action,
            )
            self.on_output(f"[{wid}] Running: {idea_description[:60]}")
            self.on_output(
                f"[{wid}] Memory policy {MEMORY_POLICY}: first remediation action {first_fix_action}"
            )
            if gpu_env:
                self.on_output(f"[{wid}] Using GPU env: {gpu_env}")

            # Create isolated worktree for this experiment
            wt_path = None
            workdir = self.repo_path  # fallback if worktree creation fails
            try:
                wt_path = create_worktree(self.repo_path, f"{wid}-{idea['id']}")
                workdir = wt_path
                self.on_output(f"[{wid}] Worktree created: {wt_path.name}")
            except Exception as exc:
                self.on_output(f"[{wid}] Worktree creation failed ({exc}), running in main repo")

            # Create agent and run in isolated worktree
            agent = self.agent_factory()
            run_code = 1
            try:
                run_env = {
                    **gpu_env,
                    "OPEN_RESEARCHER_MEMORY_POLICY": MEMORY_POLICY,
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
                    self._failure_memory.record(
                        failure_class=failure_class,
                        fix_action=first_fix_action,
                        verification_result="pass" if run_code == 0 else "fail",
                        recovery_iterations=1 if run_code == 0 else 2,
                    )
                except Exception as exc:
                    logger.debug("Failure memory record failed: %s", exc)
                # Always clean up worktree
                if wt_path is not None:
                    try:
                        remove_worktree(self.repo_path, wt_path)
                        self.on_output(f"[{wid}] Worktree cleaned up")
                    except Exception as exc:
                        logger.debug("Worktree cleanup failed: %s", exc)

        self._activity.update_worker(
            "experiment_agent", wid, status="idle"
        )
        if gpu and actual_host is not None and actual_device is not None:
            try:
                self.gpu_manager.release(actual_host, actual_device)
            except Exception:
                pass
