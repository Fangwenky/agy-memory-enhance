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
