# Open Researcher

> **Let AI agents run experiments in any repo while you sleep.**

Open Researcher is a CLI framework that sets up automated research workflows in any git repository. Point it at your project, pick an AI agent, and let it autonomously understand your code, design evaluation metrics, establish baselines, and run experiments — keeping what works, discarding what doesn't.

Unlike tools locked to specific repo formats, Open Researcher works with **any** project — ML training, performance optimization, algorithm design, or anything with measurable outcomes.

## Quick Start

```bash
pip install open-researcher

cd your-project
open-researcher init
open-researcher run --agent claude-code
# Go to sleep. Check results in the morning:
open-researcher status --sparkline
open-researcher results --chart primary
```

## How It Works

Open Researcher generates a `.research/` directory in your repo with:

| File | Purpose |
|------|---------|
| `program.md` | Agent instructions — the 4-phase research workflow |
| `config.yaml` | Mode (autonomous/collaborative), metrics, timeout |
| `project-understanding.md` | Agent fills this: what the project does |
| `evaluation.md` | Agent fills this: how to measure improvement |
| `results.tsv` | Experiment log (timestamp, commit, metrics, status) |
| `scripts/record.py` | Record experiment results |
| `scripts/rollback.sh` | Discard failed experiments |

### The 4-Phase Workflow

1. **Understand Project** — Agent reads your code, docs, tests. Writes `project-understanding.md`.
2. **Design Evaluation** — Agent defines metrics (what to optimize, how to measure). Writes `evaluation.md`.
3. **Establish Baseline** — Run current code, record baseline metrics.
4. **Experiment Loop** — Propose idea, implement, test, evaluate, keep or discard. Repeat.

Each experiment is a git commit. Successful experiments stay; failed ones are rolled back. Everything is logged in `results.tsv`.

## Supported Agents

| Agent | Command | Status |
|-------|---------|--------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `--agent claude-code` | Supported |
| [Codex CLI](https://github.com/openai/codex) | `--agent codex` | Supported |
| [Aider](https://github.com/paul-gauthier/aider) | `--agent aider` | Supported |
| [OpenCode](https://github.com/opencode-ai/opencode) | `--agent opencode` | Supported |

Auto-detection: If you don't specify `--agent`, Open Researcher will find the first installed agent.

## Commands

```bash
open-researcher init [--tag NAME]               # Initialize .research/ directory
open-researcher run [--agent NAME] [--dry-run]   # Launch AI agent with TUI dashboard
open-researcher run --multi                      # Dual-agent mode (idea + experiment)
open-researcher status [--sparkline]             # Show experiment progress
open-researcher results [--chart primary]        # Print results table or chart
open-researcher results --json                   # Export results as JSON
open-researcher export [--output FILE]           # Export markdown report
open-researcher doctor                           # Health check environment
open-researcher ideas list [--status pending]    # Manage idea pool
open-researcher config show                      # View/validate configuration
open-researcher logs [--follow] [--errors]       # View agent logs
```

## Interactive TUI Dashboard

```bash
open-researcher run --agent claude-code
```

Rich terminal dashboard with 5 tabs:

- **Overview** — Real-time experiment statistics, agent status, recent results
- **Ideas** — Idea pool with status, priority, category
- **Charts** — Metric trend visualization (plotext)
- **Logs** — Live agent output with phase coloring
- **Docs** — View project understanding, literature, evaluation design

Keyboard shortcuts: `1-5` switch tabs, `p` pause, `r` resume, `s` skip, `a` add idea, `g` GPU status, `q` quit.

## Runtime Controls

Open Researcher enforces experiment discipline at the runtime level:

- **Timeout watchdog** — Kills experiments exceeding the configured time limit
- **Crash counter** — Auto-pauses after N consecutive crashes
- **Collaborative mode** — Pauses for human review between phases
- **Parallel workers** — Run experiments across multiple GPUs simultaneously

## Comparison with autoresearch

| Feature | autoresearch | Open Researcher |
|---------|-------------|-----------------|
| Works with any repo | Fixed 3-file format | Any git repo |
| Agent support | Claude Code only | Claude Code, Codex, Aider, OpenCode |
| Auto project understanding | Manual | Agent-driven |
| Auto evaluation design | Manual | Agent-driven |
| Interactive TUI dashboard | No | 5-tab terminal dashboard |
| Terminal charts | No | plotext metric trends |
| Runtime controls | No | Timeout, crash limit, collaborative mode |
| Parallel experiments | No | Multi-GPU worker orchestration |
| Health checks | No | `doctor` command |
| Intervention modes | Autonomous only | Autonomous + Collaborative |
| `pip install` | No | Yes |

## Configuration

Edit `.research/config.yaml`:

```yaml
mode: autonomous          # autonomous | collaborative
experiment:
  timeout: 600            # seconds per experiment before kill
  max_consecutive_crashes: 3
  max_parallel_workers: 0  # 0 = auto (one per GPU), 1 = serial
metrics:
  primary:
    name: ""              # filled by agent (e.g., "test_acc")
    direction: ""         # higher_is_better | lower_is_better
environment: |
  # Describe your execution environment
  # e.g., Python 3.11, CUDA 12.1, 1x A100
```

## Platform Support

macOS, Linux, and Windows (Python 3.10+).

## Examples

See [`examples/`](examples/) for complete demo setups:

- **Triton Kernel Optimization** — Optimize GPU kernels in [Liger-Kernel](https://github.com/linkedin/Liger-Kernel)
- **NLP Model Training** — Improve [nanoGPT](https://github.com/karpathy/nanoGPT) validation loss
- **ML Fine-tuning** — Optimize HuggingFace Transformers GLUE benchmark

## Development

```bash
git clone https://github.com/open-researcher/open-researcher.git
cd open-researcher
make dev    # install with dev dependencies
make test   # run tests
make lint   # run linter
```

## License

MIT — see [LICENSE](LICENSE).
