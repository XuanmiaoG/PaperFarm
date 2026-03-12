"""Token tracking, cost estimation, and budget management."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Task 1: TokenMetrics and TokenLedger
# ---------------------------------------------------------------------------


@dataclass
class TokenMetrics:
    """Token usage counters for a single agent invocation."""

    tokens_input: int = 0
    tokens_output: int = 0

    @property
    def tokens_total(self) -> int:
        return self.tokens_input + self.tokens_output

    def add(self, other: TokenMetrics) -> TokenMetrics:
        """Return a new TokenMetrics that is the sum of self and other."""
        return TokenMetrics(
            tokens_input=self.tokens_input + other.tokens_input,
            tokens_output=self.tokens_output + other.tokens_output,
        )

    def to_dict(self) -> dict:
        return {
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_total": self.tokens_total,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TokenMetrics:
        return cls(
            tokens_input=d.get("tokens_input", 0),
            tokens_output=d.get("tokens_output", 0),
        )


@dataclass
class TokenLedger:
    """Accumulates token usage across phases and experiments within a session."""

    cumulative: TokenMetrics = field(default_factory=TokenMetrics)
    per_phase: dict[str, TokenMetrics] = field(default_factory=dict)
    per_experiment: dict[int, TokenMetrics] = field(default_factory=dict)

    def record(
        self,
        metrics: TokenMetrics,
        phase: str,
        experiment_num: int | None = None,
    ) -> None:
        """Accumulate *metrics* into cumulative, per-phase, and (optionally) per-experiment buckets."""
        self.cumulative = self.cumulative.add(metrics)

        if phase in self.per_phase:
            self.per_phase[phase] = self.per_phase[phase].add(metrics)
        else:
            self.per_phase[phase] = TokenMetrics(metrics.tokens_input, metrics.tokens_output)

        if experiment_num is not None:
            if experiment_num in self.per_experiment:
                self.per_experiment[experiment_num] = self.per_experiment[experiment_num].add(metrics)
            else:
                self.per_experiment[experiment_num] = TokenMetrics(metrics.tokens_input, metrics.tokens_output)

    def to_dict(self) -> dict:
        return {
            "cumulative": self.cumulative.to_dict(),
            "per_phase": {k: v.to_dict() for k, v in self.per_phase.items()},
            # JSON requires string keys; convert int keys to str
            "per_experiment": {str(k): v.to_dict() for k, v in self.per_experiment.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> TokenLedger:
        return cls(
            cumulative=TokenMetrics.from_dict(d.get("cumulative", {})),
            per_phase={k: TokenMetrics.from_dict(v) for k, v in d.get("per_phase", {}).items()},
            # Restore int keys from the string-keyed JSON representation
            per_experiment={int(k): TokenMetrics.from_dict(v) for k, v in d.get("per_experiment", {}).items()},
        )
