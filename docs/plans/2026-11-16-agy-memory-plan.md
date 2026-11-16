# agy-memory 实施计划

> 依据：[设计文档](../specs/2026-11-16-agy-memory-design.md)（已确认）
> 约定：Python 3.9+ 标准库；测试用 `unittest`（零依赖）；每个任务完成即 git commit。

## 仓库布局

```text
agy-memory-enhance/
├── docs/{specs,plans}/
├── plugin/agy-memory/          # 可直接安装的 plugin 本体（见设计 §11）
├── spike/                      # M0 实验脚本与录制样本（不随 plugin 发布）
├── tests/                      # 单元与回放测试
│   └── fixtures/
└── eval/                       # M3 评测任务与脚本
```

---

## M0 实验：确认 agy 的真实行为

目标：回答设计 §13 中的 6 个问题，并产出测试用的 fixture。

| # | 任务 | 产出 / 验证 |
| :-- | :-- | :-- |
| 0.1 | 初始化 git 仓库和目录骨架 | `git log` 有首个提交 |
| 0.2 | 写**探针 plugin** `spike/probe-plugin/`：6 个 hook 事件都挂同一个脚本 `probe.py`。脚本把 stdin payload、调用时刻、transcript 文件大小和末尾 3 行追加写入 `spike/out/<convId>.jsonl`，然后输出 `{}`（Stop 输出 `{"decision":""}`） | 装上后随便对话一轮，`spike/out/` 中能看到 6 类事件 |
| 0.3 | 写**分析脚本** `spike/analyze.py`：读取探针输出和 transcript，输出以下内容：每次调用的 `input_tokens` 曲线、transcript 字节数曲线、文件是否变小、新出现的 step type 或疑似压缩标记、PostToolUse 的工具名列表 | 用现有会话跑通 |
| 0.4 | **触发压缩**：在装有探针的 Antigravity 2.0 中跑一个长任务（例如反复 `view_file` 大文件、逐个阅读一个大仓库），至少触发 2 次压缩。中途在会话里埋一条约束和一次 systemMessage 注入（探针在第 N 次 PreInvocation 时注入一条带唯一标记的消息） | 录到 ≥ 2 次压缩 |
| 0.5 | 恢复会话测试：关闭 agy 再重新打开该会话发一句话，看 SessionStart 是否触发 | 有结论 |
| 0.6 | 在 agy CLI 上重复 0.4 的精简版 | 有结论 |
| 0.7 | 写 `spike/FINDINGS.md`：逐条回答 6 个问题；选定压缩检测方式（正常模式还是降级模式）；校准默认阈值；把脱敏后的压缩前后片段存入 `tests/fixtures/` | 文档 + fixture 提交 |

**决策点**：0.7 完成后，若需要修改设计（例如走降级模式），先更新设计文档再进入 M1。

---

## M1 采集与注入

| # | 任务 | 测试先行 |
| :-- | :-- | :-- |
| 1.1 | `plugin/agy-memory/plugin.json`、`hooks.json`（4 个事件 → 4 个脚本，timeout 5s） | 用 JSON 校验 |
| 1.2 | `hooks/common.py`：解析 stdin；定位存储目录（`workspacePaths[0]`，否则退回 `PLUGIN_DATA/projects/<hash>`）；首次创建目录时写入 `.gitignore`；`fcntl` 文件锁；JSONL 追加写；按 `redactPatterns` 脱敏；读取配置并合并默认值；读写 state | 覆盖存储定位、脱敏、并发追加（多进程）的测试 |
| 1.3 | `common.py` 中的 transcript 增量读取器：按偏移读取新增完整行；文件变小时重置；提取 `user_input`、`input_tokens` 和压缩标记（按 FINDINGS） | 用 fixture 回放：普通增长、截断/改写、半行写入 |
| 1.4 | 压缩检测与水位预警的纯函数 `detect(state, new_steps, cfg) -> (events, injections, new_state)`：峰值记录与压缩后清零、单次去重、nudge 步长、注入预算 | 表驱动测试：单次压缩、两次压缩、无压缩的大幅波动、预警的步长与预算耗尽 |
| 1.5 | `hooks/pre_invocation.py`：无 state 时做首次处理（生成 shim、注入简报）；读取增量；调用 detect；写入事件；输出 injectSteps | 子进程回放 stdin，断言输出 JSON |
| 1.6 | `hooks/session_start.py`：生成 shim、注入简报、写 state（与 1.5 共用同一个函数） | 同上 |
| 1.7 | `hooks/post_tool_use.py`：按 `editToolNames` 和 `run_command` 记录事件 | 同上；耗时 < 50ms |
| 1.8 | 性能测试：50MB 合成 transcript 上首次调用和增量调用的耗时 | 增量 < 300ms |
| 1.9 | 安装到本机 agy，跑真实会话，与 M0 录到的压缩样本做比对 | 命中率 100%，误报 0 |

简报渲染在 M1 中先用最小实现（只输出约束和进度），M2 再补完整。

---

## M2 Skill、CLI 与收尾

| # | 任务 | 验证 |
| :-- | :-- | :-- |
| 2.1 | `scripts/mem` 账本层：`add` / `done` / `supersede`；会话级条目带上 convId；id 生成；沿 supersedes 链解析出"当前有效视图" | 单元测试 |
| 2.2 | 简报渲染：设计 §6 的分段、按会话过滤、token 估算（CJK 计 1，其余 4 字符计 1）、按优先级截断 | 超限截断测试 |
| 2.3 | `brief` / `show`（含按指针从 transcript 或 gzip 多 member 归档中取原文）/ `search` / `timeline` / `session` / `doctor` | 用 fixture 测试；`doctor` 在缺少 python3 或 hook 未生效时给出提示 |
| 2.4 | `hooks/stop.py`：写入 `turn_end`（附带 `git diff --name-only`）、更新会话索引、增量追加 gzip member、收尾提醒 | 测试：多 member 拼接后可完整读取；收尾提醒在 3 个条件下的真值表 |
| 2.5 | `rules/AGENTS.md`（< 300 tokens） | 字数检查 |
| 2.6 | `SKILL.md` 与 `references/{write,align,recall}.md`：写入、对齐、检索、冲突处理四套规程，给出具体命令示例 | 人工审阅 |
| 2.7 | 端到端：在 M0 的长任务上开启 plugin 运行，观察压缩后 agent 是否加载 skill、核对约束、回原文取标识符 | 记录到 `spike/E2E.md` |

---

## M3 评测与发布

| # | 任务 | 验证 |
| :-- | :-- | :-- |
| 3.1 | `eval/tasks/`：5 个长任务。每个任务包含：初始仓库、任务说明（早期埋 3 条约束和 5 个标识符）、自动检查脚本（统计约束违反、标识符幻觉、完成度） | 每个检查脚本都有正例和反例 |
| 3.2 | `eval/run.md`：运行规程（固定模型和设置；有/无 plugin 各跑 3 次）；汇总脚本 `eval/report.py` 从 transcript 与检查结果生成表格 | 跑通 1 次 |
| 3.3 | 完成 30 次运行，生成 `eval/RESULTS.md` | 达标线：主要指标合计下降 ≥ 50%，额外 token 开销 ≤ 10% |
| 3.4 | 未达标时：根据失败案例调整规程或阈值，回到 3.3（最多 2 轮），然后如实报告 | — |
| 3.5 | `README.md`（中英双语）：安装、原理、配置、局限（含降级模式）、评测结果；LICENSE；示例截图 | — |
| 3.6 | 发布：打 tag；按 plugin 文档给出安装方式 | 在另一台机器或新用户目录上从零安装成功 |

---

## 风险与依赖

- **M0 需要用户配合**：触发压缩需要在 agy 中真实跑一个长会话。0.4–0.6 需要用户操作，或允许 agent 在一个独立会话里执行。
- **M3 成本**：30 次长任务运行会消耗大量额度。可先按 5 任务 × 1 次做小规模评测，结果有希望再扩大。
