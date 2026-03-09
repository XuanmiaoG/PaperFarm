"""Activity monitor — track real-time agent status via activity.json."""

import json
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock


class ActivityMonitor:
    """Read/write activity.json for agent status tracking."""

    def __init__(self, research_dir: Path):
        self.path = research_dir / "activity.json"
        self._lock = FileLock(str(self.path) + ".lock")

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def update(self, agent_key: str, **kwargs) -> None:
        with self._lock:
            data = self._read()
            entry = data.get(agent_key, {})
            entry.update(kwargs)
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            data[agent_key] = entry
            self._write(data)

    def get(self, agent_key: str) -> dict | None:
        data = self._read()
        return data.get(agent_key)

    def update_worker(self, agent_key: str, worker_id: str, **kwargs) -> None:
        """Update or add a worker entry within an agent's activity."""
        with self._lock:
            data = self._read()
            entry = data.get(agent_key, {})
            workers = entry.get("workers", [])
            found = False
            for w in workers:
                if w["id"] == worker_id:
                    w.update(kwargs)
                    w["updated_at"] = datetime.now(timezone.utc).isoformat()
                    found = True
                    break
            if not found:
                worker = {"id": worker_id, **kwargs, "updated_at": datetime.now(timezone.utc).isoformat()}
                workers.append(worker)
            entry["workers"] = workers
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            data[agent_key] = entry
            self._write(data)

    def remove_worker(self, agent_key: str, worker_id: str) -> None:
        """Remove a worker entry."""
        with self._lock:
            data = self._read()
            entry = data.get(agent_key, {})
            workers = entry.get("workers", [])
            entry["workers"] = [w for w in workers if w["id"] != worker_id]
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            data[agent_key] = entry
            self._write(data)

    def get_all(self) -> dict:
        return self._read()
