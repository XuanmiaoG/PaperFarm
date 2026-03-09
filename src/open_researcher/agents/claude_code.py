"""Claude Code agent adapter."""

from pathlib import Path
from typing import Callable

from open_researcher.agents import register
from open_researcher.agents.base import AgentAdapter


@register
class ClaudeCodeAdapter(AgentAdapter):
    name = "claude-code"
    command = "claude"

    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        return [self.command, "-p", "<prompt>", "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep"]

    def run(
        self,
        workdir: Path,
        on_output: Callable[[str], None] | None = None,
        program_file: str = "program.md",
    ) -> int:
        program_md = workdir / ".research" / program_file
        prompt = program_md.read_text()
        cmd = [self.command, "-p", prompt, "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep"]
        return self._run_process(cmd, workdir, on_output)
