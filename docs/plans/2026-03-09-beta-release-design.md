# Beta Release Design: "营销文案一致" 的完整 Beta

> Date: 2026-03-09
> Status: Approved
> Goal: 把 README 承诺的所有功能补齐，面向 ML 研究员、通用开发者和开源社区发布

## 背景

Codex gpt-5.4 分析报告（`analysis/daily/2026-03-09-release-readiness.md`）指出当前项目是"有前景的 alpha 原型"，但 README 承诺与实现存在明显断层。本设计将所有 P0 项补齐，达到与 README 承诺一致的 beta 质量。

## 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| Dashboard | 不做 web UI，TUI 替代 | 降低复杂度，README 改为 "Rich TUI Dashboard" |
| 图表粒度 | 实验级 | 用 results.tsv 现有数据，工作量可控 |
| 半成品能力 | 全部实现 | timeout/crash/collaborative/parallel workers |
| 平台兼容 | 跨平台 | fcntl → filelock |
| 实现路径 | 并行开发 | 4 个独立模块同时推进 |

## 模块划分

### 模块 A: TUI 多视图控制台

**目标**：将单页监控面板升级为 5-Tab 研究控制台

**架构**：
- 使用 Textual `TabbedContent` 组件
- 5 个 Tab：Overview / Ideas / Charts / Logs / Docs

**Overview Tab**：
- 保留现有 StatsBar（顶部）+ HotkeyBar（底部）
- ExperimentStatusPanel 增加 sparkline mini 图
- 最近 5 次实验摘要（从 results.tsv 读取）
- 当前 agent 状态 + phase 信息

**Ideas Tab**：
- 列表视图 + 右侧详情面板（master-detail）
- 状态过滤：pending / running / done / skipped
- Category 过滤：general / architecture / training / data / regularization / infrastructure
- 支持编辑 description、priority、category
- 支持删除 idea
- 显示关联的 experiment 结果

**Charts Tab**：
- 使用 `textual-plotext` 绘制实验级 metric 趋势图
- X 轴 = 实验序号，Y 轴 = primary metric value
- 数据点着色：keep=绿、discard=红、crash=黄
- 水平标注线：baseline、best
- 支持 secondary metrics overlay（如果 results.tsv 中有数据）

**Logs Tab**：
- 实时 agent 日志流（替代当前嵌入主页的 RichLog）
- 搜索功能（`/` 键触发）
- 按 agent 过滤（idea_agent / experiment_agent / single agent）
- 错误行高亮

**Docs Tab**：
- 只读查看 .research/ 下的 markdown 文件
- 文件选择列表：project-understanding.md / literature.md / evaluation.md / ideas.md
- 使用 Textual 的 `Markdown` widget 渲染

**快捷键体系**：
- `1-5` 切换 Tab
- `/` 全局搜索（在 Ideas 和 Logs Tab 中生效）
- `f` 打开过滤器
- `Enter` 查看详情
- `Esc` 返回上级
- 保留现有操作键：`p` pause, `r` resume, `s` skip, `a` add idea, `g` GPU, `q` quit

**新增依赖**：`textual-plotext` (MIT)

**影响范围**：仅 `tui/` 目录

---

### 模块 B: CLI 图表 + 子命令补全

**目标**：补全命令行图表和缺失的 CLI 子命令

#### 图表命令

`results --chart [METRIC]`：
- 使用 `plotext` 在终端绘制折线图
- 默认绘制 primary metric
- 支持指定 secondary metric 名称
- 数据点标注：keep=绿、discard=红、crash=黄
- baseline/best 水平参考线
- `--last N` 只显示最近 N 次实验
- `--normalize` 归一化多指标叠加

`status --sparkline`：
- 在 status Panel 底部追加一行 mini sparkline
- 使用 plotext 或简单 Unicode block 字符

`results --json`：
- 输出机器可读的 JSON 格式

#### 新增子命令

`doctor`：
- 检查项清单：
  - 当前目录是否为 git 仓库
  - `.research/` 是否存在且结构完整
  - agent binary 是否在 PATH 中
  - results.tsv / idea_pool.json / activity.json 是否可解析
  - config.yaml 是否有效
  - Python 版本 >= 3.10
  - 写权限检查
- 输出格式：`[OK]` / `[WARN]` / `[FAIL]` 逐项报告

`ideas`：
- `ideas list [--status STATUS] [--category CAT]`
- `ideas add "description" [--category CAT] [--priority N]`
- `ideas edit IDEA_ID --description/--priority/--category`
- `ideas delete IDEA_ID`
- `ideas prioritize` — 按 priority 排序显示

`config`：
- `config show` — 显示当前配置
- `config set KEY VALUE` — 修改配置字段
- `config validate` — 校验配置完整性

`logs`：
- `logs [--follow]` — 查看/tail 日志
- `logs --agent NAME` — 按 agent 过滤
- `logs --errors` — 只看错误行

**新增依赖**：`plotext` (MIT)

**影响范围**：`cli.py` + 新增 `doctor_cmd.py`、`ideas_cmd.py`、`config_cmd.py`、`logs_cmd.py`

---

### 模块 C: Runtime 控制面

**目标**：把 prompt 模板中定义的控制能力在 Python runtime 中真正执行

#### Timeout Watchdog

- 在 `_launch_agent_thread` 中启动 watchdog 守护线程
- 从 `config.yaml` 读取 `experiment.timeout`（默认 600s）
- 检测方式：monitoring `experiment_progress.json` 中的 `experiment_started_at` 字段
- 超时动作：`os.killpg` 终止 agent 进程，通过 `record.py` 记录 crash，rollback
- TUI 通知用户

#### Crash Counter

- 在 `run_cmd.py` 的实验循环中维护 `consecutive_crash_count`
- 数据源：每次循环后检查 `results.tsv` 最后一行的 status
- 达到 `max_consecutive_crashes`（默认 3）后：
  - 设置 `control.json` 的 `paused=true`
  - TUI 显示告警通知
  - 等待用户 `[r]` resume 后重置计数

#### Collaborative Mode

- 监听 `experiment_progress.json` 的 `phase` 字段变化
- Phase 1→2、2→3、3→4 切换时自动设置 `control.json` 的 `paused=true`
- TUI 显示 "Phase X 完成 — 按 [r] 确认并继续"
- Agent 端：模板已有 `if mode: collaborative → stop` 指令
- Runtime 端：在 agent 进程 idle 时检查 control.json，强制不启动下一个 session

#### Parallel Workers (GPU orchestration)

- `run` 启动时调用 `GPUManager.refresh()` 检测可用 GPU
- 读取 `config.yaml` 的 `max_parallel_workers` 和 `gpu.remote_hosts`
- 每个 worker = 一个线程 + 独立 git worktree（`.research/worktrees/worker-N/`）
- Worker 生命周期：
  1. `IdeaPool.claim_idea(worker_id)` 原子领取任务
  2. 在 worktree 中执行实验
  3. 结果记录到主 `results.tsv`（文件锁保护）
  4. 成功则 cherry-pick 到主分支，失败则丢弃 worktree
  5. 释放 GPU，领取下一个任务
- TUI 中 Overview Tab 显示每个 worker 的状态

**影响范围**：`run_cmd.py`、`agents/base.py`、`gpu_manager.py`

---

### 模块 D: 健壮性 + 跨平台 + 测试

#### 并发修正

`ActivityMonitor.update()`：
- 改为类似 `IdeaPool._atomic_update` 的模式
- 锁包住完整的 read → modify → write 周期

`GPUManager`：
- 所有读写操作加文件锁
- `allocate()` 和 `allocate_group()` 原子化

`_has_pending_ideas()`：
- 改用 `IdeaPool(path).summary()` 的原子读取

#### 跨平台（fcntl → filelock）

- 新增依赖 `filelock` (Unlicense)
- `activity.py`：替换 `fcntl.flock` 为 `FileLock`
- `idea_pool.py`：替换 `fcntl.flock` 为 `FileLock`
- `gpu_manager.py`：新增 `FileLock`

#### 数据容错

`status_cmd.py`：
- `float(r["metric_value"])` 包裹 try/except，坏值降级为 `N/A`
- 损坏的 TSV 行跳过并 log warning

`results_cmd.py`：
- 缺字段时显示 `<missing>` 而非崩溃
- 行数不一致时 warning

`export_cmd.py`：
- config.yaml 不存在时 graceful 降级
- 新增 `--output FILE` 选项

`init_cmd.py`：
- 前置校验：当前目录是否为 git 仓库
- 非 git 目录给出清晰错误信息和建议

#### TUI 错误处理

- `except: pass` 改为 `except Exception as e: self._log_error(e)`
- 内部 error 记录到 `.research/tui_errors.log`
- 关键错误通过 `self.notify()` 提示用户

#### 测试补充

- 坏数据 resilience：损坏 JSON、损坏 TSV、空文件、超大文件
- 并发竞争：多线程同时写 idea_pool、activity
- TUI 集成：`async with app.run_test()` 测试 Tab 切换、快捷键
- Timeout/crash 场景测试
- Doctor 命令测试
- Cross-platform：CI 中加 Windows runner

**新增依赖**：`filelock` (Unlicense)

**影响范围**：`activity.py`、`idea_pool.py`、`gpu_manager.py`、`status_cmd.py`、`results_cmd.py`、`export_cmd.py`、`init_cmd.py`、`tui/app.py`、`tests/`

---

## 新增依赖汇总

| 包 | 版本要求 | 用途 | 许可证 | 安装体积 |
|---|---------|------|--------|---------|
| `plotext` | >=5.3 | CLI 终端图表 | MIT | ~200KB，无子依赖 |
| `textual-plotext` | >=1.0 | TUI 图表 widget | MIT | ~30KB，依赖 plotext |
| `filelock` | >=3.12 | 跨平台文件锁 | Unlicense | ~20KB，无子依赖 |

## README 变更

1. `dashboard` 命令改为描述 TUI dashboard（去掉 web UI / Chart.js）
2. 对比表 "Web dashboard ❌" → "Interactive TUI dashboard ✅"
3. 新增命令文档：`doctor`、`ideas`、`config`、`logs`
4. 新增 `--chart` / `--sparkline` / `--json` 选项文档
5. 添加 TUI 截图（多 Tab 视图）
6. 添加平台支持说明：macOS / Linux / Windows

## 模块间接口约定

| 共享接口 | 格式 | 提供方 | 消费方 |
|---------|------|--------|--------|
| `results.tsv` | TSV | 不变 | B(图表), A(Charts Tab) |
| `idea_pool.json` | JSON + filelock | D(修正) | A(Ideas Tab), C(worker claim) |
| `activity.json` | JSON + filelock | D(原子更新) | A(Overview), C(worker status) |
| `control.json` | JSON | 不变 | A(pause/resume), C(collaborative) |
| `config.yaml` | YAML | 不变 | C(timeout/crash/workers) |
| `experiment_progress.json` | JSON | C(写入) | C(collaborative phase gate) |
| `gpu_status.json` | JSON + filelock | C(GPUManager) | A(GPU modal) |

## 并行开发策略

每个模块在独立的 git worktree 中开发：

```
worktree/module-a-tui/       ← TUI 多视图
worktree/module-b-cli/       ← CLI 图表 + 子命令
worktree/module-c-runtime/   ← Runtime 控制面
worktree/module-d-robustness/ ← 健壮性 + 跨平台
```

合并顺序：D → C → B → A（底层先合，UI 后合，减少冲突）

## 不在此版本范围内

- Web dashboard（P2）
- Step-level loss curve（P2，需新数据结构）
- Remote GPU fleet management UI（P2）
- Agent capability registry（P2）
- Session replay（P2）
- 报告模板与 artifact bundling（P2）
