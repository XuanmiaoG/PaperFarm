"""Tests for the core research loop extraction."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from open_researcher.config import ResearchConfig
from open_researcher.research_events import (
    AllIdeasProcessed,
    ExperimentCompleted,
    ExperimentStarted,
    IdeaAgentDone,
    IdeaCycleStarted,
    NoPendingIdeas,
)
from open_researcher.research_loop import ResearchLoop


def _setup_repo(tmp_path: Path) -> tuple[Path, Path]:
    research = tmp_path / ".research"
    research.mkdir()
    (research / "idea_program.md").write_text("# idea")
    (research / "experiment_program.md").write_text("# experiment")
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
    )
    (research / "idea_pool.json").write_text(json.dumps({"ideas": []}, indent=2))
    return tmp_path, research


def test_run_multi_agent_emits_typed_events_until_completion(tmp_path):
    repo_path, research = _setup_repo(tmp_path)
    cfg = ResearchConfig()
    events = []

    idea_call_count = {"count": 0}
    idea_agent = MagicMock()
    exp_agent = MagicMock()

    def idea_run(workdir, on_output=None, program_file="program.md", **kwargs):
        idea_call_count["count"] += 1
        if on_output:
            on_output("[idea] generating")
        if idea_call_count["count"] == 1:
            (workdir / ".research" / "idea_pool.json").write_text(
                json.dumps(
                    {
                        "ideas": [
                            {
                                "id": "idea-001",
                                "description": "Try config A",
                                "status": "pending",
                                "priority": 1,
                            }
                        ]
                    },
                    indent=2,
                )
            )
        return 0

    def exp_run(workdir, on_output=None, program_file="program.md", **kwargs):
        if on_output:
            on_output("[exp] running")
        pool_path = workdir / ".research" / "idea_pool.json"
        pool_data = json.loads(pool_path.read_text())
        for idea in pool_data["ideas"]:
            if idea["status"] == "pending":
                idea["status"] = "done"
        pool_path.write_text(json.dumps(pool_data, indent=2))
        return 0

    idea_agent.run.side_effect = idea_run
    exp_agent.run.side_effect = exp_run

    loop = ResearchLoop(repo_path, research, cfg, events.append)
    exit_codes = loop.run_multi_agent(idea_agent, exp_agent)

    assert exit_codes == {"idea": 0, "exp": 0}
    assert [type(event) for event in events if not hasattr(event, "detail")] == [
        IdeaCycleStarted,
        IdeaAgentDone,
        ExperimentStarted,
        ExperimentCompleted,
        IdeaCycleStarted,
        IdeaAgentDone,
        NoPendingIdeas,
        AllIdeasProcessed,
    ]
