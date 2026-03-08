# Open Researcher 设计文档

## 定位

Python CLI 框架，为任意 repo 生成自动化研究工作流模板和 git 辅助脚本。不调用 LLM API，所有智能工作由外部 agent（如 opencode）执行。

## 核心需求

1. 通用 repo 支持 — 不要求特定格式，agent 自动理解项目
2. 自动 evaluation 设计 — agent 分析 repo 后生成评估方案，人可干预
3. 自动研究循环 — 选方向 → 修改代码 → 跑实验 → 评估 → keep/discard
4. Git 版本管理 — 分支隔离、keep/discard 模式、实验记录
5. 可配置干预模式 — autonomous（自主）/ collaborative（协作）
6. 进度展示 — CLI status 命令 + Web dashboard

## 架构

```
open-researcher（CLI 框架）
├── init          → 初始化 .research/ 目录（模板 + 脚本）
├── status        → 终端进度展示
├── dashboard     → Web 仪表板（FastAPI + Jinja2 + Chart.js）
├── results       → 格式化打印 results.tsv
└── export        → 导出实验报告
```

### .research/ 目录结构

```
.research/
├── program.md                ← agent 指令（核心工作流）
├── project-understanding.md  ← agent 填写的项目理解
├── evaluation.md             ← agent 填写的评估设计
├── results.tsv               ← 实验记录
├── config.yaml               ← 模式/环境配置
├── run.log                   ← 最近一次实验的输出
└── scripts/
    ├── record.py             ← 记录实验结果
    └── rollback.sh           ← 回滚失败实验
```

## program.md 多阶段工作流

### 阶段 1：理解项目
- Agent 读取所有源文件、文档、配置
- 分析项目目标、代码结构、测试机制、依赖
- 输出到 `.research/project-understanding.md`
- collaborative 模式下等待人确认

### 阶段 2：设计评估体系
- 基于项目理解设计可量化的评估指标
- 定义主要指标（决定 keep/discard）和辅助指标
- 设计评估脚本实现方式
- 输出到 `.research/evaluation.md`
- 更新 `config.yaml` 中的 metrics 配置
- collaborative 模式下等待人确认

### 阶段 3：建立基线
- 运行当前代码获取 baseline 指标
- 记录到 results.tsv
- 创建 git 分支 `research/<tag>`

### 阶段 4：实验循环
1. 查看 git 状态和 results.tsv
2. 提出实验想法
3. git commit 修改
4. 运行实验，输出重定向到 .research/run.log
5. 用 evaluation.md 定义的方法提取指标
6. 调用 scripts/record.py 记录
7. 改善 → keep；未改善 → scripts/rollback.sh
8. 回到 1

## Git 管理

### 分支策略
- 每轮研究创建 `research/<tag>` 分支
- 分支历史只保留 keep 的 commit
- discard 的实验通过 git reset 回滚，但记录保留在 results.tsv

### results.tsv 格式
```
timestamp	commit	primary_metric	metric_value	secondary_metrics	status	description
```
- 7 列：时间戳、commit hash、指标名、指标值、辅助指标(JSON)、状态、描述

### 辅助脚本
- `record.py`：追加实验记录到 results.tsv（自动获取 commit hash 和时间戳）
- `rollback.sh`：git reset --hard HEAD~1

## 进度展示

### CLI status
读取 .research/ 文件，展示：当前阶段、实验统计（总数/keep/discard/crash）、主要指标趋势、最近实验列表

### Web dashboard
FastAPI + Jinja2 + Chart.js：
- 概览页：阶段、统计、指标趋势图
- 实验历史：表格 + 折线图
- 文档查看：project-understanding.md、evaluation.md
- Git 历史可视化

## config.yaml

```yaml
mode: autonomous  # autonomous | collaborative
experiment:
  timeout: 600
  max_consecutive_crashes: 3
metrics:
  primary:
    name: ""
    direction: ""  # higher_is_better | lower_is_better
environment: |
  # 用户自定义执行环境描述
```

## 项目结构

```
open-researcher/
├── pyproject.toml
├── src/
│   └── open_researcher/
│       ├── __init__.py
│       ├── cli.py              # Typer CLI 入口
│       ├── init.py             # init 命令
│       ├── status.py           # status 命令
│       ├── results.py          # results 命令
│       ├── dashboard/
│       │   ├── app.py          # FastAPI
│       │   ├── templates/
│       │   └── static/
│       ├── templates/          # .research/ 模板
│       │   ├── program.md.j2
│       │   ├── config.yaml.j2
│       │   ├── project-understanding.md.j2
│       │   └── evaluation.md.j2
│       └── scripts/
│           ├── record.py
│           └── rollback.sh
```

## 技术选型
- CLI：Typer（简洁的 CLI 框架）
- Web：FastAPI + Jinja2 + Chart.js
- 模板引擎：Jinja2
- 打包：pyproject.toml + uv
