"""Tests for graph-protocol artifact management."""

from pathlib import Path

from open_researcher.graph_protocol import ensure_graph_protocol_artifacts


def test_ensure_graph_protocol_artifacts_refreshes_internal_role_programs(tmp_path: Path) -> None:
    research = tmp_path / ".research"
    internal = research / ".internal" / "role_programs"
    internal.mkdir(parents=True)
    stale = internal / "manager.md"
    stale.write_text("old manager template\n", encoding="utf-8")

    ensure_graph_protocol_artifacts(research)

    content = stale.read_text(encoding="utf-8")
    assert "evaluation-contract hygiene" in content
    assert "old manager template" not in content
