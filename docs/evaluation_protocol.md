# Evaluation protocol

一个 case 是某个 TaskSpec、故障 commit、configuration 和 repetition 的一次独立运行。Evaluator 为每个 case 新建 clone；不会恢复、删除或复用旧工作区。旧源码目录里未提交的手工修复不会进入实验。

## 先检查，再运行

在项目根目录运行（run.py 自动选择此副本的 src 和 .env）：

```powershell
python run.py eval --suite benchmarks/suite.json --list
python run.py eval --suite benchmarks/suite.json --config basic --config full
python run.py eval --suite benchmarks/suite.json --repeat 3
```

`--list` / `--dry-run` 检查任务、基线 SHA、外部验收文件和重复项，列出将运行的 case 数；不读 API Key，不调用 LLM，不新建实验目录。实际运行才会使用你配置的模型服务，并按 case 产生真实请求。

可以重复传 `--task-file` 来选择几个 TaskSpec；`--suite` 的 tasks 路径相对 suite.json。重复 task_id 或 configuration 会在写文件前被拒绝。`--case-timeout 600` 是单次 Agent CLI 的时间限制，`--test-timeout 120` 是每次测试检查的限制，Git 命令限时 30 秒。

## 四个固定配置

| Configuration | 公开 plan + 先复现失败 | Lexical retrieval |
|---|---|---|
| basic | 关闭（update_plan 工具不可见） | 关闭 |
| reliable | 开启 | 关闭 |
| retrieval | 关闭（update_plan 工具不可见） | 开启 |
| full | 开启 | 开启 |

这是两个因素的 2×2 实验：可靠性控制组合与 retrieval。可靠性控制同时改变 planning 和 reproduction gate，不能把 basic→reliable 的差异归因于 planning 单项。每组保持同一模型、预算和工具策略；先选定配置，再完整跑完，避免中途因结果不好而调整参数。

## 一次 case 的验收过程

1. clone 并 detached checkout TaskSpec.initial_commit 的完整 40 位 SHA。
2. 在故障 clone 上运行 visible test 与外部 acceptance；两者应真正失败。测试收集错误、依赖问题、超时、无测试、初始已通过都属于 invalid_baseline，不当作 Agent 失败。
3. 启动公开 Agent CLI，记录 stdout/stderr 与 run artifacts。
4. Agent 结束后，在 workspace cwd 下用本次 Python 执行外部 acceptance。PYTHONPATH 只指向本次 clone 及 clone/src，避免误导入原 benchmark 或旧版代码。
5. 审计相对初始 commit 的 tracked 变更与所有 untracked 文件；忽略未跟踪的构建缓存，拒绝测试文件/白名单之外的源码修改，确认 HEAD 未变，保存 changes.diff。

`verification_command` 是模型可见的运行提示，也是 Harness 自己的 visible verifier。`acceptance_test_file` 则相对原 TaskSpec 定位，在 Agent workspace 外；它不会被复制到 clone 或写入 Agent 的 TaskSpec。acceptance 使用额外输入检查是否只针对可见测试写死结果，其文件摘要必须保持不变。这是逻辑上的隔离；本项目不提供对恶意代码的操作系统沙箱。

最终 `evaluation_outcome=success` 必须同时满足 CLI 成功返回、Harness `verified_success`、visible verifier 通过、外部 acceptance 通过、文件审计通过。正确补丁但 `max_steps` 仍是 failed，并单独保留 `acceptance_passed=true`。缺失 CLI artifacts 是 infra_error；单个 case 的基础设施异常会保存 result.json，后续 case 继续，汇总每次更新。

## 阅读结果

```powershell
python run.py report artifacts/evaluations/<evaluation_id>
```

也可用 `python -m codepilot.evaluation.report <evaluation_dir>`。它只读取已保存数据并输出 report.json / report.csv / report.md，不会再次运行 Agent。每个 case 还保存 baseline_visible_test.json、baseline_acceptance.json、acceptance_result.json、changes.diff、result.json、CLI 输出、trajectory 与 run metadata。

Success rate 严格计算完整成功；test pass rate 只看外部 acceptance。两者分开帮助识别“改对但没有正确终止”。Steps、repair retries、tokens、LLM latency、run latency、tool denied/error 使用真实 telemetry；缺失值保持 null，并记录有效样本数，不当作 0。失败/无效基线/infra 的 case 都保留在汇总分母中，同时记录类别，读结果时应先检查这些原因。

## 可报告结论的边界

任务集为自建合成 Bug，有清楚的故障与解法，适合检验 Harness 和复现流程。它不能等价为 SWE-bench 或真实企业仓库修复能力。先用一轮寻找流程问题，冻结协议后对代表性任务重复运行，再报告成功率、成本和失败案例。检索命中目标文件不等于因果收益；阅读 trajectory 确认是否减少探索、无关读取或后续失误。报告应同时呈现失败与成本，不只挑成功 Demo。
