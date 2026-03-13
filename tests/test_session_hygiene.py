import json

from open_researcher.control_plane import issue_control_command, read_control
from open_researcher.session_hygiene import reset_runtime_session_state


def test_reset_runtime_session_state_clears_stale_control_and_workers(tmp_path):
    research = tmp_path / ".research"
    research.mkdir()
    ctrl_path = research / "control.json"
    activity_path = research / "activity.json"

    issue_control_command(ctrl_path, command="pause", source="test", reason="stale pause")
    issue_control_command(ctrl_path, command="skip_current", source="test", reason="stale skip")
    activity_path.write_text(
        json.dumps(
            {
                "experiment_agent": {
                    "status": "running",
                    "detail": "2 active worker(s)",
                    "active_workers": 2,
                    "workers": [
                        {"id": "worker-0", "status": "running"},
                        {"id": "worker-1", "status": "idle"},
                    ],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = reset_runtime_session_state(research, source="test_session")

    assert summary["changed"] is True
    assert summary["resumed"] is True
    assert summary["cleared_skip"] is True
    assert summary["cleared_workers"] is True
    assert summary["stale_workers"] == 2

    ctrl = read_control(ctrl_path)
    assert ctrl["paused"] is False
    assert ctrl["skip_current"] is False

    activity = json.loads(activity_path.read_text(encoding="utf-8"))
    entry = activity["experiment_agent"]
    assert entry["workers"] == []
    assert entry["active_workers"] == 0
    assert entry["status"] == "idle"
    assert entry["detail"] == "0 active worker(s)"
