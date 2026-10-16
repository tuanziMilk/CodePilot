# Failure Analysis：从真实 trajectory 解释 Harness 价值

本文只把能够在 trajectory 和 evaluation 结果中复核的现象当作证据。旧开发目录中的试验、参考
修复和 scripted demo 不计入模型表现。

## 1. 模型提前结束，external verifier 触发 repair

在 `payment-idempotency-conflict/basic` 的首轮 challenge 实验中，模型读取代码后没有修改，也没有
运行测试，便返回普通 assistant message。Harness 没有接受“完成”声明，而是执行声明的 verifier，
得到 `DID NOT RAISE IdempotencyConflict`，记录 `verification_failed_retrying`，再把命令、退出码和
失败摘要作为新 observation 交给模型。第二轮模型才修改 `payments/service.py` 并通过测试。

在三次重复实验的 `dependency-cycle-order/basic/run-02` 中再次出现相同模式：模型已经看到失败测试，
却没有编辑便停止；external verifier 失败后，bounded repair 增加 DFS 的 `in_progress` 状态并成功。

结论：**模型说完成不是成功条件。** `agent_max_retries=0` 时，这两个 run 都会以 verification
failure 结束。Repair 是任务已经执行但结果不合格后的策略重试，不是普通工具试错。

## 2. Provider retry 与 Agent repair 是两条链路

重复实验的 `dependency-cycle-order/reliable/run-03` 在第一次 completion 上记录
`provider_request_retry_count=1`、该响应 latency 约 10.9 秒。Provider 在暂时性 HTTP/网络失败后
重发同一个请求，随后 Agent 正常规划、复现、修复并验证；`repair_retry_count` 始终为 0。

```text
Provider retry:  请求尚未可靠返回 → adapter 重发同一请求
Agent repair:    任务已经执行 → verifier 失败 → Harness 反馈并重新修复
```

二者分别记录，避免把 API 稳定性问题误判为 Agent 推理失败。

## 3. Planning 与 reproduction 有帮助，但不能保证成功

首轮 `dependency-cycle-order/reliable` 已生成计划并复现失败，但模型随后请求无关的 `git log`，并在
尚未修改时结束，仍需 verifier repair 才成功。这说明公开 Plan 是可检查的行为约束和实验变量，
不是执行保证，也不是隐藏 Chain-of-Thought。

当前 `update_plan` 对完全相同的计划返回 `tool_plan_unchanged`，不增加 `plan_version`。在 12 个
planning-enabled 重复 runs 中只观察到 1 次 no-op；它仍消耗一次 ToolCall，但状态和指标不会再把
重复计划伪装成有效进展。

## 4. Retrieval 命中不等于 Retrieval 造成收益

5-task challenge suite 的 lexical retrieval 为 Hit@1=60%、Hit@3=100%；该组平均 Steps 和 Token
低于 basic。但平均 `read_file` 只从 basic 的 8.2 降至 retrieval 的 8.0，模型仍会自行 list/read。

两任务三次重复中，retrieval 平均 Steps 最少、Token 最低，但这里只有两个独立 query；重复 run
不会产生新的检索问题。合理结论是“相关文件稳定进入 Top-3，且本轮观察到较低执行成本”，而不是
“Retrieval 已被证明显著提高成功率”。

## 5. 权限拒绝既提供边界，也产生效率成本

24-case 重复实验共出现 15 次 denied call：主要是 `git log`、`python -c`、`find | head`、`cat`
和 `ls -la`。所有 case 最终成功且没有越界修改，说明 policy 能阻止不在 MVP 能力表中的动作；但
模型偶尔会换一种写法再次尝试同类命令，说明自然语言拒绝提示不能保证零重复。

不应为了减少 denied 指标直接放开任意 Shell。后续是否扩权，应由失败任务证明某个命令对完成任务
必要，并补充精确 allowlist 与测试。

## 6. Token 波动主要来自多轮上下文和模型输出

`dependency-cycle-order/basic/run-03` 使用 44,813 tokens。其 Step 4 和 Step 6 分别记录 3,724 与
3,519 output tokens，而持久化的公开 ToolCall 很短。Provider usage 可能包含未写入 trajectory 的
生成 token；项目按“不保存私有 reasoning”设计，因而不能从日志反推具体内容。

随着 messages 累积，每轮还会重新发送已有 observation，因此无关读取、被拒绝命令和延迟终止既
增加步骤，也放大后续 input tokens。这里只报告可观察的 usage 与行为，不臆测隐藏推理。

## 7. 仍然存在的评测限制

- 两轮 challenge 实验均为 100% 成功，存在成功率天花板。
- 任务是小型、单根因、Python 合成仓库，无法代表企业仓库或 SWE-bench。
- 首轮每个 task/config 只有一次采样；重复实验只有两个独立任务。
- reliable 同时改变 planning 与 reproduction，不能识别二者各自的因果贡献。
- API latency 受网络和服务波动影响，应与 Steps、Tokens、工具调用一起解释。
- 外部 acceptance 位于 Agent workspace 外，但项目没有 OS sandbox，不能宣称对恶意代码强隔离。

这些限制不是需要隐藏的缺点，而是面试时说明“知道实验回答了什么、没有回答什么”的证据。
