"""Run command — launch AI agents with interactive Textual TUI."""

import threading
from datetime import date
from pathlib import Path

from jinja2 import Environment, PackageLoader
from rich.console import Console

from open_researcher.agent_runtime import resolve_agent
from open_researcher.agents import detect_agent, get_agent
from open_researcher.config import load_config
from open_researcher.log_output import make_safe_output as _make_safe_output
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
from open_researcher.tui_runner import (
    launch_dual_agent_runtime,
    print_exit_summary,
    run_tui_session,
    start_daemon,
)
from open_researcher.watchdog import TimeoutWatchdog
from open_researcher.workflow_options import apply_worker_override

console = Console()


def _resolve_agent(agent_name: str | None, agent_configs: dict | None = None):
    """Resolve agent by name or auto-detect, with per-agent config."""
    return resolve_agent(
        agent_name,
        agent_configs,
        detect_agent_fn=detect_agent,
        get_agent_fn=get_agent,
        console_obj=console,
    )


def render_scout_program(research_dir: Path, tag: str, goal: str | None) -> None:
    """Render scout_program.md with optional goal."""
    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    template = env.get_template("scout_program.md.j2")
    content = template.render(tag=tag, goal=goal or "")
    (research_dir / "scout_program.md").write_text(content)


def do_start_init(repo_path: Path, tag: str | None = None) -> Path:
    """Auto-initialize .research/ if needed, return research dir path."""
    research = repo_path / ".research"
    if research.is_dir():
        console.print("[dim]Using existing .research/ directory.[/dim]")
        return research

    from open_researcher.init_cmd import do_init

    if tag is None:
        tag = date.today().strftime("%b%d").lower()

    do_init(repo_path, tag=tag)
    return research


def do_run(repo_path: Path, agent_name: str | None, dry_run: bool) -> None:
    """Single-agent mode — backward compatible."""
    research = repo_path / ".research"
    if not research.is_dir():
        console.print("[red]Error:[/red] .research/ not found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    program_md = research / "program.md"
    if not program_md.exists():
        console.print("[red]Error:[/red] .research/program.md not found.")
        raise SystemExit(1)

    # Load config before agent resolution so agent_config is available
    cfg = load_config(research)
    agent = _resolve_agent(agent_name, cfg.agent_config)

    if dry_run:
        console.print(f"[bold]Agent:[/bold] {agent.name}")
        console.print(f"[bold]Command:[/bold] {' '.join(agent.build_command(program_md, repo_path))}")
        console.print(f"[bold]Working directory:[/bold] {repo_path}")
        console.print("\n[dim]Dry run -- no agent launched.[/dim]")
        return

    exit_codes: dict[str, int] = {}

    def setup(app, renderer):
        del renderer
        watchdog = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: agent.terminate())
        on_output = _make_safe_output(app.append_exp_log, research / "run.log")

        def _run_agent() -> None:
            try:
                code = agent.run(repo_path, on_output=on_output, program_file="program.md")
            except Exception as exc:
                on_output(f"[agent] Agent error: {exc}")
                code = 1
            exit_codes["agent"] = code

        watchdog.start()
        start_daemon(_run_agent)

        cleanup = [watchdog.stop, agent.terminate]
        if hasattr(on_output, "close"):
            cleanup.insert(0, on_output.close)
        return cleanup

    run_tui_session(repo_path, multi=False, setup=setup)
    print_exit_summary(console, exit_codes, [("agent", f"Agent {agent.name}")], show_missing=True)

    from open_researcher.status_cmd import print_status

    print_status(repo_path)


def do_start(
    repo_path: Path,
    agent_name: str | None = None,
    tag: str | None = None,
    multi: bool = False,
    idea_agent_name: str | None = None,
    exp_agent_name: str | None = None,
    workers: int | None = None,
) -> None:
    """Bootstrap a research workflow: auto-init -> Scout -> Review -> Experiment."""
    from open_researcher.tui.modals import GoalInputModal
    from open_researcher.tui.review import ReviewScreen

    if tag is None:
        tag = date.today().strftime("%b%d").lower()
    research = do_start_init(repo_path, tag=tag)
    cfg = apply_worker_override(load_config(research), workers)
    use_multi_agent = bool(multi or idea_agent_name or exp_agent_name or workers is not None)

    scout_agent = _resolve_agent(agent_name, cfg.agent_config)
    if use_multi_agent:
        idea_agent = _resolve_agent(idea_agent_name or agent_name, cfg.agent_config)
        exp_agent = _resolve_agent(exp_agent_name or agent_name, cfg.agent_config)
    else:
        idea_agent = None
        exp_agent = None

    stop = threading.Event()
    exit_codes: dict[str, int] = {}

    def setup(app, renderer):
        assert renderer is not None
        loop = ResearchLoop(repo_path, research, cfg, renderer.on_event)

        def _on_review_result(result: str | None) -> None:
            if result == "confirm":
                app.app_phase = "experimenting"
                _start_experiment_agents()
            elif result == "reanalyze":
                app.app_phase = "scouting"
                _launch_scout()
            else:
                app.exit()

        def _show_review() -> None:
            app.push_screen(ReviewScreen(research), _on_review_result)

        def _launch_scout() -> None:
            def _run_scout():
                exit_codes["scout"] = loop.run_scout(scout_agent)
                if stop.is_set():
                    return
                code = exit_codes.get("scout", -1)
                if code != 0:
                    try:
                        app.call_from_thread(
                            app.notify,
                            f"Scout Agent failed (code={code}). Check logs.",
                            severity="error",
                        )
                    except RuntimeError:
                        pass
                    return
                try:
                    app.call_from_thread(setattr, app, "app_phase", "reviewing")
                    app.call_from_thread(_show_review)
                except RuntimeError:
                    pass

            start_daemon(_run_scout)

        def _on_goal_result(goal: str | None) -> None:
            render_scout_program(research, tag=tag, goal=goal)
            if goal:
                (research / "goal.md").write_text(f"# Research Goal\n\n{goal}\n")
            app.app_phase = "scouting"
            _launch_scout()

        def _start_experiment_agents() -> None:
            if use_multi_agent and idea_agent and exp_agent:
                launch_dual_agent_runtime(
                    repo_path=repo_path,
                    research_dir=research,
                    cfg=cfg,
                    loop=loop,
                    renderer=renderer,
                    idea_agent=idea_agent,
                    exp_agent=exp_agent,
                    stop=stop,
                    exit_codes=exit_codes,
                )
                return

            def _run_single():
                exit_codes["agent"] = loop.run_single_agent(scout_agent)

            start_daemon(_run_single)

        app.push_screen(GoalInputModal(), _on_goal_result)

        cleanup = [stop.set, scout_agent.terminate]
        if idea_agent:
            cleanup.append(idea_agent.terminate)
        if exp_agent:
            cleanup.append(exp_agent.terminate)
        return cleanup

    run_tui_session(
        repo_path,
        research_dir=research,
        multi=use_multi_agent,
        initial_phase="scouting",
        setup=setup,
    )
    print_exit_summary(
        console,
        exit_codes,
        [("scout", "Scout"), ("idea", "Idea Agent"), ("exp", "Experiment Agent"), ("agent", "Agent")],
    )

    from open_researcher.status_cmd import print_status

    print_status(repo_path)


def do_run_multi(
    repo_path: Path,
    idea_agent_name: str | None,
    exp_agent_name: str | None,
    dry_run: bool,
    workers: int | None = None,
) -> None:
    """Dual-agent mode — Idea Agent + Experiment Agent in parallel."""
    research = repo_path / ".research"
    if not research.is_dir():
        console.print("[red]Error:[/red] .research/ not found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    idea_program = research / "idea_program.md"
    exp_program = research / "experiment_program.md"

    for p in [idea_program, exp_program]:
        if not p.exists():
            console.print(f"[red]Error:[/red] {p.name} not found. Re-run 'open-researcher init'.")
            raise SystemExit(1)

    # Load config before agent resolution so agent_config is available
    cfg = apply_worker_override(load_config(research), workers)
    idea_agent = _resolve_agent(idea_agent_name, cfg.agent_config)
    exp_agent = _resolve_agent(exp_agent_name, cfg.agent_config)

    if dry_run:
        console.print(f"[bold]Idea Agent:[/bold] {idea_agent.name}")
        console.print(f"[bold]Experiment Agent:[/bold] {exp_agent.name}")
        console.print(f"[bold]Working directory:[/bold] {repo_path}")
        console.print("\n[dim]Dry run -- no agents launched.[/dim]")
        return

    # Ensure worktrees directory exists for parallel experiments
    worktrees_dir = research / "worktrees"
    worktrees_dir.mkdir(exist_ok=True)
    stop = threading.Event()
    exit_codes: dict[str, int] = {}

    def setup(app, renderer):
        del app
        assert renderer is not None
        loop = ResearchLoop(
            repo_path,
            research,
            cfg,
            renderer.on_event,
            has_pending_ideas_fn=_has_pending_ideas,
            read_latest_status_fn=_read_latest_status,
            pause_fn=_set_paused,
        )
        launch_dual_agent_runtime(
            repo_path=repo_path,
            research_dir=research,
            cfg=cfg,
            loop=loop,
            renderer=renderer,
            idea_agent=idea_agent,
            exp_agent=exp_agent,
            stop=stop,
            exit_codes=exit_codes,
        )
        return [stop.set, idea_agent.terminate, exp_agent.terminate]

    run_tui_session(
        repo_path,
        research_dir=research,
        multi=True,
        setup=setup,
    )
    print_exit_summary(
        console,
        exit_codes,
        [("idea", "Idea Agent"), ("exp", "Experiment Agent")],
        show_missing=True,
    )

    from open_researcher.status_cmd import print_status

    print_status(repo_path)
