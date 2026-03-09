"""Custom Textual widgets for Open Researcher TUI — Rich-colored rendering."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class StatsBar(Static):
    """Top status bar showing experiment summary with Rich color markup."""

    stats_text = reactive("")

    def render(self) -> Text:
        if self.stats_text:
            return Text.from_markup(self.stats_text)
        return Text.from_markup("Open Researcher — starting...")

    def update_stats(self, state: dict) -> None:
        total = state.get("total", 0)
        keep = state.get("keep", 0)
        discard = state.get("discard", 0)
        crash = state.get("crash", 0)
        best = state.get("best_value")
        pm = state.get("primary_metric", "")

        parts: list[str] = ["[bold]Open Researcher[/bold]"]
        if total > 0:
            parts.append(f"{total} exp")
            parts.append(f"[green]{keep} kept[/green]")
            parts.append(f"[red]{discard} disc[/red]")
            if crash:
                parts.append(f"[yellow]{crash} crash[/yellow]")
            if best is not None:
                parts.append(f"[bold cyan]best {pm}={best:.4f}[/bold cyan]")
        else:
            parts.append("[dim]waiting for experiments...[/dim]")

        self.stats_text = " | ".join(parts)


class ExperimentStatusPanel(Static):
    """Prominent display of experiment agent phase with colored icons."""

    status_text = reactive("")

    def render(self) -> Text:
        if self.status_text:
            return Text.from_markup(self.status_text)
        return Text.from_markup("[dim]-- \\[IDLE] waiting to start...[/dim]")

    def update_status(
        self, activity: dict | None, completed: int = 0, total: int = 0
    ) -> None:
        if not activity:
            self.status_text = "[dim]-- \\[IDLE] waiting to start...[/dim]"
            return

        status = activity.get("status", "idle")
        detail = activity.get("detail", "")
        idea = activity.get("idea", "")

        # Phase icon and color mapping
        phase_map: dict[str, tuple[str, str, str]] = {
            "running": ("\u25b6", "green", "RUNNING"),
            "establishing_baseline": ("\u27f3", "yellow", "BASELINE"),
            "paused": ("\u23f8", "yellow", "PAUSED"),
            "idle": ("--", "dim", "IDLE"),
            "analyzing": ("\u25b6", "cyan", "ANALYZING"),
            "generating": ("**", "magenta", "GENERATING"),
            "searching": ("..", "blue", "SEARCHING"),
            "coding": ("<>", "green", "CODING"),
            "evaluating": ("##", "cyan", "EVALUATING"),
            "scheduling": ("::", "yellow", "SCHEDULING"),
            "detecting_gpus": ("||", "blue", "DETECTING_GPUS"),
            "monitoring": ("()", "cyan", "MONITORING"),
            "cpu_serial_mode": ("\\[]", "yellow", "CPU_SERIAL"),
        }

        icon, color, label = phase_map.get(status, ("*", "white", status.upper()))

        lines: list[str] = []
        lines.append(f"  [{color}]{icon} \\[{label}][/{color}]")
        if idea:
            lines.append(f"     [bold]{idea}[/bold]")
        if detail:
            lines.append(f"     [dim]{detail}[/dim]")

        # Progress bar
        if total > 0:
            bar_width = 20
            filled = int(bar_width * completed / total) if total else 0
            empty = bar_width - filled
            bar = "\u2588" * filled + "\u2591" * empty
            lines.append(f"     [{color}]{bar}[/{color}]  {completed}/{total} ideas")

        self.status_text = "\n".join(lines)


class IdeaListPanel(Static):
    """Rich-formatted idea list — each idea is one colored line."""

    ideas_text = reactive("")

    def render(self) -> Text:
        if self.ideas_text:
            return Text.from_markup(self.ideas_text)
        return Text.from_markup("[dim]No ideas yet[/dim]")

    def update_ideas(self, ideas: list[dict]) -> None:
        if not ideas:
            self.ideas_text = "[dim]No ideas yet[/dim]"
            return

        # Status icons with colors
        icon_map: dict[str, tuple[str, str]] = {
            "kept": ("\u2713", "green"),
            "discarded": ("\u2717", "red"),
            "running": ("\u25b6", "bold yellow"),
            "pending": ("\u00b7", "dim"),
            "skipped": ("\u2013", "dim"),
            "done": ("\u2713", "green"),  # fallback for done without verdict
        }

        # Sort: running -> pending(by priority) -> done -> skipped
        status_order = {"running": 0, "pending": 1, "done": 2, "skipped": 3}
        sorted_ideas = sorted(
            ideas,
            key=lambda i: (
                status_order.get(i.get("status", "pending"), 9),
                i.get("priority", 99),
            ),
        )

        lines: list[str] = []
        for idea in sorted_ideas:
            sid = idea.get("status", "pending")
            result = idea.get("result")

            # Determine display verdict
            verdict = ""
            if result and isinstance(result, dict):
                verdict = result.get("verdict", "")

            # Pick icon based on verdict first, then status
            if verdict in icon_map:
                icon_char, icon_style = icon_map[verdict]
            elif sid in icon_map:
                icon_char, icon_style = icon_map[sid]
            else:
                icon_char, icon_style = ("?", "white")

            iid = idea.get("id", "???").replace("idea-", "#")
            desc = idea.get("description", "")
            # Pad/truncate description to 72 chars
            if len(desc) > 72:
                desc = desc[:69] + "..."
            desc = desc.ljust(72)

            # Metric value
            val = ""
            if result and isinstance(result, dict) and result.get("metric_value"):
                val = f"{result['metric_value']:.4f}"
            val = val.ljust(8)

            # Status display
            status_display = verdict if verdict else sid
            status_display = status_display.ljust(10)

            line = (
                f"  [{icon_style}]{icon_char}[/{icon_style}]"
                f"  {iid}"
                f"  {desc}"
                f"  {val}"
                f"  {status_display}"
            )
            lines.append(line)

        self.ideas_text = "\n".join(lines)


class HotkeyBar(Static):
    """Bottom bar showing available keyboard shortcuts with Rich styling."""

    def render(self) -> Text:
        keys = [
            ("[bold cyan]\\[p][/bold cyan][dim]ause[/dim]"),
            ("[bold cyan]\\[r][/bold cyan][dim]esume[/dim]"),
            ("[bold cyan]\\[s][/bold cyan][dim]kip[/dim]"),
            ("[bold cyan]\\[a][/bold cyan][dim]dd idea[/dim]"),
            ("[bold cyan]\\[e][/bold cyan][dim]dit[/dim]"),
            ("[bold cyan]\\[g][/bold cyan][dim]pu[/dim]"),
            ("[bold cyan]\\[l][/bold cyan][dim]og[/dim]"),
            ("[bold cyan]\\[m][/bold cyan][dim]in/max[/dim]"),
            ("[bold cyan]\\[q][/bold cyan][dim]uit[/dim]"),
        ]
        return Text.from_markup(" ".join(keys))
