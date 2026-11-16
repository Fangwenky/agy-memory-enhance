# M0 实验发现（进行中）

## 方式二：分析历史会话（2026-11-16）

**结论：本机没有发生过压缩的历史会话，无法从历史数据中确认压缩信号。** 仍需方式一（探针 plugin + 长会话）。

### 样本
- `~/.gemini/antigravity/brain/` 下只有 3 个会话：当前会话、它的 reviewer 子会话，以及一个 11-02 的会话。
- 11-02 的会话共 49 步、20 次模型调用，总上下文峰值约 57k tokens，远低于社区报告的压缩阈值（140k–276k）。

### 有价值的发现

1. **`input_tokens` 只计未命中缓存的部分。** 示例：
   - step 43：`input_tokens=636`，`cache_read_tokens=56325`；
   - step 48：`input_tokens=52533`，`cache_read_tokens=4633`（缓存失效）。

   因此**上下文大小 ≈ `input_tokens + cache_read_tokens`**。只看 `input_tokens` 会因为缓存命中率波动而大量误报压缩。设计 §7.3 已据此修正。
2. **transcript 的 step 类型**（`source`, `type`）有以下几种：
   - `USER_EXPLICIT/USER_INPUT`
   - `MODEL/PLANNER_RESPONSE`，带 token 字段和 `tool_calls`
   - `MODEL/GENERIC`，工具结果
   - `SYSTEM/SYSTEM_MESSAGE`

   注入的 systemMessage 会以 `SYSTEM_MESSAGE` 形式出现在 transcript 中，可以用它判断"我们之前的注入是否还在"。
3. **transcript 有两个版本**：`transcript.jsonl`（长字段截断，带 `truncated_fields`）和 `transcript_full.jsonl`。按指针取原文时应读 full 版本。
4. **agy 真正的存储是 `~/.gemini/antigravity/conversations/<convId>.db`**：SQLite，`steps` 表里存的是 protobuf blob，还有 `gen_metadata`、`executor_metadata` 等表。这是内部格式，**不依赖它**；`transcript.jsonl` 是由它导出的视图。
5. 默认沙箱下无法读取 `~/.gemini/antigravity/brain/`，hook 进程是否受同样限制，需在探针实验中确认。

### 仍未回答（需方式一）
- 压缩时 transcript 是否只追加；是否有显式压缩标记。
- 压缩前后 `input_tokens + cache_read_tokens` 的变化幅度。
- 注入的 systemMessage 在压缩后是否保留。
- 恢复会话时 SessionStart 是否触发。
- 写文件类工具在 hook 中的名称。
- hook 进程能否读取 `transcriptPath`。

## 方式一：探针实验（2026-11-16，会话 `f9b05ad4`）

**环境**：Antigravity 2.0。工作区 `agy-probe-ws`。首轮模型为 Claude Opus 5.5，长任务期间切换到 Gemini 4 Hydrogen（payload 中的 `modelName` 为 `gemini-4-hydrogen-medium`）。共 205 步、76 次模型调用，上下文峰值 518,079 tokens，**发生 1 次压缩**。

### 6 个问题的答案

| 问题 | 结论 | 证据 |
| :-- | :-- | :-- |
| 压缩有无显式标记 | **有。** transcript 中出现一个 `source=SYSTEM, type=CHECKPOINT` 的步骤，内容以 `# Resuming from a compaction` 开头 | step 146 |
| transcript 是否只追加 | **是。** 文件从未变小，`step_index` 连续无断档；压缩前的步骤仍保留在 `transcript_full.jsonl` 中 | 探针在 352 次记录中，文件大小单调递增 |
| 上下文变化 | 518,079 → 32,201（−94%）。CHECKPOINT 步骤自带 token 字段（生成摘要本身的开销） | step 144 → 147 |
| 注入的 systemMessage 压缩后是否保留 | **不保留。** 两个探针标记只出现在 step 1 和 step 6，CHECKPOINT 摘要里没有。注入记为 `SYSTEM_SDK/SYSTEM_MESSAGE`，内容前缀为 "injected by a SessionStart/PreInvocation hook" | 标记检索 |
| 恢复会话时 SessionStart 是否触发 | **不触发。** 重启后（step 203 为服务重启通知）发送"你好"，SessionStart 总计仍为 1 次 | 事件计数 |
| 写文件类工具名 | `write_file`（另有 `read_file`、`run_command`）。本次未出现 `edit_file`，但它是现有工具，应列入 | PostToolUse 统计 |

### 其他发现

1. **hook 给的 `transcriptPath` 直接指向 `transcript_full.jsonl`**，hook 进程可以读取，不受沙箱限制。
2. **workspace 里的 plugin，`PLUGIN_DATA` 为 null**，`PLUGIN_ROOT` 正常。所以无工作区时的退回路径不能依赖 `PLUGIN_DATA`。
3. **骤降检测的误报**：step 4 处 42,976 → 27,857（−35%），并没有发生压缩，原因是会话开头切换模型、缓存重建。`minPeakTokens` 门槛能挡住这类情况，而且现在有显式标记，可以把它作为主信号。
4. **压缩阈值远高于社区报告**：本次在约 518k 时才压缩（Gemini 4 Hydrogen）。阈值显然与模型相关，固定的 `softLimitTokens=120k` 会过早、过多地预警。
5. **agy 原生的压缩摘要质量很高**。摘要约 11.7k 字符，结构如下：
   - `# User Requests`：用户原话全文；
   - `Task Overview`、`Done`、`Files Already Read`、`Code Map`、`Key Findings`、`Active Context`；
   - `Commitments & Constraints`、`Next Steps`；
   - 一组 "RESUME RULES"；
   - 指回 transcript 的链接。

   其中有一条规则值得注意："facts in it count as observed and I do not re-verify them"，也就是说摘要里的事实不再核对。**摘要一旦有误，错误就会被固化。**
6. **基线结果：完全正确。** 40 个 key 全部写对；回忆测试中 3 条约束复述准确，m03、m21 的 key 正确；agent 也知道自己经历过压缩。
   - **但这个任务对记忆的考验不够**：任务本身要求把状态写进 `notes/keys.md`，相当于自带了"外部状态文件"；约束也写在首条用户消息里，而摘要会原样保留用户请求。
   - 并且只发生了一次压缩，没有覆盖"摘要的摘要"这类叠加损失。

### 对设计的影响
- 压缩检测改为：**以 `CHECKPOINT` 步骤为主信号**，token 骤降只作为后备。
- 每次压缩后**必须重新注入**简报（已在设计中）。
- 恢复会话由 PreInvocation 兜底（已在设计中，现已确认是必需的）。
- 水位预警阈值改为**按模型学习**：记录每个 `modelName` 实际压缩时的峰值，取它的一个比例；没有观测数据时用保守默认值。
- 压缩时把 CHECKPOINT 摘要原文存入事件流。它本身就是高质量的阶段性记录，可用于长期追溯，也可以和账本对照，找出被摘要丢掉或改写的条目。
- 价值定位需要调整，见下一节。

### 价值定位再评估
在"单次压缩 + 约束写在首条消息"的场景下，原生机制已经够用。agy-memory 的增量价值应集中在原生摘要覆盖不到的地方：
1. **多次压缩**：摘要的摘要会逐步失真，账本不会。
2. **中途追加的约束和决策**：出现在后续轮次、在长对话中被稀释的那部分。
3. **跨会话**：原生摘要只存在于单个会话内。
4. **长期追溯**：例如"上周为什么这么改"。
5. **核对摘要**：原生规则禁止重新核对摘要中的事实，我们可以用账本和原文指针来抽查。

M3 的评测任务需要据此重新设计。
