# Evaluation results

本文冻结 CodePilot 求职 MVP 的两轮主要真实模型实验。原始 `artifacts/` 含完整 workspace、轨迹和
CLI 输出，因体积、运行时文件和潜在本机路径不进入 Git；这里保留协议、聚合数字和可复核解释。

> 这两轮数据早于 `hard_suite_v2`，不能与新套件直接混算。6 个多文件任务的 mvp-v2 候选结果见
> [hard_suite_v2_results.md](hard_suite_v2_results.md)，运行说明见
> [hard_suite_v2.md](hard_suite_v2.md)。

首轮 hard-v2 探索运行已经用于发现并修正 benchmark 契约和 step-limit 终止问题，但由于协议随后
升级为 `mvp-v2`，该轮不作为正式排名。分析见
[hard_suite_v2_exploratory_results.md](hard_suite_v2_exploratory_results.md)。

## 固定条件

| 项目 | 值 |
| --- | --- |
| Provider | DeepSeek OpenAI-compatible endpoint |
| Configured model identifier | `deepseek-flash` |
| Temperature | 0 |
| Max output tokens | 4096 |
| Agent max steps | 12 |
| Agent max repair retries | 1 |
| Provider request retries | 2 |
| Tool policy / prompt | `mvp-v1` / `mvp-v1` |
| Evaluated source commit | `e6a2f5128222753ca2d805c602be27004a1cb844` |

每个 case 从 TaskSpec 的完整 `initial_commit` 建立独立 detached clone。最终 success 必须同时满足：

```text
CLI 正常结束
+ Harness terminal_state == verified_success
+ external acceptance passed
+ 只修改 allowed files
+ tests / forbidden files 未被篡改
+ Git HEAD 未改变
```

四组配置构成 2×2 对照：basic、reliable（planning + reproduction）、retrieval（lexical context）和
full。reliable 是组合干预，不能单独测量 planning 的因果效果。

## Experiment A：5-task challenge suite

运行规模：5 tasks × 4 configurations × 1 repeat = 20 cases。

| Config | Success | Avg steps | Avg tokens | Avg latency | Avg reads | Avg denied | Hit@1 | Hit@3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic | 5/5 | 7.8 | 19,593.8 | 40.1s | 8.2 | 0.8 | n/a | n/a |
| reliable | 5/5 | 7.8 | 21,336.6 | 45.9s | 8.2 | 0.2 | n/a | n/a |
| retrieval | 5/5 | **6.2** | 18,151.6 | 34.5s | 8.0 | 0.4 | 60% | 100% |
| full | 5/5 | 7.2 | **18,083.0** | **32.3s** | **7.6** | 0.2 | 60% | 100% |

观察：

- 所有配置成功，成功率存在天花板，不能比较谁“更会修 Bug”。
- full 相对 basic 平均 Token 少约 7.7%、latency 少约 19.5%；retrieval 平均 Steps 少约 20.5%。
- Retrieval 将目标修改文件全部排进 Top-3，但读取次数只略降，收益不能简单归因为“少读文件”。
- basic 与 reliable 各出现一次 verifier-triggered repair；所有 Provider request retry 为 0。
- 所有 case 只修改预期实现文件，acceptance 和 audit 全部通过。

## Experiment B：两个代表任务的重复实验

选择曾触发 repair 的 `dependency-cycle-order` 与 `payment-idempotency-conflict`，运行
2 tasks × 4 configurations × 3 repeats = 24 cases。

| Config | Success | Avg steps | Avg tokens | Avg latency | Avg reads | Denied total | Plan no-op | Hit@1 | Hit@3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic | 6/6 | 8.17 | 26,470.3 | 51.0s | 9.17 | 8 | 0 | n/a | n/a |
| reliable | 6/6 | 7.50 | 17,608.5 | 37.3s | 7.83 | 1 | 0 | n/a | n/a |
| retrieval | 6/6 | **6.67** | **17,115.0** | **33.8s** | 8.50 | 4 | 0 | 50% | 100% |
| full | 6/6 | 7.00 | 18,298.8 | 34.1s | **7.67** | 2 | 1 | 50% | 100% |

相对 basic，本轮 retrieval 平均 Steps 少约 18.4%、Token 少约 35.3%、latency 少约 33.7%；full
平均 Token 少约 30.9%、latency 少约 33.2%。但只有两个独立任务，百分比是描述性结果，不是统计
显著性结论。

### 关键事件

- `dependency-cycle-order/basic/run-02`：模型复现失败后未编辑便停止；external verifier 失败，
  Harness 提供 feedback，repair 后通过。当前实验 Agent repair 共 1 次。
- `dependency-cycle-order/reliable/run-03`：第一次 Provider completion 发生一次请求重试；任务随后
  正常完成，Agent repair 为 0。这验证了两种 retry 分离。
- 12 个 planning-enabled runs 共观察到 1 次相同 Plan no-op；状态保持正确，但仍消耗 ToolCall。
- 24 cases 共 15 次 denied call、0 tool error；模型最终都恢复到允许的工具路径。
- 所有 case acceptance、allowed-file audit 和 HEAD audit 均通过。

## 如何使用这些结果

主 README 使用 Experiment A 展示覆盖 5 类 challenge task 的结果；Experiment B 用来讨论重复性、
variance 和 failure modes。不要把 B 的较大百分比替换成“总体性能提升”，也不要把相同 retrieval
query 的三次重复当成六个独立检索任务。

求职项目能够支持的结论是：CodePilot 已形成可运行、可追踪、可评估的 Coding Agent 闭环；可靠性
控制和 retrieval 在当前小样本中改变了步骤与成本，并产生了可解释的成功/失败轨迹。它不能支持
SWE-bench、生产级 sandbox 或一般化显著提升等更强主张。

## Experiment C：6-task Hard Suite V2（mvp-v2 候选结果）

运行规模：6 tasks × 4 configurations × 1 repeat = 24 cases。四组配置均为 6/6 strict success。
Retrieval 的平均 Steps 最少（9.17）；Full 的平均 Token（36,701.8）、latency（47.1s）、读取次数
（12.33）和 denied calls（共 5 次）最低。Full 相对 Basic 平均 Token 少 10.7%、latency 少
17.3%。5 次运行由 step-limit 后的最终 verifier 正确收敛，直接验证了新版 termination 语义。

Retrieval reference Hit@1 为 16.7%，平均 reference-file recall@K 为 61.1%，说明 Top-3 通常命中
相关区域但不能覆盖全部多文件修复点。完整表格、工具拒绝分类、过度修改案例与复现限制见
[hard_suite_v2_results.md](hard_suite_v2_results.md)。
