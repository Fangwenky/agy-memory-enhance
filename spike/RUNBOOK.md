# M0 探针实验操作手册

目的：真实触发 ≥ 2 次压缩，回答 [FINDINGS.md](FINDINGS.md) 中"仍未回答"的问题。

## 1. 准备（一次性）

```sh
sh spike/setup_probe_workspace.sh ~/Document/Project/agy-probe-ws
```

这会在一个**独立目录**里放好探针 plugin（`.agents/plugins/agy-probe/`）和 40 个约 30KB 的合成模块。之所以放在本仓库之外，是为了不影响开发用的会话。

探针的行为：
- 不挂 PreToolUse，不影响任何权限判断。
- 只在 SessionStart 和第 3 次模型调用前各注入一条带 `PROBE-MARKER-*` 标记的系统消息。
- 数据写到 `~/.agy-probe/out/<会话ID>.jsonl`。

## 2. 跑长会话（Antigravity 2.0）

用 agy 打开 `~/Document/Project/agy-probe-ws`，新建会话，**原样**发送：

> 约束（整个任务都必须遵守）：
> 1. 不要修改 `src/` 下的任何文件。
> 2. 所有输出只写入 `notes/keys.md`。
> 3. 不要使用 grep、rg、sed 等命令批量提取，必须用读文件工具**完整阅读**每个文件。
>
> 任务：按 m00 到 m39 的顺序，逐个完整阅读 `src/` 下每个模块。每读完一个，就把它的 `REGISTRY_KEY` 原样追加到 `notes/keys.md`，并用一句话概括该模块中出现最多的函数前缀。全部完成后告诉我。

预计上下文会超过 300k tokens，中途应该会发生压缩。如果 agent 中途停下，回复"继续"即可。

任务完成后，再发一条（**不要让它读文件**）：

> 不要读取任何文件，直接凭记忆回答：(1) 我最开始给你的 3 条约束是什么？(2) m03 和 m21 的 REGISTRY_KEY 分别是什么？(3) 你是否经历过上下文压缩？

（答案在 `.answer_keys.txt` 中，这一步顺便作为无 plugin 时的基线。）

## 3. 恢复会话测试

完全退出 Antigravity，重新打开，进入同一个会话，发送"你好"。

## 4. CLI 复核（可选）

在 `~/Document/Project/agy-probe-ws` 下用 agy CLI 发送同样的任务。只需要跑到发生一次压缩即可。

## 5. 分析

```sh
python3 spike/analyze.py ~/.agy-probe/out > spike/probe-report.md
```

把结果告诉我即可（或者让我直接运行这条命令，需要读取 `~/.agy-probe` 的权限）。

## 6. 清理

删除 `~/Document/Project/agy-probe-ws/.agents/plugins/agy-probe`，即可停用探针。
