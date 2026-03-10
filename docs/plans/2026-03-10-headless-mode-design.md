# Headless Mode + Max Experiments 设计

## 需求

1. `start` 命令支持 `--headless` 模式，无 TUI，纯 CLI 输出
2. 结构化 JSON Lines 日志输出到 stdout + 文件，便于外部工具解析监控
3. 支持 `--max-experiments N` 设置实验次数上限
4. 保持 TUI 模式完全不变

## CLI 接口

```bash
# headless 模式
open-researcher start --headless --goal "improve accuracy" --max-experiments 10

# TUI 模式（不变）
open-researcher start
```

参数：
- `--headless`：无 TUI，日志输出到 stdout（JSON Lines）
- `--goal TEXT`：研究目标（headless 模式下必需）
- `--max-experiments INT`：实验次数上限（0 = 无限制，默认 0）

## Headless 流程

```
Phase 0: Bootstrap → auto-init .research/ + load config（不变）
Phase 1: Goal Input → 直接使用 --goal 参数（跳过 GoalInputModal）
Phase 2: Scout Analysis → 同步运行 Scout，JSON Lines 输出
Phase 3: Human Review → 跳过（自动确认），输出 Scout 摘要
Phase 4: Experiments → 循环执行，到达 max_experiments 停止
```

## 结构化日志（JSON Lines）

每行一个 JSON 对象：

```json
{"ts": "2025-03-10T12:34:56Z", "level": "info", "phase": "scouting", "event": "agent_started", "detail": "Scout agent analyzing project"}
{"ts": "2025-03-10T12:45:00Z", "level": "info", "phase": "experimenting", "event": "experiment_completed", "idea": "idea-001", "metric_value": 0.95, "verdict": "kept", "experiment_num": 3, "max_experiments": 10}
{"ts": "2025-03-10T12:50:00Z", "level": "info", "phase": "done", "event": "limit_reached", "detail": "Max experiments (10) reached"}
```

事件类型：session_started, scout_started, scout_completed, doc_updated, experiment_started, experiment_completed, experiment_failed, limit_reached, session_completed, agent_output

## 文件改动

| 文件 | 改动 |
|------|------|
| cli.py | start 命令新增 --headless, --goal, --max-experiments |
| start_cmd.py | do_start() 分支到 headless 路径 |
| headless.py | 新文件：HeadlessLogger + do_start_headless() |
| run_cmd.py | dual-agent 循环增加 max_experiments 计数 |
| config.py | ResearchConfig 增加 max_experiments 字段 |
| templates/config.yaml.j2 | 增加 max_experiments 默认值 |

不改动：tui/、agents/、JSON 协调文件格式
