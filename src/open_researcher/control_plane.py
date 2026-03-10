"""Linearizable control-plane commands for .research/control.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from filelock import FileLock

from open_researcher.storage import atomic_write_json

ControlCommand = Literal["pause", "resume", "skip_current", "clear_skip"]

_VALID_COMMANDS: tuple[ControlCommand, ...] = (
    "pause",
    "resume",
    "skip_current",
    "clear_skip",
)
_IDEMPOTENCY_WINDOW = 64


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_control() -> dict:
    return {
        "paused": False,
        "skip_current": False,
        "control_seq": 0,
        "applied_command_ids": [],
    }


def _load_control(ctrl_path: Path) -> dict:
    default = _default_control()
    if not ctrl_path.exists():
        return default
    try:
        payload = json.loads(ctrl_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default
    if not isinstance(payload, dict):
        return default

    merged = dict(payload)
    merged["paused"] = bool(merged.get("paused", False))
    merged["skip_current"] = bool(merged.get("skip_current", False))
    seq = merged.get("control_seq", 0)
    try:
        merged["control_seq"] = max(int(seq), 0)
    except (TypeError, ValueError):
        merged["control_seq"] = 0

    ids = merged.get("applied_command_ids", [])
    if not isinstance(ids, list):
        ids = []
    merged["applied_command_ids"] = [str(item) for item in ids if str(item).strip()][
        -_IDEMPOTENCY_WINDOW:
    ]
    return merged


def read_control(ctrl_path: Path) -> dict:
    """Read control.json under lock with backward-compatible defaults."""
    lock = FileLock(str(ctrl_path) + ".lock")
    with lock:
        return _load_control(ctrl_path)


def _apply_locked_command(
    ctrl: dict,
    *,
    command: ControlCommand,
    seq: int,
    source: str,
    reason: str | None,
    command_id: str | None,
) -> dict:
    if command not in _VALID_COMMANDS:
        raise ValueError(f"Unsupported control command: {command!r}")
    if seq <= 0:
        raise ValueError(f"control sequence id must be positive, got {seq!r}")

    current_seq = int(ctrl.get("control_seq", 0))
    normalized_id = str(command_id or "").strip()
    applied_ids = list(ctrl.get("applied_command_ids", []))

    if normalized_id and normalized_id in applied_ids:
        return {
            "applied": False,
            "duplicate_suppressed": True,
            "out_of_order": False,
            "control_seq": current_seq,
            "command_id": normalized_id,
        }

    if seq <= current_seq:
        return {
            "applied": False,
            "duplicate_suppressed": True,
            "out_of_order": True,
            "control_seq": current_seq,
            "command_id": normalized_id,
        }

    if command == "pause":
        ctrl["paused"] = True
        if reason:
            ctrl["pause_reason"] = str(reason)
    elif command == "resume":
        ctrl["paused"] = False
        ctrl.pop("pause_reason", None)
    elif command == "skip_current":
        ctrl["skip_current"] = True
    elif command == "clear_skip":
        ctrl["skip_current"] = False

    ctrl["control_seq"] = int(seq)
    ctrl["last_command"] = command
    ctrl["last_command_source"] = str(source).strip() or "unknown"
    ctrl["last_command_id"] = normalized_id
    ctrl["updated_at"] = _now_iso()

    if normalized_id:
        applied_ids.append(normalized_id)
        ctrl["applied_command_ids"] = applied_ids[-_IDEMPOTENCY_WINDOW:]

    return {
        "applied": True,
        "duplicate_suppressed": False,
        "out_of_order": False,
        "control_seq": int(ctrl["control_seq"]),
        "command_id": normalized_id,
    }


def apply_control_command(
    ctrl_path: Path,
    *,
    command: ControlCommand,
    seq: int,
    source: str,
    reason: str | None = None,
    command_id: str | None = None,
) -> dict:
    """Apply a command with an explicit sequence id under lock."""
    lock = FileLock(str(ctrl_path) + ".lock")
    with lock:
        ctrl = _load_control(ctrl_path)
        result = _apply_locked_command(
            ctrl,
            command=command,
            seq=seq,
            source=source,
            reason=reason,
            command_id=command_id,
        )
        atomic_write_json(ctrl_path, ctrl)
    return {**result, "state": ctrl}


def issue_control_command(
    ctrl_path: Path,
    *,
    command: ControlCommand,
    source: str,
    reason: str | None = None,
    command_id: str | None = None,
) -> dict:
    """Issue the next monotonic command id and apply atomically."""
    lock = FileLock(str(ctrl_path) + ".lock")
    with lock:
        ctrl = _load_control(ctrl_path)
        next_seq = int(ctrl.get("control_seq", 0)) + 1
        result = _apply_locked_command(
            ctrl,
            command=command,
            seq=next_seq,
            source=source,
            reason=reason,
            command_id=command_id,
        )
        atomic_write_json(ctrl_path, ctrl)
    return {**result, "state": ctrl}
