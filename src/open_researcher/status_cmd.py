"""Implementation of the 'status' command."""

import csv
import subprocess
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel


def _detect_phase(research: Path) -> int:
    """Detect current research phase (1-4) based on file contents."""
    pu = research / "project-understanding.md"
    ev = research / "evaluation.md"
    results = research / "results.tsv"

    # Phase 1: project understanding not filled
    if pu.exists():
        content = pu.read_text()
        if "<!--" in content and content.strip().endswith("-->"):
            return 1
        has_content = any(
            line.strip() and not line.startswith("#") and not line.startswith(">") and "<!--" not in line
            for line in content.splitlines()
        )
        if not has_content:
            return 1

    # Phase 2: evaluation not filled
    if ev.exists():
        content = ev.read_text()
        has_content = any(
            line.strip() and not line.startswith("#") and not line.startswith(">") and "<!--" not in line
            for line in content.splitlines()
        )
        if not has_content:
            return 2

    # Phase 3/4: check results
    if results.exists():
        rows = list(csv.DictReader(results.open(), delimiter="\t"))
        if len(rows) == 0:
            return 3
        return 4

    return 3


def parse_research_state(repo_path: Path) -> dict:
    """Parse .research/ directory into a state dict."""
    research = repo_path / ".research"
    state = {}

    # Parse config
    config_path = research / "config.yaml"
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text()) or {}
        state["mode"] = config.get("mode", "autonomous")
        metrics = config.get("metrics", {}).get("primary", {})
        state["primary_metric"] = metrics.get("name", "")
        state["direction"] = metrics.get("direction", "")
    else:
        state["mode"] = "unknown"
        state["primary_metric"] = ""
        state["direction"] = ""

    # Parse results
    results_path = research / "results.tsv"
    rows = []
    if results_path.exists():
        rows = list(csv.DictReader(results_path.open(), delimiter="\t"))

    state["total"] = len(rows)
    state["keep"] = sum(1 for r in rows if r["status"] == "keep")
    state["discard"] = sum(1 for r in rows if r["status"] == "discard")
    state["crash"] = sum(1 for r in rows if r["status"] == "crash")
    state["recent"] = rows[-5:] if rows else []

    # Compute metric values
    higher = state["direction"] == "higher_is_better"
    keep_rows = [r for r in rows if r["status"] == "keep"]
    if keep_rows:
        values = [float(r["metric_value"]) for r in keep_rows]
        state["baseline_value"] = values[0]
        state["current_value"] = values[-1]
        state["best_value"] = max(values) if higher else min(values)
    else:
        state["baseline_value"] = None
        state["current_value"] = None
        state["best_value"] = None

    state["phase"] = _detect_phase(research)

    # Git branch
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True, cwd=repo_path,
    )
    state["branch"] = result.stdout.strip() if result.returncode == 0 else "unknown"

    return state


PHASE_NAMES = {
    1: "理解项目 (Phase 1)",
    2: "设计评估 (Phase 2)",
    3: "建立基线 (Phase 3)",
    4: "实验循环 (Phase 4)",
}


def print_status(repo_path: Path) -> None:
    """Print formatted research status to terminal."""
    research = repo_path / ".research"
    if not research.exists():
        print("[ERROR] No .research/ directory found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    state = parse_research_state(repo_path)
    console = Console()

    lines = []
    lines.append(f"  阶段: {PHASE_NAMES.get(state['phase'], 'unknown')}")
    lines.append(f"  分支: {state['branch']}")
    lines.append(f"  模式: {state['mode']}")
    lines.append("")

    if state["total"] > 0:
        lines.append("  实验统计:")
        lines.append(
            f"    总数: {state['total']}  "
            f"✓ keep: {state['keep']}  "
            f"✗ discard: {state['discard']}  "
            f"💥 crash: {state['crash']}"
        )
        lines.append("")

        if state["primary_metric"]:
            lines.append(f"  主要指标: {state['primary_metric']}")
            if state["baseline_value"] is not None:
                lines.append(f"    基线:  {state['baseline_value']:.4f}")
                lines.append(f"    当前:  {state['current_value']:.4f}")
                lines.append(f"    最佳:  {state['best_value']:.4f}")
            lines.append("")

        lines.append(f"  最近 {len(state['recent'])} 次实验:")
        status_icons = {"keep": "✓", "discard": "✗", "crash": "💥"}
        for r in reversed(state["recent"]):
            icon = status_icons.get(r["status"], "?")
            val = float(r["metric_value"])
            lines.append(f"    {icon} {val:.4f}  {r['description']}")
    else:
        lines.append("  尚无实验记录")

    panel = Panel(
        "\n".join(lines),
        title="Open Researcher",
        border_style="blue",
    )
    console.print(panel)
