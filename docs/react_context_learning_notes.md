# ReAct 与上下文管理学习手册

## 1. 这次补的 ReAct 到底是什么

ReAct 是 **Reason + Act** 的 Agent 工作方式，不是必须安装的框架。它强调模型不要一次性猜出最终
答案，而是在环境反馈中循环：

```text
任务与当前上下文
  → 模型选择下一项 Action
  → Harness 校验并执行 ToolCall
  → ToolResult 成为 Observation
  → 模型依据 Observation 选择下一项 Action
  → 模型停止调用工具
  → 外部 verifier 决定是否成功
```

CodePilot 从 Phase 1 起就有这个循环。这次增强是把它变成更明确、可观测、上下文有界的
**ReAct-style loop**，而不是引入 LangChain 的 ReAct Agent 实现。

经典 ReAct 论文示例常把 `Thought` 写出来，但工程上不需要保存模型私有思维链。CodePilot 的对应
关系是：

| ReAct 概念 | CodePilot 实现 |
| --- | --- |
| Reason | 模型内部推理，对 Harness 不透明，不记录 hidden reasoning |
| Action | Provider 归一化后的 `ToolCall` |
| Action summary | Harness 根据工具名和参数生成的公开短摘要 |
| Observation | 带 `tool_name`、`status`、`return_code` 和输出的 `role=tool` 消息 |
| Finish | 模型不再请求工具，Harness 启动独立 verification |

因此面试时应说“实现了 ReAct-style action/observation loop”，不要声称项目持久化了完整 Thought。

## 2. 为什么还需要上下文管理

原实现把 `RunState.messages` 在每轮完整发送给模型。第 8 步不仅会发送当前任务，还会再次发送前
7 步读过的文件、测试输出、被拒绝的请求和模型消息。这样会产生三个问题：

1. 输入 Token 随 step 增长；
2. 旧的失败和重复读取会干扰当前决策；
3. 大文件内容可能挤占真正相关的最近反馈。

现在区分两份视图：

```text
RunState.messages（完整、规范历史）
  ├─ 用于运行状态和审计，不删除
  └─ ReActContextManager.build()
       ├─ 固定保留 system / task / 初始 retrieval context
       ├─ 将较老的完整 step 变成公开、确定性摘要
       ├─ 原样保留最近若干 assistant + tool 消息
       └─ 生成 ChatRequest.messages（Provider 工作视图）
```

这叫 **working context compaction**，不是长期 Memory，也不是 Repository Retrieval。

## 3. 压缩算法做了什么

默认参数：

```dotenv
AGENT_CONTEXT_TRIGGER_CHARS=16000
AGENT_CONTEXT_MAX_CHARS=32000
AGENT_CONTEXT_RECENT_STEPS=4
```

每次 Provider 请求前，`ReActContextManager` 会：

1. 固定保留 system prompt、用户任务和首轮 lexical retrieval；
2. 按“一个 assistant action + 随后的 tool observations / verifier feedback”切分 step；
3. 小于 16000 字符时保留完整历史，不因 step 数量单独触发压缩；
4. 达到 trigger 后，最多原样保留最近 4 个 step；
5. 若仍超过 max budget，继续按完整 step 移出较老内容；
6. 根据公开 `ToolCall` 和 `ToolResult` 生成一条短摘要；
7. 在摘要顶部补充公开状态：当前 plan、是否已复现失败、repair retry 次数；
8. 保证保留下来的 assistant tool call 与对应 tool message 不被拆开。

摘要是普通程序拼接出来的，不调用 LLM，因此没有额外模型请求，也不会凭空“总结”代码语义。它
不会复制旧 assistant 的自由文本，只描述已经可观察到的工具、目标和结果片段。

`AGENT_CONTEXT_TRIGGER_CHARS` 决定何时开始压缩，`AGENT_CONTEXT_MAX_CHARS` 是尽量维持的上限；
二者都是 provider-neutral 的近似预算，不等同 tokenizer 的精确 Token 上限。
如果最新单个 step 本身异常巨大，当前 MVP 会优先保持 tool-call 协议完整，而不是强行截断它。

## 4. Observation 为什么也改了

旧版把 `output_summary` 直接作为 tool message。某些文件工具的文本不能一眼看出成功、拒绝还是工具
错误。现在模型会收到：

```text
Tool: edit_file
Status: denied
Return code: 2
Observation:
The requested path is not writable.
```

这让下一轮模型不必从自然语言猜执行状态，也是 ReAct 中“环境反馈必须明确”的工程化体现。

## 5. 它与 Retrieval、RAG、Memory 的区别

| 能力 | 解决的问题 | 当前 CodePilot |
| --- | --- | --- |
| Repository Retrieval | 大仓库里先找哪些代码相关 | run 开始时 lexical Top-K |
| Working context | 多步对话中保留哪些历史 | 公开摘要 + 最近完整 steps |
| RAG | 检索外部/仓库知识并注入生成 | 只有一个极简 lexical repository retrieval 基线 |
| Long-term Memory | 跨 run 记住经验或用户偏好 | 未实现 |

所以“加强上下文”不等于“补一个向量数据库”，也不需要先引入 LangChain。

## 6. 如何运行和观察

默认启用压缩：

```powershell
python run.py run `
  --task-file benchmarks\tasks\addition-smoke.json `
  --context-mode compact
```

保留旧行为用于对照：

```powershell
python run.py run `
  --task-file benchmarks\tasks\addition-smoke.json `
  --context-mode full
```

较长任务发生压缩后，`trajectory.jsonl` 会出现 `context_compaction` 事件，pretty viewer 会显示：

```text
Context: compacted 3 older step(s); messages 13→8; chars 28000→12000
```

`final_summary.json` 中可查看：

```text
context_compaction_count
metrics.context_compaction_count
metrics.context_request_count
metrics.total_context_chars_sent
metrics.context_chars_saved
metrics.max_context_chars_before
metrics.max_context_chars_after
metrics.max_context_steps_compacted
```

Evaluation 还提供两个不加入默认四组、避免自动增加 API 成本的对照配置：

```powershell
python run.py eval `
  --suite benchmarks\context_ablation_v2_suite.json `
  --config full-uncompacted `
  --config full `
  --repeat 3
```

两组的 Planning、失败复现和 Retrieval 相同，唯一差别是完整历史与压缩上下文。仍建议至少重复 3
次再讨论成功率或 Token 差异，单次轨迹只能作为案例分析。

## 7. 当前 limitation

- 摘要是规则式的，不理解代码语义，可能丢失较老输出中的细节；
- 字符数只是 Token 的近似值；
- 最近的完整步骤仍可能包含重复内容；
- 没有基于相关性的历史选择，也没有跨 run Memory；
- 已完成2-task × 3-repeat的强制触发 A/B，但默认16k仍需要更长任务验证；
- 8k实验中 compact 组出现更多重复读取，可能是信息损失或编辑后主动复查，当前不能区分；
- 端到端 Token 差异同时受步骤数与模型随机性影响，不能全部归因于摘要算法。

这正适合作为求职项目的后续实验点：实现不复杂，但有清晰问题、可切换 baseline、可观察指标和诚实
边界。

## 8. 实验应该怎样解释

默认16k校准中，compact 组一次压缩都没有发生。这不是“压缩无效”，而是实验处理没有生效；它只能
证明短任务不会过早压缩。随后用临时8k trigger进行12-case压力实验，6个 compact run 共发生14次
压缩，且两组都保持6/6 strict success。

实验中 compact 平均输入 Token 少22.1%，但能由算法直接确认的是累计消息字符少约4.9%、单轮峰值
上下文少约11.7%。剩余差异包含模型少走步骤等轨迹效应。面试时应同时报告观察值和直接机制指标，
不要把22.1%全部说成 compaction 的确定性收益。
