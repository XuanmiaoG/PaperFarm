# Project Understanding

## Project Goal
Liger-Kernel provides efficient Triton kernels for LLM training operations (RMSNorm, RoPE, SwiGLU, CrossEntropy, FusedLinearCrossEntropy). Each kernel replaces a PyTorch operation with a faster Triton implementation.

## Code Structure
- `src/liger_kernel/ops/` — Individual Triton kernel implementations
- `src/liger_kernel/transformers/` — Drop-in replacements for HuggingFace layers
- `benchmark/` — Performance benchmarks comparing Triton vs PyTorch
- `test/` — Correctness tests for each kernel

## How to Benchmark
```bash
python benchmark/benchmark_rms_norm.py
```
