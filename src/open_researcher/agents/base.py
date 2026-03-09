"""Abstract base class for AI agent adapters."""

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


class AgentAdapter(ABC):
    """Base class that all agent adapters must implement."""

    name: str
    command: str

    def __init__(self):
        self._proc: subprocess.Popen | None = None

    def check_installed(self) -> bool:
        """Return True if the agent binary is available on PATH."""
        return shutil.which(self.command) is not None

    @abstractmethod
    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        """Build the subprocess command list to launch the agent."""

    @abstractmethod
    def run(
        self,
        workdir: Path,
        on_output: Callable[[str], None] | None = None,
        program_file: str = "program.md",
    ) -> int:
        """Launch the agent, stream output via callback, return exit code."""

    def _run_process(
        self,
        cmd: list[str],
        workdir: Path,
        on_output: Callable[[str], None] | None = None,
        stdin_text: str | None = None,
    ) -> int:
        """Common subprocess execution with streaming output."""
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdin=subprocess.PIPE if stdin_text else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        if stdin_text:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        self._proc = proc
        for line in proc.stdout:
            if on_output:
                on_output(line.rstrip("\n"))
        return proc.wait()

    def terminate(self) -> None:
        """Terminate the running agent subprocess."""
        if self._proc and self._proc.poll() is None:
            try:
                os.killpg(os.getpgid(self._proc.pid), 15)
            except (OSError, ProcessLookupError):
                pass
