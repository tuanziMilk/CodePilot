# Hard Suite V2：降低小任务天花板

旧 challenge suite 的四组配置全部成功，适合证明评测链路，却不足以区分 Agent 能力。`hard_suite_v2`
用 6 个可复现的合成任务增加定位与修复负担，同时保持本地运行简单：只需要 Python、Git 和 pytest，
不引入 Docker、数据库或网络服务。

## 任务设计

| Task | 文件数 | 参考修改点 | 主要难点 |
| --- | ---: | ---: | --- |
| schema-alias-migration | 12 | 2 | 新旧 schema 同时读取、只写规范字段、保留 falsy 值 |
| role-cache-invalidation | 12 | 2 | 写服务发布稳定事件，监听器只失效目标用户 |
| filtered-cursor-pagination | 12 | 3 | 过滤后稳定排序、排他游标、终页 cursor |
| webhook-dedup-transaction | 12 | 2 | 失败不占用幂等键、重复返回旧结果、载荷冲突 |
| plugin-resolution-shadowing | 13 | 2 | 数字版本排序、主注册表优先、legacy 干扰文件 |
| ledger-transfer-atomicity | 13 | 2 | 提交前完整校验、批量原子写入、请求载荷冲突 |

问题描述只说明行为，不给源码路径；`allowed_files` 仍列出全部实现文件，避免权限白名单直接泄露
答案。visible test 展示主要症状，Agent workspace 外的 acceptance test 检查边界与回归。reference
metadata 只供离线题目校验和运行后的 evaluator 指标使用，不会物化进 Agent 看到的 `task.json`。

这些任务借鉴真实 benchmark 的基本原则：固定故障 revision、issue text、可执行测试与补丁级验收。
它们不是 SWE-bench 的子集，也没有声称复刻真实项目分布。后续若要继续扩展，可参考
[SWE-bench](https://github.com/SWE-bench/SWE-bench)、[BugsInPy](https://github.com/soarsmu/BugsInPy)
与 [Defects4J](https://defects4j.org/)；这些方案的环境、依赖和隔离成本更高，应作为投递后的增强。

## 当前离线有效性

`python run.py validate --suite benchmarks\hard_suite_v2.json` 已验证 6/6：

- 故障 baseline 的 visible test 失败；
- 故障 baseline 的 external acceptance 失败；
- 应用 evaluator-only reference edits 后两者通过；
- 原始 benchmark repo 保持 clean。

这只能证明题目有效，不能算模型成绩。

2026-10-17 的首轮 24-case 探索实验进一步发现了三个 issue/acceptance 契约不完全对齐的问题，
以及正确补丁在 step limit 处未执行最终验证的问题。当前 `mvp-v2` 协议已经：

- 明示 `roles.changed` 的公开 payload；
- 用结果相等和无重复副作用验证 ledger 幂等，不要求 Python 对象身份相同；
- 明示失败 webhook 不得留下 delivery record；
- 在 LLM 步数耗尽后执行一次只读的最终 verifier，测试仍失败时继续保留 `max_steps`；
- 给 `update_plan` 提供准确的字符串数组 JSON 示例。

首轮数字只作为 Failure Analysis，不是最终模型排名，见
[hard_suite_v2_exploratory_results.md](hard_suite_v2_exploratory_results.md)。

## 推荐运行顺序

先确认计划，不调用 API：

```powershell
python run.py eval --suite benchmarks\hard_suite_v2.json --dry-run
```

预算优先时，只比较最小 Agent 与完整 Agent，共 12 个 cases：

```powershell
python run.py eval --suite benchmarks\hard_suite_v2.json --config basic --config full
```

若你需要同一个 `evaluation_dir` 内的完整 2×2 对照，则跳过上面的实际运行命令，直接跑四配置，
共 24 个 cases：

```powershell
python run.py eval --suite benchmarks\hard_suite_v2.json
```

两条实际运行命令二选一，避免重复支付 basic/full 的 API 成本。若 12-case 试跑已经完成，后续也可以
只跑 `--config reliable --config retrieval`，再由分析者并列阅读两个报告，但不要直接把两个目录伪装成
一次预先冻结的实验。

把终端最后的 `evaluation_dir=...` 发给分析者，或本地生成报告：

```powershell
python run.py report "<evaluation_dir>"
```

## 应重点观察什么

- `success_rate`：严格成功，需要 Agent 终态、visible verifier、external acceptance 和 diff audit
  同时通过。
- `step_limit_successes`：LLM 已耗尽行动步数，但当前工作区通过最终 verifier 的次数；它不会增加
  模型行动预算。
- `test_pass_rate`：补丁是否通过外部验收；可识别“修对了但没正确终止”。
- Steps、Tokens、latency、read/search 次数：成功之外的成本。
- changed Hit@K：检索是否命中 Agent 最后实际修改的文件，保留用于旧报告兼容。
- reference Hit@1：Top-1 是否命中任一参考修改文件。
- reference file recall@K：Top-K 覆盖了多少参考修改文件；多文件任务比只看首次命中更可信。
- trajectory 与 `changes.diff`：判断失败源于定位、理解、编辑限制、权限、验证还是终止。

不要只期待成功率下降。如果 basic/full 仍都成功，但 full 明显减少无关读取、步骤或 repair，也能形成
可解释结果；反过来，如果 retrieval 带来噪声或 plan 增加成本，也应如实报告。

## 局限

- 每题仍只有 12–13 个实现文件，属于中等规模合成任务，不是大型仓库。
- reference patch 有 2–3 个精确替换点，不覆盖重构、新依赖或长补丁。
- 只使用 Python/pytest，不能代表跨语言构建环境。
- 一次运行受模型随机性影响；找到有区分的任务后，再对少量代表任务做 3 次重复即可。
