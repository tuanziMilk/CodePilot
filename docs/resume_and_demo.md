# 项目介绍、Demo 与简历表述

## 30 秒项目介绍

CodePilot 是我从零实现的 repository-level Coding Agent。模型只负责产生结构化 ToolCall，Harness
负责参数校验、权限控制、工具执行、状态更新和最终验证。我还实现了公开 Planning、失败复现门禁、
bounded repair、lexical retrieval、阈值式 working-context compaction 和独立 Evaluation Runner，
用固定 Git baseline、额外验收与 diff audit 比较 Agent 配置，而不是只展示一次成功 Demo。

## 简历版本

**CodePilot｜可复现评估的 Coding Agent｜Python / Pydantic / Git / DeepSeek API**

- 从零实现 Provider-neutral Agent Harness，将 LLM 输出统一为内部 `ToolCall`，完成参数校验、
  ToolResult observation、max-step termination、测试失败反馈与 external verification；区分 Provider
  请求重试和任务级 bounded repair。
- 实现 Workspace 路径边界、允许文件审计、受限 Git Bash、精确编辑与 JSONL trajectory，记录
  Git commit、Token、latency、退出码和状态变化，同时避免持久化 API Key 与私有 Chain-of-Thought。
- 构建 21 个固定 Git 故障基线及独立 acceptance tests，其中 6 题要求跨 2–3 个文件维护契约；对
  Basic、Reliable、Retrieval、Full 四组配置进行自动化评测；6-task hard-v2 候选实验达到 24/24
  strict success，Lexical Retrieval Hit@3=100%、reference-file recall@K=61.1%。
- 在 hard-v2 实验中，Full 相较 Basic 平均 Tokens 减少 10.7%、latency 减少 17.3%、文件读取减少
  19.6%；通过 trajectory 识别并修复 step-limit 误判，并分析 permission denial、Provider retry
  与轻微过度修改等 failure modes。
- 分离完整审计历史与 Provider working context；在12-case强制触发消融中保持100% strict success，
  观察到输入 Token 少22.1%、latency少13.9%，同时用直接字符指标和重复读取分析限定因果解释。

最后一条必须和限定条件一起理解：只有 6 个独立任务且每配置只运行一次，不能写成统计显著或一般化
性能提升。正式投递前应从 clean commit 重跑一次并替换候选数字。如果希望
简历更保守，可改为：

> 通过 2×2 ablation 记录成功率、Steps、Token、latency、Retrieval Hit@K 与权限拒绝，并结合
> trajectory 分析检索收益、重复计划和提前终止等典型失败模式。

不要写“生产级 sandbox”“媲美 Codex”“SWE-bench 达到 X%”或“检索显著提升成功率”。

## 3–5 分钟 Demo

### 1. 说明任务和基线

打开一个 `benchmarks/tasks/*.json`，指出：

- `initial_commit` 固定故障状态；
- issue 不直接给出目标文件；
- `allowed_files` 是本地权限，不是模型定位答案；
- acceptance 文件不会复制进 Agent workspace。

### 2. 运行一个真实 case

```powershell
python run.py eval `
  --task-file benchmarks\tasks\dependency-cycle-order.json `
  --config basic `
  --config full
```

说明每个配置从相同 commit 建立独立 clone，不复用上一个配置的修复。

### 3. 展示 trajectory

```powershell
python run.py view "<artifact_dir>\trajectory.jsonl"
```

沿着下面的链路讲：

```text
User task → Provider → internal ToolCall → validation/permission
→ tool execution → ToolResult observation → next LLM step
→ model stops → external verifier → success or bounded repair
```

重点展示一次测试失败、一次源码编辑、测试通过和最终 verifier。若轨迹含 denied call，应解释它是
权限策略的可观察结果，而不是隐藏日志。

### 4. 展示 Evaluation

```powershell
python run.py report "<evaluation_dir>"
```

先讲成功判定，再讲成本指标，最后主动说明样本量和合成任务限制。最值得展示的 failure case 是模型
未修改便结束、随后被 verifier repair 救回；它能直接说明为什么 Harness 不能只相信模型自述。
仓库内的 [trajectory_example.md](trajectory_example.md) 已把该真实 run 整理成可公开浏览的逐步案例。

## 面试时应能回答

- `ToolResult` 怎样变成下一轮 `role=tool` observation？
- Pydantic、Workspace 与 PermissionPolicy 分别检查哪一层？
- 为什么 `resolve` 与 `relative_to` 要一起使用？
- 为什么测试返回非零可以是“成功复现”，却不是最终成功？
- Provider retry 与 Agent repair 的触发点和计数有何区别？
- 公开 Plan 为什么不是 Chain-of-Thought？重复 Plan 如何被记录？
- Hit@3=100% 为什么不能证明 Retrieval 提升了成功率？
- 为什么完整 `RunState.messages` 与 Provider working context 要分离？8k实验的22.1%为什么不能全部
  归因于 compaction？
- 为什么 `verified_success`、acceptance 和 diff audit 都必须通过？
- 为什么逻辑 workspace boundary 不能称为 OS sandbox？

能结合代码和某一条真实 trajectory 回答这些问题，项目就具备求职展示所需的解释深度。
