# Example: Liger-Kernel Research

This example shows how to use Open Researcher with [linkedin/Liger-Kernel](https://github.com/linkedin/Liger-Kernel) to optimize Triton GPU kernels for LLM training.

## Setup

```bash
git clone https://github.com/linkedin/Liger-Kernel.git
cd Liger-Kernel
pip install -e ".[dev]"

# Initialize Open Researcher
open-researcher init --tag liger

# Launch research
open-researcher run --agent claude-code
```

## What the Agent Will Try

- Tiling strategy optimization
- Memory access pattern improvements
- Operator fusion techniques
- Register pressure reduction
- Autotuning configurations

## Metrics

- **Primary:** `speedup_ratio` (higher is better) — execution speed vs PyTorch baseline
- **Evaluation:** Run kernel benchmarks, compare Triton kernel throughput against PyTorch reference
