# M2 端到端测试手册（装有 agy-memory）

目的：
1. 在真实 agy 中验证 hook、`mem` 命令和 skill 能串起来工作。
2. 观察压缩后 agent 是否加载 skill 并按规程对齐。
3. 用"中途追加约束 + 来自工具输出的精确事实"做一次比 M0 更难的回忆测试。

## 准备（已由 agent 完成）

`~/Document/Project/agy-memory-e2e` 是一个新的测试目录，里面包含：
- 40 个合成模块；
- agy-memory plugin（`.agents/plugins/agy-memory/`）；
- 探针（`.agents/plugins/agy-probe/`，用于事后分析）。

答案文件已移出测试目录。

## 步骤

用 agy 打开 `~/Document/Project/agy-memory-e2e`，新建会话，**分 4 条消息**依次发送。每条都等 agent 完成后再发下一条。

**消息 1**
```
约束：不要修改 src/ 下的任何文件；不要使用 grep、rg、sed 等命令批量提取，必须用读文件工具完整阅读每个文件。
任务第一阶段：按顺序完整阅读 src/m00.py 到 src/m09.py，读完后告诉我每个模块的 REGISTRY_KEY。不要把结果写进任何文件。
```

**消息 2**
```
追加一条约束：从现在起，所有回复必须用英文。
另外，从现在起，每个模块除了 REGISTRY_KEY，还要告诉我该文件中最后一个函数的函数名。
第二阶段：完整阅读 src/m10.py 到 src/m24.py。
```

**消息 3**
```
第三阶段：完整阅读 src/m25.py 到 src/m39.py，规则同上。
```

**消息 4**（不要让它读任何文件）
```
不要读取任何源文件，凭记忆回答：(1) 我总共给过你哪些约束？分别是什么时候给的？(2) m03 和 m21 的 REGISTRY_KEY 是什么？(3) m12 的最后一个函数叫什么？(4) 你经历过上下文压缩吗？压缩后你做了什么？
```

预计在第二、三阶段之间会发生压缩，Claude 模型的阈值目前未知。如果读完 m39 仍未压缩，告诉我即可。

## 观察要点（可选）
- 会话开头是否出现 `[agy-memory] Project memory is enabled` 的系统消息。
- agent 是否主动 `mem add` 约束。
- 压缩后 agent 是否加载 agy-memory skill，并执行 `mem brief` / `mem search` 等命令。
- 是否出现 Stop 收尾提醒。由于不写文件，大概率不会出现。

## 完成后
回到开发会话说"e2e 跑完了"。agent 会运行分析脚本、检查 `.agy-memory/` 并核对答案。
