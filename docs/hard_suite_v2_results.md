# Hard Suite V2：mvp-v2 真实模型结果

运行日期：2026-10-17。运行目录：`artifacts/evaluations/20261017T105522424137Z`。规模为
6 tasks × 4 configurations × 1 repeat = 24 cases。模型配置为 DeepSeek OpenAI-compatible
Provider、`deepseek-flash`、temperature 0、`max_steps=12`、`agent_max_retries=1`；prompt 为
`mvp-v2`，tool policy 为 `mvp-v1`。

成功必须同时满足 `verified_success`、外部 acceptance、allowed-file diff audit 和 Git HEAD audit。

## 聚合结果

| Config | Success | Avg steps | Avg tokens | Avg latency | Avg reads | Denied total | Step-limit saves |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic | 6/6 | 10.83 | 41,087.7 | 56.9s | 15.33 | 14 | 3 |
| reliable | 6/6 | 11.50 | 37,609.2 | 49.0s | 12.83 | 7 | 1 |
| retrieval | 6/6 | **9.17** | 37,793.2 | 51.1s | 13.83 | 14 | 0 |
| full | 6/6 | 10.17 | **36,701.8** | **47.1s** | **12.33** | **5** | 1 |

24/24 case 的外部验收和 audit 全部通过，0 infrastructure error、0 Agent repair、0 tool error。
总计使用 919,151 tokens，累计 run latency 约 20.42 分钟；两次 Provider request retry 均自动恢复。

相对 basic，本轮 retrieval 的平均 Steps 少 15.4%、Token 少 8.0%、latency 少 10.2%；full 的
平均 Steps 少 6.2%、Token 少 10.7%、latency 少 17.3%、读取次数少 19.6%、ToolCall 少 19.1%。
这些是单次小样本的描述性差异，不是统计显著或一般化因果结论。

聚合均值也不能代表每题都更好：`schema-alias-migration/full` 相对 basic 多用约 52.4% Token、
latency 高约 61.5%，而 Full 在其余 5 题的 latency 更低。该离群点说明 Planning + Retrieval 会因
具体轨迹产生额外成本，不能只展示平均值。

## Harness 与协议观察

- 5/24 runs 在第 12 个模型步骤结束时工作区已经正确；新的最终 verifier 将它们标记为
  `verified_success`，并通过 `verified_at_step_limit` 保留来源。旧终止规则会把同一状态误判为
  `max_steps`。这是本轮最直接、最可解释的 Harness 改进。
- planning-enabled runs 没有再次出现旧实验中的 `update_plan` 对象数组解析错误。reliable 有 1 次
  相同 plan no-op，full 为 0；这与 prompt 中加入准确 JSON 形状后的预期一致，但单次随机运行不能
  单独证明因果。
- 40 次 denied call 中，主要是组合 shell / inline Python、未列入白名单的命令、被策略归为网络或
  破坏性的操作，以及 8 次超过长度限制的 `BashInput`。Agent 最终均恢复到允许路径，但这是当前
  最明显的 Token 和 step 浪费来源。
- 所有修改都处于 allowed files。`filtered/basic` 修改 4 个文件而参考补丁涉及 3 个，
  `schema/reliable` 修改 3 个而参考补丁涉及 2 个；两者都通过外部契约，但后者增加了未实际使用的
  alias map，属于可讨论的轻微过度设计。reference patch 是一个合法解，不是唯一 gold patch。

## Retrieval 观察

retrieval 与 full 使用相同的确定性 Top-3 结果：

- changed-file Hit@1：16.7%；Hit@3：100%；
- reference-patch Hit@1：16.7%；
- reference-patch file recall@K：61.1%。

这说明 lexical retrieval 能稳定把至少一个相关区域放进 Top-3，但对需要修改 2–3 个文件的任务，
初始上下文并不能覆盖所有修复点。Retrieval 在本轮的步骤和成本低于 basic，但成功率全部触顶，且
每个任务只运行一次，因此只能报告相关性，不能写成“检索显著提升成功率”。

## 如何对外表述

可以表述为：在 6 个多文件契约任务、四种配置的 24 次真实模型运行中，CodePilot 完成 24/24
严格成功；Full 相对 Basic 平均 Token 少 10.7%、latency 少 17.3%，并通过 trajectory 定位
step-limit 误判、工具拒绝和过度修改等行为。

必须同时说明：任务是自建合成 benchmark、只有 6 个独立任务且每配置只运行一次，成功率存在天花板；
结果不等同 SWE-bench，也不支持生产级或统计显著的主张。

原始 `artifacts/` 默认不进入 Git。此次运行时仓库存在未提交改动，报告中的
`codepilot_git_commit=394cc263...` 只表示当时 HEAD，不能单独重建完整 working tree。发布正式冻结
结果时，应先提交当前实现，再从 clean worktree 重跑，或在 metadata 中增加 dirty-state/diff hash。
