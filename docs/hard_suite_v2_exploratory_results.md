# Hard Suite V2 首轮探索结果（已被 mvp-v2 协议取代）

运行日期：2026-10-17。规模：6 tasks × 4 configurations × 1 repeat = 24 cases。该轮使用旧的
`mvp-v1` prompt/termination 语义；它的作用是审计评测设计并发现 Failure Modes，不作为最终配置排名。

## 原始机械结果

| Config | Strict success | External acceptance | Avg steps | Avg tokens | Avg run latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| basic | 4/6 | 5/6 | 10.67 | 34,564 | 49.7s |
| reliable | 3/6 | 4/6 | 11.17 | 40,071 | 47.4s |
| retrieval | 3/6 | 4/6 | 10.17 | 39,121 | 47.2s |
| full | 3/6 | 5/6 | 10.17 | 33,688 | 42.9s |

总计 13/24 strict successes、18/24 external acceptance passes、7 个 `max_steps`、0 个
infrastructure error、0 次 Provider retry 和 1 次 Agent repair。总 Token 为 884,662；Provider
没有返回 cost。

这些数字不能直接解释成 basic 优于 full：其中 5 个 case 的补丁已经通过 external acceptance，
却因为模型在第 12 步前没有停止而被判失败。

## Harness 发现

- filtered 的 reliable/retrieval/full，以及 webhook 的 basic/full，均出现“acceptance 已通过但
  `max_steps`”现象。filtered/retrieval 甚至在第 10 和第 12 步两次运行 pytest 成功。
- Planning-enabled runs 出现 7 次错误的 `update_plan` 对象数组参数和 4 次相同 plan no-op，消耗了
  紧张的行动预算。
- basic 与 retrieval 各有 11 次 denied calls，reliable 有 6 次，full 为 0；常见原因是 inline
  `python -c`、组合 shell 命令或受保护路径。
- 旧语义在 step limit 后不运行 verifier，因此把正确工作区和错误工作区都统一归为 `max_steps`。

对应改进：`mvp-v2` 明示 `update_plan({"steps":["..."]})` 参数形状，并在 LLM 行动预算耗尽后执行
一次最终本地 verifier。该 verifier 不增加模型步骤，也不允许继续修复；报告用
`verified_at_step_limit` / `step_limit_successes` 单独标识。

## Retrieval 发现

两个 lexical 配置使用相同的确定性 Top-3：

- changed-file Hit@3：100%；
- reference-patch Hit@1：1/6；
- reference-patch file recall@K：平均 61.1%。

Top-1 经常是测试或刻意放置的邻近干扰文件，例如 plugin 任务的 `legacy_registry.py`、schema 任务的
`legacy.py`。这说明 lexical retrieval 能找到相关代码区域，但不能稳定覆盖跨文件修复点。changed-file
Hit@K 又是在运行后拿 Agent 实际修改文件计算，容易显得过于乐观，因此多文件任务必须同时报告
reference-patch recall，并检查 trajectory；reference patch 也只是一个合法解，不是唯一 gold patch。

## Benchmark 发现

外部验收审计发现三处公开规格与隐藏断言不完全一致：

1. role 题要求保留公共事件契约，却没有向 Agent 公开 `user_id`/`roles` 的准确 payload；仓库现有
   listener 反而使用 `account_id`。
2. ledger 题用 Python `is` 检查结果对象身份，而公开需求只要求相同请求复用等价结果且不重复记账。
3. webhook 题要求失败后 `store.get(id) is None`，但 issue 只说明失败后可重试，没有明确禁止保存
   未完成记录。

当前任务已经分别改为：明示 role payload、ledger 使用值相等并检查 journal 不增长、webhook 明示
失败不留记录。离线 validator 的 6/6 只能证明 baseline 会失败且 reference 能修复，不能自动证明
issue 与 acceptance 语义公平；这次探索正好说明为什么 benchmark 还需要人工契约审计。

## 可使用与不可使用的结论

可以把该轮用于展示 CodePilot 能区分补丁正确性、终止失败、权限拒绝、规划协议错误和 benchmark
缺陷。不能把 66.7% vs 50% 写成模型或配置能力排名，也不能与修正后的 `mvp-v2` 结果合并。
