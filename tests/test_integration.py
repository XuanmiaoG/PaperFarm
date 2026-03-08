import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from open_researcher.init_cmd import do_init
from open_researcher.status_cmd import parse_research_state
from open_researcher.results_cmd import load_results
from open_researcher.export_cmd import generate_report


def test_full_workflow():
    """Test init -> record -> status -> results -> export."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup git repo with a commit
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, "train.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True)

        repo = Path(tmpdir)

        # 1. Init
        do_init(repo, tag="test1")
        assert (repo / ".research" / "program.md").exists()
        assert (repo / ".research" / "scripts" / "record.py").exists()

        # 2. Simulate agent filling in config
        config_path = repo / ".research" / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["metrics"]["primary"]["name"] = "accuracy"
        config["metrics"]["primary"]["direction"] = "higher_is_better"
        config_path.write_text(yaml.dump(config))

        # 3. Record baseline
        record_script = repo / ".research" / "scripts" / "record.py"
        result = subprocess.run(
            [sys.executable, str(record_script),
             "--metric", "accuracy", "--value", "0.85",
             "--status", "keep", "--desc", "baseline"],
            cwd=tmpdir, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"record failed: {result.stderr}"

        # 4. Record an experiment
        result = subprocess.run(
            [sys.executable, str(record_script),
             "--metric", "accuracy", "--value", "0.87",
             "--secondary", '{"f1": 0.86}',
             "--status", "keep", "--desc", "increase LR"],
            cwd=tmpdir, capture_output=True, text=True,
        )
        assert result.returncode == 0

        # 5. Check status
        state = parse_research_state(repo)
        assert state["total"] == 2
        assert state["keep"] == 2
        assert state["current_value"] == 0.87
        assert state["baseline_value"] == 0.85

        # 6. Check results
        rows = load_results(repo)
        assert len(rows) == 2

        # 7. Check export
        report = generate_report(repo)
        assert "accuracy" in report
        assert "baseline" in report
        assert "increase LR" in report
