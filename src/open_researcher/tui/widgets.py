"""Custom Textual widgets for Open Researcher TUI."""

from textual.reactive import reactive
from textual.widgets import DataTable, Static


class StatsBar(Static):
    """Top status bar showing experiment summary."""

    stats = reactive("")

    def render(self) -> str:
        return self.stats or "Open Researcher — starting..."

    def update_stats(self, state: dict) -> None:
        total = state.get("total", 0)
        keep = state.get("keep", 0)
        discard = state.get("discard", 0)
        crash = state.get("crash", 0)
        best = state.get("best_value")
        pm = state.get("primary_metric", "")

        parts = ["Open Researcher"]
        if total > 0:
            parts.append(f"{total} exp")
            parts.append(f"{keep} kept {discard} disc {crash} crash")
            if best is not None:
                parts.append(f"best {pm}={best:.4f}")
        else:
            parts.append("waiting for experiments...")

        self.stats = " | ".join(parts)


class IdeaPoolTable(Static):
    """Scrollable DataTable showing all ideas in the pool."""

    def compose(self):
        yield DataTable(id="idea-table")

    def on_mount(self):
        table = self.query_one("#idea-table", DataTable)
        table.add_columns("ID", "Description", "Status", "Pri", "Result")
        table.cursor_type = "row"

    def update_ideas(self, ideas: list[dict], summary: dict) -> None:
        table = self.query_one("#idea-table", DataTable)
        table.clear()
        status_order = {"running": 0, "pending": 1, "done": 2, "skipped": 3}
        sorted_ideas = sorted(
            ideas,
            key=lambda i: (status_order.get(i["status"], 9), i.get("priority", 99)),
        )
        for idea in sorted_ideas:
            sid = idea["status"]
            iid = idea["id"].replace("idea-", "#")
            desc = idea["description"][:80]
            pri = str(idea.get("priority", ""))
            result = idea.get("result")
            if result and result.get("metric_value"):
                val = f"{result['metric_value']:.4f}"
            else:
                val = ""
            status_display = sid.upper() if sid == "running" else sid
            table.add_row(iid, desc, status_display, pri, val)


class AgentStatusWidget(Static):
    """Prominent display of agent's current phase and action."""

    status_text = reactive("  -- [IDLE] waiting to start...")

    def render(self) -> str:
        return self.status_text

    def update_status(self, activity: dict | None) -> None:
        if not activity:
            self.status_text = "  -- [IDLE] waiting to start..."
            return

        status = activity.get("status", "idle")
        detail = activity.get("detail", "")
        idea = activity.get("idea", "")
        updated = activity.get("updated_at", "")[:19]

        # Status icon mapping (text symbols, no emoji)
        status_icons = {
            "analyzing": ">>",
            "generating": "**",
            "searching": "..",
            "idle": "--",
            "coding": "<>",
            "evaluating": "##",
            "scheduling": "::",
            "detecting_gpus": "||",
            "establishing_baseline": "==",
            "monitoring": "()",
            "paused": "--",
            "cpu_serial_mode": "[]",
        }
        icon = status_icons.get(status, " *")

        lines = [f"  {icon} [{status.upper()}]"]
        if detail:
            lines.append(f"     {detail}")
        if idea:
            lines.append(f"     Idea: {idea}")
        if updated:
            lines.append(f"     Updated: {updated}")

        self.status_text = "\n".join(lines)


class HotkeyBar(Static):
    """Bottom bar showing available keyboard shortcuts."""

    def render(self) -> str:
        return "\\[p]ause \\[r]esume \\[s]kip \\[a]dd idea \\[e]dit \\[g]pu \\[l]og \\[q]uit"
