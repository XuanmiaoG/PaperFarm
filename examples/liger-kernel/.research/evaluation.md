# Evaluation Design

## Primary Metric
- **Name:** speedup_ratio
- **Direction:** higher_is_better
- **How to measure:** Run kernel benchmark, compute ratio of PyTorch time / Triton time

## Evaluation Command
```bash
python benchmark/benchmark_rms_norm.py 2>&1 | grep "speedup" | awk '{print $NF}'
```

## Secondary Metrics
- `memory_savings_pct` — Memory reduction vs PyTorch baseline
- `numerical_error` — Max absolute difference from PyTorch output (must stay < 1e-5)
