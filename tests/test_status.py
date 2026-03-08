import tempfile
from pathlib import Path

from open_researcher.status_cmd import parse_research_state


def test_parse_state_with_results():
    """Should correctly parse results.tsv and config.yaml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        (research / "config.yaml").write_text(
            "mode: autonomous\n"
            "metrics:\n"
            "  primary:\n"
            "    name: accuracy\n"
            "    direction: higher_is_better\n"
        )

        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
            "2026-03-08T10:00:00\ta1b2c3d\taccuracy\t0.850000\t{}\tkeep\tbaseline\n"
            "2026-03-08T10:15:00\tb2c3d4e\taccuracy\t0.872000\t{}\tkeep\tincrease LR\n"
            "2026-03-08T10:30:00\tc3d4e5f\taccuracy\t0.840000\t{}\tdiscard\tswitch optimizer\n"
            "2026-03-08T10:45:00\td4e5f6g\taccuracy\t0.000000\t{}\tcrash\tOOM\n"
        )

        # Write filled project understanding
        (research / "project-understanding.md").write_text("# Project\n\nThis is a real project description.")

        # Write filled evaluation
        (research / "evaluation.md").write_text("# Eval\n\nThis uses accuracy as the metric.")

        state = parse_research_state(Path(tmpdir))

        assert state["mode"] == "autonomous"
        assert state["primary_metric"] == "accuracy"
        assert state["direction"] == "higher_is_better"
        assert state["total"] == 4
        assert state["keep"] == 2
        assert state["discard"] == 1
        assert state["crash"] == 1
        assert state["baseline_value"] == 0.85
        assert state["current_value"] == 0.872
        assert state["best_value"] == 0.872
        assert len(state["recent"]) == 4


def test_parse_state_empty():
    """Should handle empty results.tsv (no experiments yet)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        (research / "config.yaml").write_text(
            "mode: collaborative\n"
            "metrics:\n"
            "  primary:\n"
            "    name: ''\n"
            "    direction: ''\n"
        )
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        )
        (research / "project-understanding.md").write_text("<!-- empty -->")
        (research / "evaluation.md").write_text("<!-- empty -->")

        state = parse_research_state(Path(tmpdir))
        assert state["total"] == 0
        assert state["phase"] == 1  # project understanding not filled
