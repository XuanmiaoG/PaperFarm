"""Open Researcher CLI — research workflow framework for AI agents."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from open_researcher.config_cmd import config_app
from open_researcher.ideas_cmd import ideas_app
from open_researcher.logs_cmd import logs_app
from open_researcher.workflow_options import build_workflow_selection

console = Console()

app = typer.Typer(
    name="open-researcher",
    help="Research workflow framework for AI agents. Initialize automated experiment tracking in any repo.",
)

app.add_typer(ideas_app, name="ideas")
app.add_typer(config_app, name="config")
app.add_typer(logs_app, name="logs")


def _print_notices(notices: list[str]) -> None:
    for notice in notices:
        console.print(f"[dim]{notice}[/dim]")


def _print_bootstrap_dry_run(
    repo_path: Path,
    *,
    frontend_mode: str,
    goal: str | None,
    max_experiments: int,
    workers: int | None,
) -> None:
    console.print("[bold]Workflow:[/bold] bootstrap")
    console.print(f"[bold]Frontend:[/bold] {frontend_mode}")
    console.print(f"[bold]Working directory:[/bold] {repo_path}")
    if workers is not None:
        console.print(f"[bold]Workers:[/bold] {workers}")
    if goal:
        console.print(f"[bold]Goal:[/bold] {goal}")
    if max_experiments > 0:
        console.print(f"[bold]Max experiments:[/bold] {max_experiments}")
    console.print("\n[dim]Dry run -- no bootstrap or agent launch performed.[/dim]")


def _dispatch_workflow(
    *,
    repo_path: Path,
    agent: str | None,
    workers: Optional[int],
    multi: bool,
    idea_agent: str | None,
    exp_agent: str | None,
    mode: str = "interactive",
    headless: bool = False,
    tag: str | None = None,
    goal: str | None = None,
    max_experiments: int = 0,
    dry_run: bool = False,
    force_bootstrap: bool = False,
) -> None:
    try:
        selection = build_workflow_selection(
            agent=agent,
            mode=mode,
            headless=headless,
            workers=workers,
            multi=multi,
            idea_agent=idea_agent,
            exp_agent=exp_agent,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    _print_notices(selection.notices)
    research_dir = repo_path / ".research"
    use_bootstrap_flow = (
        force_bootstrap
        or not research_dir.is_dir()
        or selection.frontend_mode == "headless"
        or tag is not None
        or goal is not None
        or max_experiments > 0
    )

    if use_bootstrap_flow:
        if selection.frontend_mode == "headless" and not goal:
            console.print("[red]--goal is required when using `--mode headless`.[/red]")
            raise typer.Exit(code=1)
        if dry_run:
            _print_bootstrap_dry_run(
                repo_path,
                frontend_mode=selection.frontend_mode,
                goal=goal,
                max_experiments=max_experiments,
                workers=selection.workers,
            )
            return
        if not force_bootstrap:
            if not research_dir.is_dir():
                console.print("[dim]No `.research/` found; bootstrapping before run.[/dim]")
            else:
                console.print("[dim]Using bootstrap workflow for this run.[/dim]")
        if selection.frontend_mode == "headless":
            from open_researcher.headless import do_start_headless

            do_start_headless(
                repo_path=repo_path,
                goal=goal or "",
                max_experiments=max_experiments,
                agent_name=selection.primary_agent_name,
                tag=tag,
                multi=selection.use_multi_agent,
                idea_agent_name=selection.idea_agent_name,
                exp_agent_name=selection.exp_agent_name,
                workers=selection.workers,
            )
            return

        from open_researcher.run_cmd import do_start

        do_start(
            repo_path=repo_path,
            agent_name=selection.primary_agent_name,
            tag=tag,
            multi=selection.use_multi_agent,
            idea_agent_name=selection.idea_agent_name,
            exp_agent_name=selection.exp_agent_name,
            workers=selection.workers,
        )
        return

    if selection.use_multi_agent:
        from open_researcher.run_cmd import do_run_multi

        do_run_multi(
            repo_path=repo_path,
            idea_agent_name=selection.idea_agent_name,
            exp_agent_name=selection.exp_agent_name,
            dry_run=dry_run,
            workers=selection.workers,
        )
    else:
        from open_researcher.run_cmd import do_run

        do_run(repo_path=repo_path, agent_name=selection.primary_agent_name, dry_run=dry_run)


@app.command()
def demo():
    """Launch the TUI with sample data — no agent or project needed."""
    from open_researcher.demo_cmd import do_demo

    do_demo()


@app.command()
def init(tag: str = typer.Option(None, help="Experiment tag (e.g. mar8). Defaults to today's date.")):
    """Initialize .research/ directory in the current repo."""
    from open_researcher.init_cmd import do_init

    do_init(repo_path=Path.cwd(), tag=tag)


@app.command()
def status(
    sparkline: bool = typer.Option(False, "--sparkline", help="Show metric sparkline"),
):
    """Show current research progress."""
    from open_researcher.status_cmd import print_status

    print_status(Path.cwd(), sparkline=sparkline)


@app.command()
def results(
    chart: str = typer.Option(None, "--chart", help="Show chart for metric (use 'primary' or metric name)"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON"),
    last: int = typer.Option(None, "--last", help="Show only last N experiments"),
):
    """Print experiment results table."""
    from open_researcher.results_cmd import print_results, print_results_chart, print_results_json

    if json_out:
        print_results_json(Path.cwd())
    elif chart is not None:
        metric = chart if chart else None
        print_results_chart(Path.cwd(), metric=metric, last=last)
    else:
        print_results(Path.cwd())


@app.command()
def export():
    """Export experiment report as Markdown."""
    from open_researcher.export_cmd import do_export

    do_export(Path.cwd())


@app.command()
def doctor():
    """Run health checks on the research environment."""
    from open_researcher.doctor_cmd import print_doctor

    print_doctor(Path.cwd())


@app.command()
def run(
    agent: str = typer.Option(None, help="Agent to use (claude-code, codex, aider, opencode)."),
    tag: str = typer.Option(None, help="Experiment tag when bootstrapping a new workflow."),
    mode: str = typer.Option("interactive", "--mode", help="Run mode: `interactive` or `headless`."),
    workers: Optional[int] = typer.Option(
        None,
        "--workers",
        help="Experiment worker count. `1` enables the research loop, `>1` enables parallel workers.",
    ),
    multi: bool = typer.Option(False, "--multi", help="Enable dual-agent mode (Idea + Experiment).", hidden=True),
    idea_agent: str = typer.Option(None, "--idea-agent", help="Agent for idea generation (multi mode).", hidden=True),
    exp_agent: str = typer.Option(None, "--exp-agent", help="Agent for experiments (multi mode).", hidden=True),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run without TUI, output JSON Lines to stdout.",
        hidden=True,
    ),
    goal: str = typer.Option(None, "--goal", help="Research goal for bootstrap/headless mode."),
    max_experiments: int = typer.Option(0, "--max-experiments", help="Stop after N experiments (0 = unlimited)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the command without executing."),
):
    """Primary workflow command: bootstrap if needed, otherwise run the existing workflow."""
    _dispatch_workflow(
        repo_path=Path.cwd(),
        agent=agent,
        tag=tag,
        mode=mode,
        workers=workers,
        multi=multi,
        idea_agent=idea_agent,
        exp_agent=exp_agent,
        headless=headless,
        goal=goal,
        max_experiments=max_experiments,
        dry_run=dry_run,
    )


@app.command(hidden=True)
def start(
    agent: str = typer.Option(None, help="Agent to use (claude-code, codex, aider, opencode)."),
    tag: str = typer.Option(None, help="Experiment tag (e.g. mar10). Defaults to today's date."),
    mode: str = typer.Option("interactive", "--mode", help="Run mode: `interactive` or `headless`."),
    workers: Optional[int] = typer.Option(
        None,
        "--workers",
        help="Experiment worker count. `1` enables the research loop, `>1` enables parallel workers.",
    ),
    multi: bool = typer.Option(False, "--multi", help="Enable dual-agent mode (Idea + Experiment).", hidden=True),
    idea_agent: str = typer.Option(None, "--idea-agent", help="Agent for idea generation (multi mode).", hidden=True),
    exp_agent: str = typer.Option(None, "--exp-agent", help="Agent for experiments (multi mode).", hidden=True),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run without TUI, output JSON Lines to stdout.",
        hidden=True,
    ),
    goal: str = typer.Option(None, "--goal", help="Research goal (required for `--mode headless`)."),
    max_experiments: int = typer.Option(0, "--max-experiments", help="Stop after N experiments (0 = unlimited)."),
):
    """Legacy alias for bootstrap mode; prefer `run` for both new and existing workflows."""
    _dispatch_workflow(
        repo_path=Path.cwd(),
        agent=agent,
        tag=tag,
        mode=mode,
        workers=workers,
        multi=multi,
        idea_agent=idea_agent,
        exp_agent=exp_agent,
        headless=headless,
        goal=goal,
        max_experiments=max_experiments,
        force_bootstrap=True,
    )


if __name__ == "__main__":
    app()
